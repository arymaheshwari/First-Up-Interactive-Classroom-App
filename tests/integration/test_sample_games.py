"""
T6 sample games — every file in sample_games/ imports cleanly, each member's games
meet the T6 coverage rules, and each member game plays end to end with a perfect
player scoring the maximum.

Member games are named `<netid>_<topic>_classroom.json` / `<netid>_<topic>_party.json`;
the starter games (no such suffix) only have to import.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from .engine.orchestrator import run_game
from .engine.scoring import GameScenario, PlayerScript, QuestionSpec
from .helpers import Tracker

SAMPLE_DIR = pathlib.Path(__file__).parent.parent.parent / "sample_games"
ALL_FILES = sorted(SAMPLE_DIR.glob("*.json"))
MEMBER_FILES = [
    p for p in ALL_FILES if p.stem.endswith("_classroom") or p.stem.endswith("_party")
]
ALL_TYPES = {
    "multiple_choice",
    "true_false",
    "fill_in_the_blank",
    "multi_select",
    "pin_drop",
    "estimate",
}


@pytest.fixture
def t(docker_stack, base_url, admin_token):
    tracker = Tracker(base_url, admin_token)
    yield tracker
    tracker.cleanup()


def _bundle(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _import(t: Tracker, course: int, path: pathlib.Path) -> int:
    r = t.admin(
        "POST",
        "/admin/games/import",
        files={"file": (path.name, path.read_bytes(), "application/json")},
        data={"course_id": str(course)},
    )
    assert r.status_code == 201, f"{path.name}: {r.text}"
    game_id = r.json()["game_id"]
    t.game_ids.append(game_id)
    return game_id


@pytest.mark.parametrize("path", ALL_FILES, ids=[p.name for p in ALL_FILES])
def test_sample_game_imports_cleanly(t, path):
    bundle = _bundle(path)
    assert bundle["format"] == "buzzer/game" and bundle["version"] == 1
    game_id = _import(t, t.course(), path)

    stored = t.admin("GET", f"/admin/games/{game_id}/questions").json()
    assert [(q["type"], q["prompt"]) for q in stored] == [
        (q["type"], q["prompt"]) for q in bundle["questions"]
    ]


def test_each_member_has_a_classroom_and_a_party_game():
    members: dict[str, set[str]] = {}
    for path in MEMBER_FILES:
        netid = path.stem.split("_", 1)[0]
        members.setdefault(netid, set()).add(path.stem.rsplit("_", 1)[1])
    assert members, "no member games found in sample_games/"
    for netid, kinds in members.items():
        assert kinds == {"classroom", "party"}, f"{netid}: {sorted(kinds)}"


@pytest.mark.parametrize("path", MEMBER_FILES, ids=[p.name for p in MEMBER_FILES])
def test_member_game_meets_t6_coverage(path):
    questions = _bundle(path)["questions"]
    assert {q["type"] for q in questions} == ALL_TYPES, "every question type"
    assert {q["grading_type"] for q in questions} == {"ACCURACY", "COMPLETENESS"}


def _perfect_answer(q: dict) -> dict:
    """An answer worth full points_value (any valid answer for COMPLETENESS)."""
    ad, cfg = q["answer_data"], q["config"]
    complete = q["grading_type"] == "COMPLETENESS"
    match q["type"]:
        case "multiple_choice":
            pts = ad.get("answer_points") or [0]
            return {"selectedIndex": 0 if complete else pts.index(max(pts))}
        case "true_false":
            return {
                "selectedValue": True if complete else ad["answer_points"]["true"] > 0
            }
        case "fill_in_the_blank":
            return {"text": "anything" if complete else ad["acceptedAnswers"][0]}
        case "multi_select":
            return {
                "selectedIndices": [0]
                if complete
                else [i for i, p in enumerate(ad["answer_points"]) if p > 0]
            }
        case "pin_drop":
            grid = cfg["grid"]
            return {
                "point": {"x": grid["xMin"], "y": grid["yMin"]}
                if complete
                else ad["target"]
            }
        case "estimate":
            return {"value": 1 if complete else ad["answer"]}
    raise AssertionError(f"unknown type {q['type']}")


@pytest.mark.parametrize("path", MEMBER_FILES, ids=[p.name for p in MEMBER_FILES])
async def test_member_game_plays_end_to_end(t, base_url, path):
    questions = _bundle(path)["questions"]
    game_id = _import(t, t.course(), path)
    room = t.room(game_id)
    tokens = []
    for _ in range(2):
        guest = t.guest(room)
        assert guest.status_code == 200, guest.text
        tokens.append(guest.json()["access_token"])
    scenario = GameScenario(
        name=path.stem,
        questions=[
            QuestionSpec(
                type=q["type"],
                grading_type=q["grading_type"],
                prompt=q["prompt"],
                config=q["config"],
                answer_data=q["answer_data"],
                points_value=q["points_value"],
            )
            for q in questions
        ],
        player_scripts=[
            PlayerScript(responses=[_perfect_answer(q) for q in questions]),
            PlayerScript(responses=[None for _ in questions]),
        ],
    )

    perfect, skipper = await run_game(
        base_url=base_url,
        host_token=t.admin_token,
        player_tokens=tokens,
        room_code=room,
        scenario=scenario,
    )

    assert perfect["yourFinalScore"] == pytest.approx(
        sum(q["points_value"] for q in questions)
    )
    assert skipper["yourFinalScore"] == 0
