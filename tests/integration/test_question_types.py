"""
T7 question types — the shared registry and the two new types end to end.

Scenario ids (N1…N8) match docs/plans/t7-new-question-types.md §8.2.
Runs against the live stack, like the rest of tests/integration.
"""

from __future__ import annotations

import asyncio
import copy
import json

import pytest

from .engine.orchestrator import run_game
from .engine.scoring import GameScenario, PlayerScript, QuestionSpec
from .engine.socket_client import TestSocketClient
from .helpers import Tracker

EVENT_TIMEOUT = 20.0


@pytest.fixture
def t(docker_stack, base_url, admin_token):
    tracker = Tracker(base_url, admin_token)
    yield tracker
    tracker.cleanup()


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

GRID = {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5, "step": 1}

PIN = {
    "type": "pin_drop",
    "grading_type": "ACCURACY",
    "prompt": "Plot the x-intercept of y = 2x - 4",
    "config": {"grid": GRID, "snap": True},
    "answer_data": {"target": {"x": 2, "y": 0}, "fullRadius": 1, "zeroRadius": 4},
    "points_value": 10,
    "time_limit_seconds": 30,
}
PIN_COMPLETE = {
    **PIN,
    "grading_type": "COMPLETENESS",
    "prompt": "Pin your favourite point",
    "answer_data": {},
}
EST_ABS = {
    "type": "estimate",
    "grading_type": "ACCURACY",
    "prompt": "What year did YouTube launch?",
    "config": {"unit": "year", "integer": True},
    "answer_data": {
        "answer": 2005,
        "tolerance": {"mode": "absolute", "full": 1, "zero": 10},
    },
    "points_value": 10,
    "time_limit_seconds": 30,
}
EST_REL = {
    **EST_ABS,
    "prompt": "How tall is Everest?",
    "config": {"unit": "m"},
    "answer_data": {
        "answer": 8849,
        "tolerance": {"mode": "relative", "full": 5, "zero": 25},
    },
}
EST_COMPLETE = {
    **EST_ABS,
    "grading_type": "COMPLETENESS",
    "prompt": "How many cups of coffee today?",
    "config": {"unit": "cups"},
    "answer_data": {},
}
NEW_TYPES = [PIN, PIN_COMPLETE, EST_ABS, EST_REL, EST_COMPLETE]

MULTI_SELECT = {
    "type": "multi_select",
    "grading_type": "ACCURACY",
    "prompt": "Which of these are prime?",
    "config": {"options": ["Two", "Three", "Four"]},
    "answer_data": {"answer_points": [1, 1, -1]},
    "points_value": 2,
    "time_limit_seconds": 30,
}


def _with(question: dict, **changes) -> dict:
    """Deep copy of `question` with nested changes: answer_data__target=… sets that key."""
    q = copy.deepcopy(question)
    for path, value in changes.items():
        *parents, leaf = path.split("__")
        node = q
        for p in parents:
            node = node[p]
        node[leaf] = value
    return q


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def add_questions(
    t: Tracker, game_id: int, questions: list[dict], token=None, prefix="/admin"
) -> list[dict]:
    created = []
    for q in questions:
        r = t.call(
            "POST",
            f"{prefix}/games/{game_id}/questions",
            token or t.admin_token,
            json=q,
        )
        assert r.status_code == 201, r.text
        created.append(r.json())
    return created


def import_bundle(t: Tracker, course_id: int, questions: list[dict]):
    bundle = {
        "format": "buzzer/game",
        "version": 1,
        "game": {"title": "T7 import", "description": "", "max_players": 50},
        "questions": questions,
    }
    r = t.admin(
        "POST",
        "/admin/games/import",
        files={"file": ("game.json", json.dumps(bundle), "application/json")},
        data={"course_id": str(course_id)},
    )
    if r.status_code == 201:
        t.game_ids.append(r.json()["game_id"])
    return r


