"""
T4 host management — access control, course scoping, rosters, questions, downloads.

Scenario ids (H1…H17) match docs/plans/t4-ui-restructuring.md §8.1.
Runs against the live stack, like the rest of tests/integration.
"""

from __future__ import annotations

import csv
import io
import json
import pathlib

import pytest

from .engine.orchestrator import run_game
from .helpers import ONE_QUESTION_SCENARIO, Tracker, try_join

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


@pytest.fixture
def t(docker_stack, base_url, admin_token):
    tracker = Tracker(base_url, admin_token)
    yield tracker
    tracker.cleanup()


# ---------------------------------------------------------------------------
# Course scoping and the layered access rule (D1/D2)
# ---------------------------------------------------------------------------


def test_h1_host_creates_game_in_own_course(t):
    course = t.course()
    _, host = t.host(course)

    game_id = t.game(course, token=host, prefix="/host")

    r = t.call("GET", f"/host/games/{game_id}", host)
    assert r.status_code == 200
    assert r.json()["course_id"] == course
    mine = t.call("GET", "/game/my-games", host).json()
    assert [g["id"] for g in mine] == [game_id], "creator should be auto-granted"
    listed = t.call("GET", f"/host/courses/{course}/games", host).json()
    assert [g["id"] for g in listed] == [game_id]


def test_h2_host_cannot_create_game_in_course_they_do_not_host(t):
    hosted, other = t.course(), t.course()
    _, host = t.host(hosted)

    r = t.call("POST", "/host/games", host, json={"course_id": other, "title": "x"})

    assert r.status_code == 403
    assert t.call("GET", "/game/my-games", host).json() == []


def test_h3_host_cannot_touch_another_courses_game(t):
    course_a, course_b = t.course(), t.course()
    _, host_a = t.host(course_a)
    game_b = t.game(course_b)

    assert t.call("GET", f"/host/games/{game_b}", host_a).status_code == 403
    assert (
        t.call(
            "PUT", f"/host/games/{game_b}", host_a, json={"title": "hijack"}
        ).status_code
        == 403
    )
    assert t.call("DELETE", f"/host/games/{game_b}", host_a).status_code == 403
    assert t.admin("GET", f"/admin/games/{game_b}").json()["title"] != "hijack"


def test_h4_second_host_needs_a_grant(t):
    course = t.course()
    _, owner = t.host(course)
    game_id = t.game(course, token=owner, prefix="/host")
    colleague_id, colleague = t.host(course)

    assert t.call("GET", f"/host/games/{game_id}", colleague).status_code == 403

    r = t.admin(
        "POST", f"/admin/users/{colleague_id}/game-access", json={"game_id": game_id}
    )
    assert r.status_code == 204
    assert t.call("GET", f"/host/games/{game_id}", colleague).status_code == 200


def test_h5_game_grant_requires_host_role_in_games_course(t):
    course = t.course()
    game_id = t.game(course)
    user_id, _ = t.user()

    r = t.admin(
        "POST", f"/admin/users/{user_id}/game-access", json={"game_id": game_id}
    )
    assert r.status_code == 400
    assert "HOST" in r.json()["message"]

    t.grant_course(user_id, course, "HOST")
    r = t.admin(
        "POST", f"/admin/users/{user_id}/game-access", json={"game_id": game_id}
    )
    assert r.status_code == 204


def test_h6_losing_host_role_revokes_game_access(t):
    course = t.course()
    host_id, host = t.host(course)
    game_id = t.game(course, token=host, prefix="/host")
    assert t.call("GET", f"/host/games/{game_id}", host).status_code == 200

    r = t.admin("DELETE", f"/admin/users/{host_id}/course-access/{course}")
    assert r.status_code == 204

    assert t.call("GET", f"/host/games/{game_id}", host).status_code == 403
    assert t.call("GET", "/game/my-games", host).json() == []


def test_h7_admin_passes_every_host_check(t):
    course = t.course()
    game_id = t.game(course, token=t.admin_token, prefix="/host")
    t.question(game_id, prefix="/host")

    for path in (
        f"/host/courses/{course}/roster",
        f"/host/courses/{course}/games",
        f"/host/games/{game_id}",
        f"/host/games/{game_id}/questions",
        f"/host/games/{game_id}/export",
        f"/host/sessions?course_id={course}",
    ):
        assert t.admin("GET", path).status_code == 200, path


