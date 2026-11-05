"""
HTTP/socket helpers for the T4 host-management and guest-policy tests.

Kept separate from conftest.py so the pre-existing fixtures stay untouched.
Everything created through a `Tracker` is removed by the `tracker` fixture:
games first (the admin delete also clears their rooms from Redis, so the
MAX_ROOMS limit isn't exhausted across runs), then users. Courses have no
delete endpoint and are left behind, as in the existing suite.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import httpx

from .engine.scoring import GameScenario, PlayerScript, QuestionSpec
from .engine.socket_client import TestSocketClient

# Docker Desktop on Windows occasionally stalls one request past 10s; a real hang
# still fails, just later.
TIMEOUT = 30.0

MC_QUESTION = {
    "type": "multiple_choice",
    "grading_type": "ACCURACY",
    "prompt": "Which planet is closest to the Sun?",
    "config": {"options": ["Venus", "Mercury", "Mars"]},
    "answer_data": {"answer_points": [0, 1, 0]},
    "points_value": 1,
    "time_limit_seconds": 30,
}

ONE_QUESTION_SCENARIO = GameScenario(
    name="one_question",
    questions=[
        QuestionSpec(
            type=MC_QUESTION["type"],
            grading_type=MC_QUESTION["grading_type"],
            prompt=MC_QUESTION["prompt"],
            config=MC_QUESTION["config"],
            answer_data=MC_QUESTION["answer_data"],
            points_value=1,
        )
    ],
    player_scripts=[PlayerScript(responses=[{"selectedIndex": 1}])],
)


def tag() -> str:
    return uuid.uuid4().hex[:8]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass
class Tracker:
    base_url: str
    admin_token: str
    game_ids: list[int] = field(default_factory=list)
    user_ids: list[str] = field(default_factory=list)

    # ── raw request ──────────────────────────────────────────────────────────
    def call(self, method: str, path: str, token: str | None = None, **kw):
        headers = bearer(token) if token else {}
        return httpx.request(
            method, f"{self.base_url}/api{path}", headers=headers, timeout=TIMEOUT, **kw
        )

    def admin(self, method: str, path: str, **kw):
        return self.call(method, path, self.admin_token, **kw)

    # ── setup builders (assert on success so failures point at setup) ───────
    def course(self, guest_policy: str = "OPEN") -> int:
        r = self.admin(
            "POST",
            "/admin/courses",
            json={
                "name": f"T4 {tag()}",
                "semester": "Test",
                "guest_policy": guest_policy,
            },
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def user(self) -> tuple[str, str]:
        """Create a local USER account; return (user_id, access_token)."""
        name, password = f"t4_{tag()}", f"Pw-{tag()}-x"
        r = self.admin(
            "POST",
            "/admin/users",
            json={"username": name, "display_name": name, "password": password},
        )
        assert r.status_code == 201, r.text
        user_id = r.json()["id"]
        self.user_ids.append(user_id)
        r = self.call(
            "POST", "/auth/login", json={"username": name, "password": password}
        )
        assert r.status_code == 200, r.text
        return user_id, r.json()["access_token"]

    def grant_course(self, user_id: str, course_id: int, role: str = "HOST") -> None:
        r = self.admin(
            "POST",
            f"/admin/users/{user_id}/course-access",
            json={"course_id": course_id, "role": role},
        )
        assert r.status_code == 204, r.text

    def host(self, course_id: int) -> tuple[str, str]:
        user_id, token = self.user()
        self.grant_course(user_id, course_id, "HOST")
        return user_id, token

    def game(
        self, course_id: int, token: str | None = None, prefix: str = "/admin"
    ) -> int:
        """Create a game (as admin by default, or as `token` via /host)."""
        r = self.call(
            "POST",
            f"{prefix}/games",
            token or self.admin_token,
            json={"course_id": course_id, "title": f"T4 Game {tag()}"},
        )
        assert r.status_code == 201, r.text
        game_id = r.json()["id"]
        self.game_ids.append(game_id)
        return game_id

    def question(
        self, game_id: int, token: str | None = None, prefix: str = "/admin"
    ) -> int:
        r = self.call(
            "POST",
            f"{prefix}/games/{game_id}/questions",
            token or self.admin_token,
            json=MC_QUESTION,
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def room(self, game_id: int, token: str | None = None) -> str:
        r = self.call(
            "POST", "/game/rooms", token or self.admin_token, json={"game_id": game_id}
        )
        assert r.status_code == 201, r.text
        return r.json()["room_code"]

    def session_id(self, room_code: str) -> str:
        r = self.admin("GET", f"/game/rooms/{room_code}")
        assert r.status_code == 200, r.text
        return r.json()["session_id"]

    def guest(self, room_code: str, email: str | None = None) -> httpx.Response:
        return self.call(
            "POST",
            "/auth/guest",
            json={
                "display_name": f"Guest {tag()}",
                "email": email or f"guest.{tag()}@example.com",
                "room_code": room_code,
            },
        )

    def roster_rows(self, course_id: int, rows: list[dict]) -> None:
        r = self.admin(
            "POST", f"/admin/courses/{course_id}/roster/import", json={"rows": rows}
        )
        assert r.status_code == 200, r.text

    # ── teardown ─────────────────────────────────────────────────────────────
    def cleanup(self) -> None:
        for game_id in self.game_ids:
            self.admin("DELETE", f"/admin/games/{game_id}")
        for user_id in self.user_ids:
            self.admin("DELETE", f"/admin/users/{user_id}")


async def try_join(base_url: str, token: str, room_code: str) -> tuple[str, dict]:
    """Join a room as PLAYER; return ("sync_state"|"error", payload)."""
    import asyncio

    client = TestSocketClient(base_url, token, "joiner")
    await client.connect()
    try:
        await client.emit("join_room", {"room_code": room_code, "role": "PLAYER"})
        waits = {
            asyncio.create_task(client.wait_for(ev, 10.0)): ev
            for ev in ("sync_state", "error")
        }
        done, pending = await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        task = done.pop()
        return waits[task], task.result()
    finally:
        await client.disconnect()