def scenario(questions: list[dict], answers: list[list[dict]]) -> GameScenario:
    """A scenario for questions that already exist; `answers` is one list per player."""
    return GameScenario(
        name="t7",
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
        player_scripts=[PlayerScript(responses=a) for a in answers],
    )


async def play(t: Tracker, base_url: str, questions: list[dict], answers):
    """Create a game with `questions`, play it with one guest per answer list."""
    course = t.course()
    game_id = t.game(course)
    add_questions(t, game_id, questions)
    room = t.room(game_id)
    tokens = []
    for _ in answers:
        guest = t.guest(room)
        assert guest.status_code == 200, guest.text
        tokens.append(guest.json()["access_token"])
    game_over = await run_game(
        base_url=base_url,
        host_token=t.admin_token,
        player_tokens=tokens,
        room_code=room,
        scenario=scenario(questions, answers),
    )
    return t.session_id(room), game_over


async def first_of(client: TestSocketClient, *events: str) -> tuple[str, dict]:
    waits = {
        asyncio.create_task(client.wait_for(ev, EVENT_TIMEOUT)): ev for ev in events
    }
    done, pending = await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    task = done.pop()
    return waits[task], task.result()


class LiveGame:
    """
    Step-by-step control of a live game (run_game only returns game_over), so tests
    can inspect every payload: new_question, answer acks/errors, results, game over.
    """

    def __init__(self, t: Tracker, base_url: str, questions: list[dict], players: int):
        self.t, self.base_url = t, base_url
        course = t.course()
        self.game_id = t.game(course)
        add_questions(t, self.game_id, questions)
        self.room = t.room(self.game_id)
        self.session_id = t.session_id(self.room)
        self.host = TestSocketClient(base_url, t.admin_token, "host")
        self.players = [
            TestSocketClient(base_url, self.guest_token(), f"p{i}")
            for i in range(players)
        ]

    def guest_token(self) -> str:
        r = self.t.guest(self.room)
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    async def join(self, client: TestSocketClient, role: str) -> dict:
        await client.connect()
        await client.emit("join_room", {"room_code": self.room, "role": role})
        return await client.wait_for("sync_state", EVENT_TIMEOUT)

    async def __aenter__(self) -> LiveGame:
        await self.join(self.host, "HOST")
        for p in self.players:
            await self.join(p, "PLAYER")
        return self

    async def __aexit__(self, *exc) -> None:
        await asyncio.gather(
            *[c.disconnect() for c in (self.host, *self.players)],
            return_exceptions=True,
        )

    async def next_question(self) -> tuple[dict, list[dict]]:
        await self.host.emit("host_advance", {})
        host_q = await self.host.wait_for("new_question", EVENT_TIMEOUT)
        player_qs = [
            await p.wait_for("new_question", EVENT_TIMEOUT) for p in self.players
        ]
        return host_q, player_qs

    async def answer(self, player: int, question_id: int, answer: dict):
        client = self.players[player]
        await client.emit(
            "submit_answer",
            {"question_id": question_id, "answer_data": answer, "answer_time_ms": 500},
        )
        return await first_of(client, "answer_received", "error")

    async def results(self) -> tuple[dict, list[dict]]:
        await self.host.emit("host_advance", {})
        host_r = await self.host.wait_for("question_results", EVENT_TIMEOUT)
        player_rs = [
            await p.wait_for("question_results", EVENT_TIMEOUT) for p in self.players
        ]
        return host_r, player_rs

    async def finish(self) -> tuple[dict, list[dict]]:
        await self.host.emit("host_advance", {})
        host_over = await self.host.wait_for("game_over", EVENT_TIMEOUT)
        player_overs = [
            await p.wait_for("game_over", EVENT_TIMEOUT) for p in self.players
        ]
        return host_over, player_overs