def test_h8_room_course_comes_from_the_game(t):
    course, other = t.course(), t.course()
    game_id = t.game(course)
    t.question(game_id)

    r = t.admin("POST", "/game/rooms", json={"game_id": game_id, "course_id": other})
    assert r.status_code == 400

    room = t.room(game_id)
    assert t.admin("GET", f"/game/rooms/{room}").json()["course_id"] == course


async def test_h9_players_from_other_courses_cannot_join(t, base_url):
    course_a, course_b = t.course(), t.course()
    game_id = t.game(course_a)
    t.question(game_id)
    room = t.room(game_id)
    outsider_id, outsider = t.user()
    t.grant_course(outsider_id, course_b, "PLAYER")
    member_id, member = t.user()
    t.grant_course(member_id, course_a, "PLAYER")

    event, _ = await try_join(base_url, outsider, room)
    assert event == "error"
    event, _ = await try_join(base_url, member, room)
    assert event == "sync_state"


def test_h10_admin_game_creation_requires_an_existing_course(t):
    r = t.admin("POST", "/admin/games", json={"title": "no course"})
    assert r.status_code == 422
    r = t.admin("POST", "/admin/games", json={"title": "ghost", "course_id": 999999999})
    assert r.status_code == 404


def test_h11_course_cannot_be_changed_after_creation(t):
    course, other = t.course(), t.course()
    _, host = t.host(course)
    game_id = t.game(course, token=host, prefix="/host")

    r = t.call("PUT", f"/host/games/{game_id}", host, json={"course_id": other})

    assert r.status_code == 422
    assert t.call("GET", f"/host/games/{game_id}", host).json()["course_id"] == course


# ---------------------------------------------------------------------------
# Roster management
# ---------------------------------------------------------------------------


