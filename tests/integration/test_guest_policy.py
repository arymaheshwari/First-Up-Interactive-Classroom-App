"""
T4 guest policy — per-course guest admission and session-bound guest passes.

Scenario ids (G1…G7) match docs/plans/t4-ui-restructuring.md §8.2.
Runs against the live stack, like the rest of tests/integration.
"""

from __future__ import annotations

import pytest

from .engine.socket_client import TestSocketClient
from .helpers import Tracker, tag, try_join


@pytest.fixture
def t(docker_stack, base_url, admin_token):
    tracker = Tracker(base_url, admin_token)
    yield tracker
    tracker.cleanup()


def _room(t: Tracker, guest_policy: str) -> tuple[int, str]:
    course = t.course(guest_policy)
    game_id = t.game(course)
    t.question(game_id)
    return course, t.room(game_id)


def test_g1_roster_only_rejects_unknown_email(t):
    _, room = _room(t, "ROSTER_ONLY")

    r = t.guest(room, email=f"stranger.{tag()}@example.com")

    assert r.status_code == 403
    assert "roster" in r.json()["message"]


async def test_g2_roster_only_admits_roster_email_under_roster_name(t, base_url):
    course, room = _room(t, "ROSTER_ONLY")
    email = f"Roster.Student.{tag()}@Example.com"
    t.roster_rows(
        course,
        [{"netid": f"rs_{tag()}", "full_name": "Roster Student", "email": email}],
    )
    host = TestSocketClient(base_url, t.admin_token, "host")
    await host.connect()
    try:
        await host.emit("join_room", {"room_code": room, "role": "HOST"})
        await host.wait_for("sync_state")

        r = t.guest(room, email=email.lower())
        assert r.status_code == 200, r.text
        event, _ = await try_join(base_url, r.json()["access_token"], room)
        assert event == "sync_state"

        joined = await host.wait_for("player_joined")
        assert joined["displayName"] == "Roster Student"
    finally:
        await host.disconnect()


def test_g3_roster_only_rejects_inactive_roster_entry(t):
    course, room = _room(t, "ROSTER_ONLY")
    email = f"dropped.{tag()}@example.com"
    t.roster_rows(
        course, [{"netid": f"dr_{tag()}", "full_name": "Dropped", "email": email}]
    )
    entry = t.admin("GET", f"/admin/courses/{course}/roster").json()[0]
    r = t.admin(
        "PATCH",
        f"/admin/courses/{course}/roster/{entry['id']}",
        json={"is_active": False},
    )
    assert r.status_code == 200

    assert t.guest(room, email=email).status_code == 403


def test_g4_disabled_course_rejects_all_guests(t):
    _, room = _room(t, "DISABLED")

    r = t.guest(room)

    assert r.status_code == 403
    assert "not allowed" in r.json()["message"]


async def test_g5_open_course_admits_any_guest(t, base_url):
    _, room = _room(t, "OPEN")

    r = t.guest(room)

    assert r.status_code == 200
    event, _ = await try_join(base_url, r.json()["access_token"], room)
    assert event == "sync_state"


async def test_g6_guest_pass_only_works_for_its_own_room(t, base_url):
    _, room_x = _room(t, "OPEN")
    _, room_y = _room(t, "OPEN")
    r = t.guest(room_x)
    assert r.status_code == 200

    event, payload = await try_join(base_url, r.json()["access_token"], room_y)

    assert event == "error"
    assert "different room" in str(payload)


def test_g7_new_courses_default_to_roster_only(t):
    r = t.admin(
        "POST", "/admin/courses", json={"name": f"T4 {tag()}", "semester": "Test"}
    )

    assert r.status_code == 201
    assert r.json()["guest_policy"] == "ROSTER_ONLY"