def _no_answer_in(payload: dict) -> None:
    text = json.dumps(payload)
    assert "answer_data" not in payload
    for leak in ('"target"', '"answer"', '"tolerance"', "fullRadius", "zeroRadius"):
        assert leak not in text, f"{leak} leaked in {text}"


# ---------------------------------------------------------------------------
# N1 — authoring through both routers
# ---------------------------------------------------------------------------


def test_n1_new_types_created_through_host_and_admin(t):
    course = t.course()
    _, host = t.host(course)
    host_game = t.game(course, token=host, prefix="/host")
    admin_game = t.game(course)

    for game_id, token, prefix in (
        (host_game, host, "/host"),
        (admin_game, None, "/admin"),
    ):
        created = add_questions(t, game_id, NEW_TYPES, token=token, prefix=prefix)
        for sent, stored in zip(NEW_TYPES, created):
            assert stored["type"] == sent["type"]
            assert stored["config"] == sent["config"]
            assert stored["answer_data"] == sent["answer_data"]

    listed = t.call("GET", f"/host/games/{host_game}/questions", host).json()
    assert [q["type"] for q in listed] == [q["type"] for q in NEW_TYPES]


# ---------------------------------------------------------------------------
# N2 — create, update and import reject the same bad shapes (T7's warning)
# ---------------------------------------------------------------------------

INVALID = {
    "grid_too_dense": _with(
        PIN, config__grid={"xMin": -15, "xMax": 15, "yMin": -10, "yMax": 10, "step": 1}
    ),
    "grid_not_whole_steps": _with(PIN, config__grid={**GRID, "step": 0.3}),
    "grid_boolean_number": _with(PIN, config__grid={**GRID, "step": True}),
    "target_outside_grid": _with(PIN, answer_data__target={"x": 9, "y": 0}),
    "full_not_below_zero": _with(PIN, answer_data__fullRadius=4),
    "relative_answer_zero": _with(EST_REL, answer_data__answer=0),
    "fraction_when_integer": _with(EST_ABS, answer_data__answer=2005.5),
    "unknown_tolerance_mode": _with(
        EST_ABS, answer_data__tolerance={"mode": "percent", "full": 1, "zero": 10}
    ),
    "unit_too_long": _with(EST_ABS, config__unit="x" * 21),
}


@pytest.mark.parametrize("bad", list(INVALID.values()), ids=list(INVALID))
def test_n2_invalid_shapes_rejected_by_create_update_and_import(t, bad):
    course = t.course()
    game_id = t.game(course)
    valid = PIN if bad["type"] == "pin_drop" else EST_ABS
    [question] = add_questions(t, game_id, [valid])

    created = t.admin("POST", f"/admin/games/{game_id}/questions", json=bad)
    updated = t.admin(
        "PUT",
        f"/admin/games/{game_id}/questions/{question['id']}",
        json={"config": bad["config"], "answer_data": bad["answer_data"]},
    )
    imported = import_bundle(t, course, [bad])

    assert (created.status_code, updated.status_code, imported.status_code) == (
        422,
        422,
        422,
    ), (created.text, updated.text, imported.text)
    stored = t.admin("GET", f"/admin/games/{game_id}/questions").json()
    assert [q["answer_data"] for q in stored] == [valid["answer_data"]]


# ---------------------------------------------------------------------------
# N3 — export / import round trip
# ---------------------------------------------------------------------------


def test_n3_export_import_round_trip(t):
    course = t.course()
    game_id = t.game(course)
    add_questions(t, game_id, NEW_TYPES)

    exported = t.admin("GET", f"/admin/games/{game_id}/export")
    assert exported.status_code == 200
    bundle = exported.json()
    r = t.admin(
        "POST",
        "/admin/games/import",
        files={"file": ("game.json", exported.content, "application/json")},
        data={"course_id": str(course)},
    )
    assert r.status_code == 201, r.text
    t.game_ids.append(r.json()["game_id"])

    fields = ("type", "grading_type", "prompt", "config", "answer_data", "points_value")
    original = t.admin("GET", f"/admin/games/{game_id}/questions").json()
    copied = t.admin("GET", f"/admin/games/{r.json()['game_id']}/questions").json()
    assert [{f: q[f] for f in fields} for q in copied] == [
        {f: q[f] for f in fields} for q in original
    ]
    assert len(bundle["questions"]) == len(NEW_TYPES)