def test_h12_host_manages_roster_of_hosted_course_only(t):
    course, other = t.course(), t.course()
    _, host = t.host(course)
    _, other_host = t.host(other)
    csv_bytes = (
        _REPO_ROOT / "sample_rosters/sample_roster_from_gradebook.csv"
    ).read_bytes()

    r = t.call(
        "POST",
        f"/host/courses/{course}/roster",
        host,
        files={"file": ("roster.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200, r.text
    imported = r.json()["imported"]
    assert imported > 0
    roster = t.call("GET", f"/host/courses/{course}/roster", host).json()
    assert len(roster) == imported

    entry = roster[0]
    r = t.call(
        "PATCH",
        f"/host/courses/{course}/roster/{entry['id']}",
        host,
        json={"is_active": False},
    )
    assert r.status_code == 200
    roster = t.call("GET", f"/host/courses/{course}/roster", host).json()
    assert next(e for e in roster if e["id"] == entry["id"])["is_active"] is False

    row = {"netid": "zz_other", "full_name": "Other", "email": "zz@example.com"}
    assert (
        t.call("GET", f"/host/courses/{course}/roster", other_host).status_code == 403
    )
    assert (
        t.call(
            "POST",
            f"/host/courses/{course}/roster",
            other_host,
            files={"file": ("roster.csv", csv_bytes, "text/csv")},
        ).status_code
        == 403
    )
    assert (
        t.call(
            "POST",
            f"/host/courses/{course}/roster/import",
            other_host,
            json={"rows": [row]},
        ).status_code
        == 403
    )
    assert (
        t.call(
            "PATCH",
            f"/host/courses/{course}/roster/{entry['id']}",
            other_host,
            json={"is_active": True},
        ).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# Question authoring and import
# ---------------------------------------------------------------------------


def test_h13_host_authors_and_reorders_questions(t):
    course = t.course()
    _, host = t.host(course)
    game_id = t.game(course, token=host, prefix="/host")
    q_ids = [t.question(game_id, token=host, prefix="/host") for _ in range(3)]

    r = t.call(
        "POST",
        f"/host/games/{game_id}/questions/reorder",
        host,
        json={"order": list(reversed(q_ids))},
    )
    assert r.status_code == 204
    listed = t.call("GET", f"/host/games/{game_id}/questions", host).json()
    assert [q["id"] for q in listed] == list(reversed(q_ids))

    r = t.call(
        "PUT",
        f"/host/games/{game_id}/questions/{q_ids[0]}",
        host,
        json={"config": {"options": ["only one"]}},
    )
    assert r.status_code == 422
    r = t.call(
        "PUT",
        f"/host/games/{game_id}/questions/{q_ids[0]}",
        host,
        json={"prompt": "Renamed?"},
    )
    assert r.status_code == 200 and r.json()["prompt"] == "Renamed?"

    assert (
        t.call(
            "DELETE", f"/host/games/{game_id}/questions/{q_ids[1]}", host
        ).status_code
        == 204
    )
    remaining = [
        q["id"] for q in t.call("GET", f"/host/games/{game_id}/questions", host).json()
    ]
    assert q_ids[1] not in remaining and len(remaining) == 2


def test_h14_host_imports_unmodified_v1_game_file(t):
    course = t.course()
    _, host = t.host(course)
    path = _REPO_ROOT / "sample_games/data_structures.json"
    bundle = json.loads(path.read_text(encoding="utf-8"))
    assert bundle["version"] == 1 and "course_id" not in bundle["game"]

    r = t.call(
        "POST",
        "/host/games/import",
        host,
        files={"file": (path.name, path.read_bytes(), "application/json")},
        data={"course_id": str(course)},
    )
    assert r.status_code == 201, r.text
    game_id = r.json()["game_id"]
    t.game_ids.append(game_id)
    assert t.call("GET", f"/host/games/{game_id}", host).json()["course_id"] == course
    questions = t.call("GET", f"/host/games/{game_id}/questions", host).json()
    assert len(questions) == len(bundle["questions"])

    r = t.call(
        "POST",
        "/host/games/import",
        host,
        files={"file": (path.name, path.read_bytes(), "application/json")},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Sessions and downloads (D9)
# ---------------------------------------------------------------------------


async def test_h15_downloads_for_completed_sessions(t, base_url):
    course, other = t.course(), t.course()
    host_id, host = t.host(course)
    _, other_host = t.host(other)
    game_id = t.game(course)
    t.question(game_id)
    t.admin("POST", f"/admin/users/{host_id}/game-access", json={"game_id": game_id})
    title = t.admin("GET", f"/admin/games/{game_id}").json()["title"]

    lobby_room = t.room(game_id)
    lobby_session = t.session_id(lobby_room)
    r = t.call("GET", f"/host/sessions/{lobby_session}/report", host)
    assert r.status_code == 409

    room = t.room(game_id)
    guest = t.guest(room)
    assert guest.status_code == 200, guest.text
    await run_game(
        base_url=base_url,
        host_token=t.admin_token,
        player_tokens=[guest.json()["access_token"]],
        room_code=room,
        scenario=ONE_QUESTION_SCENARIO,
    )
    session = t.session_id(room)

    report = t.call("GET", f"/host/sessions/{session}/report", host)
    assert report.status_code == 200
    assert report.headers["content-type"].startswith("text/html")
    assert title in report.text

    export = t.call("GET", f"/host/sessions/{session}/export?format=raw", host)
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(export.text)))
    assert len(rows) == 2, "header + one row for the single player"

    assert (
        t.call("GET", f"/host/sessions/{session}/report", other_host).status_code == 403
    )
    assert (
        t.call("GET", f"/host/sessions/{session}/export", other_host).status_code == 403
    )


def test_h16_session_list_is_scoped(t):
    course_a, course_b = t.course(), t.course()
    host_id, host = t.host(course_a)
    game_a, game_b = t.game(course_a), t.game(course_b)
    for g in (game_a, game_b):
        t.question(g)
    t.admin("POST", f"/admin/users/{host_id}/game-access", json={"game_id": game_a})
    session_a = t.session_id(t.room(game_a))
    session_b = t.session_id(t.room(game_b))

    listed = t.admin("GET", f"/host/sessions?course_id={course_a}").json()
    ids = {s["session_id"] for s in listed}
    assert session_a in ids and session_b not in ids
    assert all(s["course_id"] == course_a for s in listed)

    mine = {s["session_id"] for s in t.call("GET", "/host/sessions", host).json()}
    assert session_a in mine and session_b not in mine


def test_h17_live_game_delete_blocked_for_host_forced_for_admin(t):
    course = t.course()
    _, host = t.host(course)
    game_id = t.game(course, token=host, prefix="/host")
    t.question(game_id, token=host, prefix="/host")
    room = t.room(game_id, token=host)
    assert t.call("GET", f"/game/rooms/{room}/ping").status_code == 200

    assert t.call("DELETE", f"/host/games/{game_id}", host).status_code == 409

    assert t.admin("DELETE", f"/admin/games/{game_id}").status_code == 204
    assert t.call("GET", f"/game/rooms/{room}/ping").status_code == 404, (
        "admin delete must clear the room from Redis too"
    )


# ---------------------------------------------------------------------------
# Added after the mean review (spec §8.1 H18-H19)
# ---------------------------------------------------------------------------


def test_h18_roster_upload_deactivates_omitted_students(t):
    course = t.course()
    _, host = t.host(course)
    roster_url = f"/host/courses/{course}/roster"
    full = (_REPO_ROOT / "sample_rosters/sample_roster_from_gradebook.csv").read_text(
        encoding="utf-8"
    )
    students = [
        row
        for row in csv.DictReader(io.StringIO(full))
        if "@" in (row.get("SIS Login ID") or "")
    ]
    dropped = students[-1]["SIS Login ID"]
    reduced = "\n".join(line for line in full.splitlines() if dropped not in line)

    def upload(text: str):
        r = t.call(
            "POST",
            roster_url,
            host,
            files={"file": ("roster.csv", text.encode(), "text/csv")},
        )
        assert r.status_code == 200, r.text
        return r.json()

    assert upload(full)["imported"] == len(students)
    assert upload(reduced)["deactivated"] == 1
    roster = t.call("GET", roster_url, host).json()
    inactive = [e["netid"] for e in roster if not e["is_active"]]
    assert inactive == [dropped.split("@")[0].lower()]

    upload(full)
    assert all(e["is_active"] for e in t.call("GET", roster_url, host).json())

    # Same rule through the mapped-rows import the Host UI's wizard uses.
    rows = [
        {
            "netid": f"m1_{course}",
            "full_name": "Kept",
            "email": f"kept{course}@example.com",
        },
        {
            "netid": f"m2_{course}",
            "full_name": "Dropped",
            "email": f"drop{course}@example.com",
        },
    ]
    import_url = f"{roster_url}/import"
    assert t.call("POST", import_url, host, json={"rows": rows}).status_code == 200
    r = t.call("POST", import_url, host, json={"rows": rows[:1]})
    assert r.status_code == 200 and r.json()["deactivated"] >= 1
    by_netid = {
        e["netid"]: e["is_active"] for e in t.call("GET", roster_url, host).json()
    }
    assert by_netid[f"m1_{course}"] is True and by_netid[f"m2_{course}"] is False


def test_h19_can_delete_flag_matches_delete_rule(t):
    course = t.course()
    _, host = t.host(course)
    game_id = t.game(course, token=host, prefix="/host")
    t.question(game_id, token=host, prefix="/host")
    mine = t.session_id(t.room(game_id, token=host))
    admins = t.session_id(t.room(game_id))

    flags = {
        s["session_id"]: s["can_delete"]
        for s in t.call("GET", f"/host/sessions?course_id={course}", host).json()
    }
    assert flags == {mine: True, admins: False}
    admin_flags = {
        s["session_id"]: s["can_delete"]
        for s in t.admin("GET", f"/host/sessions?course_id={course}").json()
    }
    assert admin_flags[mine] is True and admin_flags[admins] is True

    assert t.call("DELETE", f"/game/sessions/{admins}", host).status_code == 403
    assert t.call("DELETE", f"/game/sessions/{mine}", host).status_code == 204


async def test_h20_former_host_loses_access_to_past_sessions(t, base_url):
    course = t.course()
    host_id, host = t.host(course)
    game_id = t.game(course, token=host, prefix="/host")
    t.question(game_id, token=host, prefix="/host")
    room = t.room(game_id, token=host)
    guest = t.guest(room)
    assert guest.status_code == 200, guest.text
    await run_game(
        base_url=base_url,
        host_token=host,
        player_tokens=[guest.json()["access_token"]],
        room_code=room,
        scenario=ONE_QUESTION_SCENARIO,
    )
    session = t.session_id(room)
    reads = [
        f"/host/sessions/{session}/report",
        f"/host/sessions/{session}/export?format=raw",
        f"/game/sessions/{session}/export",
        f"/game/sessions/{session}/guests",
    ]

    for path in reads:
        assert t.call("GET", path, host).status_code == 200, path
    assert session in {
        s["session_id"] for s in t.call("GET", "/host/sessions", host).json()
    }

    r = t.admin("DELETE", f"/admin/users/{host_id}/course-access/{course}")
    assert r.status_code == 204

    for path in reads:
        assert t.call("GET", path, host).status_code == 403, path
    assert session not in {
        s["session_id"] for s in t.call("GET", "/host/sessions", host).json()
    }
    assert t.call("DELETE", f"/game/sessions/{session}", host).status_code == 403
    assert t.admin("GET", f"/host/sessions/{session}/report").status_code == 200