# ---------------------------------------------------------------------------
# N4, N5, N8 — a live pin_drop question
# ---------------------------------------------------------------------------


async def test_n4_n5_n8_pin_drop_live(t, base_url):
    leaky = _with(PIN, config__target={"x": 2, "y": 0})  # author's stray key
    async with LiveGame(t, base_url, [leaky], players=3) as game:
        host_q, player_qs = await game.next_question()

        # N8: no answer in the question payload, even with a stray config key
        for payload in (host_q, *player_qs):
            assert payload["config"] == {"grid": GRID, "snap": True}
            _no_answer_in(payload)
        late = TestSocketClient(base_url, game.guest_token(), "late")
        game.players.append(late)
        await game.join(late, "PLAYER")
        late_q = await late.wait_for("new_question", EVENT_TIMEOUT)
        assert late_q["config"] == {"grid": GRID, "snap": True}
        _no_answer_in(late_q)

        # N4: malformed answers are rejected and not counted
        qid = host_q["questionId"]
        for bad in (
            {"point": {"x": 9, "y": 0}},
            {"point": {"x": float("nan"), "y": 0}},
            {"point": {"x": True, "y": 0}},
            {"point": {"x": "2", "y": 0}},
            {"value": 2},
        ):
            event, payload = await game.answer(0, qid, bad)
            assert event == "error", (bad, payload)

        # Exact, partial (d = 2.5: 10 × 1.5/3), miss; the late player doesn't answer
        expected = [10, 5, 0]
        pins = [{"x": 2, "y": 0}, {"x": 2, "y": 2.5}, {"x": -5, "y": 5}]
        for i, pin in enumerate(pins):
            event, ack = await game.answer(i, qid, {"point": pin})
            assert event == "answer_received", ack
            assert ack["pointsAwarded"] == expected[i]
            assert ack["isCorrect"] is (i == 0)

        # N5: the host gets every submitted pin, players their own reveal
        host_r, player_rs = await game.results()
        assert host_r["totalAnswered"] == 3
        key = lambda p: (p["x"], p["y"])  # noqa: E731
        assert sorted(host_r["answerValues"], key=key) == sorted(pins, key=key)
        reveal = {
            "type": "pin_drop",
            "target": {"x": 2, "y": 0},
            "fullRadius": 1,
            "zeroRadius": 4,
        }
        assert host_r["answerReveal"] == reveal
        for r, points in zip(player_rs, expected + [0]):
            assert r["answerReveal"] == reveal
            assert r["yourPoints"] == points
            assert "answerValues" not in r

        # N6: game-over summaries
        host_over, player_overs = await game.finish()
        [summary] = host_over["questionSummary"]
        assert sorted(summary["values"], key=key) == sorted(pins, key=key)
        assert summary["correctCount"] == 1
        for i, over in enumerate(player_overs[:3]):
            [mine] = over["questionSummary"]
            assert mine["playerAnswer"] == {"point": pins[i]}
            assert mine["answerReveal"] == reveal
            assert mine["pointsAwarded"] == expected[i]


# ---------------------------------------------------------------------------
# N4, N5, N6 — live estimate questions (absolute, relative, completeness)
# ---------------------------------------------------------------------------


async def test_n4_n5_n6_estimate_live(t, base_url):
    questions = [EST_ABS, EST_REL, EST_COMPLETE]
    # answers[player][question]
    answers = [
        [2005.0, 8849 * 1.1, 1],  # 2005.0 counts as whole; 10% off → 10 × 15/20
        [2009, 8849 * 1.15, 1],  # 4 years off → 10 × 6/9; 15% off → 10 × 10/20
    ]
    expected = [[10, 7.5, 10], [6.67, 5, 10]]
    async with LiveGame(t, base_url, questions, players=2) as game:
        for q_idx, question in enumerate(questions):
            host_q, player_qs = await game.next_question()
            qid = host_q["questionId"]
            for payload in (host_q, *player_qs):
                _no_answer_in(payload)
            assert host_q["config"] == {
                "unit": question["config"]["unit"],
                "integer": question["config"].get("integer", False),
            }

            if q_idx == 0:  # N4 on the whole-number question
                for bad in ({"value": 2005.5}, {"value": "2005"}, {"value": None}):
                    event, payload = await game.answer(0, qid, bad)
                    assert event == "error", (bad, payload)

            for p in range(2):
                event, ack = await game.answer(p, qid, {"value": answers[p][q_idx]})
                assert event == "answer_received", ack
                assert ack["pointsAwarded"] == pytest.approx(expected[p][q_idx])

            # approx: MySQL's JSON column drops the last bits of a double
            # (9733.900000000001 comes back as 9733.9). Scores are computed first.
            host_r, player_rs = await game.results()
            assert sorted(host_r["answerValues"]) == pytest.approx(
                sorted([answers[0][q_idx], answers[1][q_idx]])
            )
            if question["grading_type"] == "COMPLETENESS":
                assert host_r["answerReveal"] == {"type": "completeness"}
            else:
                assert host_r["answerReveal"] == {
                    "type": "estimate",
                    "answer": question["answer_data"]["answer"],
                    "unit": question["config"]["unit"],
                    "tolerance": question["answer_data"]["tolerance"],
                }

        host_over, player_overs = await game.finish()
        for q_idx, summary in enumerate(host_over["questionSummary"]):
            assert sorted(summary["values"]) == pytest.approx(
                sorted([answers[0][q_idx], answers[1][q_idx]])
            )
        for p, over in enumerate(player_overs):
            for q_idx, mine in enumerate(over["questionSummary"]):
                assert mine["playerAnswer"]["value"] == pytest.approx(answers[p][q_idx])
                assert mine["pointsAwarded"] == pytest.approx(expected[p][q_idx])


# ---------------------------------------------------------------------------
# N7 — HTML report
# ---------------------------------------------------------------------------


async def test_n7_report_shows_multi_select_answer(t, base_url):
    """Regression: the report's own reveal copy had no multi_select branch (§1)."""
    session, _ = await play(
        t,
        base_url,
        [MULTI_SELECT],
        [[{"selectedIndices": [0, 1]}], [{"selectedIndices": [2]}]],
    )

    report = t.admin("GET", f"/host/sessions/{session}/report")

    assert report.status_code == 200, report.text
    html = report.text
    assert "Multi-Select" in html
    marks = html.count("Correct</span>")
    assert marks == 2, "Two and Three earn points, Four doesn't"
    for option in ("A Two", "B Three", "C Four"):
        assert option in html


async def test_n7_report_renders_new_types(t, base_url):
    unsafe = _with(EST_ABS, config__unit="<b>yr</b>")
    session, _ = await play(
        t,
        base_url,
        [PIN, unsafe],
        [
            [{"point": {"x": 2, "y": 0}}, {"value": 2004}],
            [{"point": {"x": -3, "y": 4}}, {"value": 2012}],
        ],
    )

    html = t.admin("GET", f"/host/sessions/{session}/report").text

    assert "Pin It" in html and "Estimate" in html
    assert 'aria-label="Pin plot"' in html
    assert "2 pins · 1 within full credit · 1 earned points · target (2, 0)" in html
    assert 'aria-label="Number line of guesses"' in html
    assert "Closest guess" in html and "2004" in html
    assert "<b>yr</b>" not in html and "&lt;b&gt;yr&lt;/b&gt;" in html
