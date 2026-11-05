#!/usr/bin/env python3
"""
Capture the UI screenshots for docs/ui/.

Runs against the dev stack: the backend on :8000 and the Vite dev servers for the host
(5173), player (5174) and admin (5175) apps. It creates fixture data through the API
(one reusable "UI capture" course, six short games, generated images), plays the games
with the host UI, one player page and two socket players, captures each named screen,
and deletes what it created (courses and rosters can't be deleted, so the course is
reused across runs).

Every screen is reached once; for a themed run the theme is switched in place and the
screen is captured once per theme, so a full run plays each game once.

Usage:
  pip install -r scripts/requirements-ui.txt && playwright install chromium
  python scripts/capture_ui_screenshots.py                       # docs/ui/after/{light,dark}/
  python scripts/capture_ui_screenshots.py --only host-lobby,player-lobby
  python scripts/capture_ui_screenshots.py --legacy --out docs/ui/before --only <names>

Selectors use roles, visible text and routes only (never classes), because every class
changes between the "before" and "after" UI.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import time
import uuid
from contextlib import suppress
from pathlib import Path

import httpx
import socketio
from PIL import Image, ImageDraw
from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
API = "http://localhost:8000/api"
BACKEND = "http://localhost:8000"
HOST_APP, PLAYER_APP, ADMIN_APP = (
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
)
COURSE_NAME = "UI capture"
UI_HOST_USERNAME = "ui_capture_host"
TIMEOUT = 15_000

NAMES = [
    # the 21 committed "before" names
    "admin-users",
    "host-gameover",
    "host-home",
    "host-lobby",
    "host-login",
    "host-manage-games",
    "host-question-editor",
    "host-question-fitb",
    "host-question-mc-participation",
    "host-question-mc",
    "host-question-tf",
    "host-results-fitb-wordcloud",
    "host-results-mc",
    "host-results-tf",
    "player-feedback",
    "player-gameover",
    "player-join",
    "player-lobby",
    "player-name",
    "player-question-mc",
    "player-results",
    # 23 more
    "admin-courses",
    "admin-user-detail",
    "admin-guests",
    "admin-login",
    "host-manage-rosters",
    "host-manage-sessions",
    "host-manage-images",
    "host-question-editor-images",
    "host-question-pin-image",
    "host-question-estimate",
    "host-results-pin",
    "host-results-estimate",
    "player-question-pin",
    "player-question-estimate",
    "player-question-image-options",
    "player-results-pin",
    "host-question-pin-grid",
    "host-question-multiselect",
    "player-question-multiselect",
    "host-image-picker",
    "host-manage-roster",
    "host-focus",
    "host-question-image-options",
    "host-session-detail",
    "player-login",
    "player-question-tf",
    "player-question-fitb",
    # curated interaction states, captured with the same current UI
    "host-home-quiz-open",
    "host-home-sessions-scroll",
    "host-manage-new-game",
    "player-name-netid",
    "player-name-local",
    "player-login-error",
]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def env() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    )


class Api:
    def __init__(self) -> None:
        e = env()
        r = httpx.post(
            f"{API}/auth/login",
            json={"username": e["ADMIN_USERNAME"], "password": e["ADMIN_PASSWORD"]},
        )
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def call(self, method: str, path: str, **kw) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"}
        return httpx.request(method, API + path, headers=headers, timeout=60, **kw)

    def ok(self, method: str, path: str, **kw):
        r = self.call(method, path, **kw)
        assert r.status_code < 300, f"{method} {path}: {r.status_code} {r.text[:300]}"
        return r.json() if r.content else None

    def delete(self, path: str) -> None:
        """Best-effort cleanup; one retry on a server error (§4.13)."""
        for _ in range(2):
            r = self.call("DELETE", path)
            if r.status_code < 500:
                return
            time.sleep(1)


def guest(api: Api, room: str, name: str) -> tuple[str, str]:
    """(token, user id) for a new guest in `room`."""
    email = f"ui.{uuid.uuid4().hex[:8]}@example.com"
    r = httpx.post(
        f"{API}/auth/guest",
        json={"display_name": name, "email": email, "room_code": room},
        timeout=30,
    )
    r.raise_for_status()
    token = r.json()["access_token"]
    payload = token.split(".")[1]
    sub = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))[
        "sub"
    ]
    return token, sub


def picture(label: str, size: tuple[int, int], colour: str, shape: str) -> bytes:
    """A flat fixture image: one outlined shape and its name (content, not UI colour)."""
    w, h = size
    im = Image.new("RGB", size, colour)
    d = ImageDraw.Draw(im)
    box = (w * 0.3, h * 0.2, w * 0.7, h * 0.8)
    if shape == "circle":
        d.ellipse(box, outline="white", width=10)
    elif shape == "triangle":
        d.polygon(
            [(w * 0.5, h * 0.18), (w * 0.72, h * 0.8), (w * 0.28, h * 0.8)],
            outline="white",
            width=10,
        )
    elif shape == "star":
        cx, cy, r = w * 0.5, h * 0.5, min(w, h) * 0.32
        import math

        pts = [
            (
                cx + (r if i % 2 == 0 else r * 0.45) * math.sin(i * math.pi / 5),
                cy - (r if i % 2 == 0 else r * 0.45) * math.cos(i * math.pi / 5),
            )
            for i in range(10)
        ]
        d.polygon(pts, outline="white", width=10)
    else:
        d.rectangle(box, outline="white", width=10)
    d.text((16, 16), label, fill="white")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures (§4.13)
# ---------------------------------------------------------------------------


def q(type_, prompt, config, answer_data, grading="ACCURACY", points=1000):
    return {
        "type": type_,
        "grading_type": grading,
        "prompt": prompt,
        "config": config,
        "answer_data": answer_data,
        "time_limit_seconds": 300,
        "points_value": points,
    }


class Fixtures:
    def __init__(self, api: Api) -> None:
        self.api = api
        self.games: dict[str, int] = {}
        self.images: dict[str, str] = {}
        self.user_ids: list[str] = []
        courses = api.ok("GET", "/admin/courses")
        found = next((c for c in courses if c["name"] == COURSE_NAME), None)
        if found:
            self.course = found["id"]
            api.ok(
                "PUT", f"/admin/courses/{self.course}", json={"guest_policy": "OPEN"}
            )
        else:
            self.course = api.ok(
                "POST",
                "/admin/courses",
                json={"name": COURSE_NAME, "semester": "Demo", "guest_policy": "OPEN"},
            )["id"]
        rows = [
            {
                "netid": f"student{i}",
                "full_name": name,
                "email": f"student{i}@example.edu",
            }
            for i, name in enumerate(
                [
                    "Ada Lovelace",
                    "Alan Turing",
                    "Grace Hopper",
                    "Edsger Dijkstra",
                    "Barbara Liskov",
                ],
                1,
            )
        ]
        api.ok(
            "POST", f"/host/courses/{self.course}/roster/import", json={"rows": rows}
        )
        users = api.ok("GET", "/admin/users")
        existing = next(
            (u for u in users if u.get("username") == UI_HOST_USERNAME), None
        )
        if existing:
            self.ui_host = existing["id"]
        else:
            self.ui_host = api.ok(
                "POST",
                "/admin/users",
                json={
                    "username": UI_HOST_USERNAME,
                    "display_name": "UI Capture Host",
                    "password": "ui-capture-pass",
                },
            )["id"]
        self.user_ids.append(self.ui_host)
        api.call(
            "POST",
            f"/admin/users/{self.ui_host}/course-access",
            json={"course_id": self.course, "role": "HOST"},
        )

        for key, (size, colour, shape) in {
            "prompt": ((1200, 675), "navy", "square"),
            "circle": ((600, 450), "darkorange", "circle"),
            "triangle": ((600, 450), "seagreen", "triangle"),
            "square": ((600, 450), "steelblue", "square"),
            "star": ((600, 450), "purple", "star"),
            "map": ((1600, 800), "darkolivegreen", "circle"),
        }.items():
            r = api.call(
                "POST",
                f"/host/courses/{self.course}/images",
                files={
                    "file": (
                        f"{key}.png",
                        picture(key, size, colour, shape),
                        "image/png",
                    )
                },
            )
            assert r.status_code in (200, 201), r.text
            self.images[key] = r.json()["id"]

        grid = {"xMin": -5, "xMax": 5, "yMin": -5, "yMax": 5, "step": 1}
        self.questions = {
            "A": [
                q(
                    "multiple_choice",
                    "Which planet is known as the Red Planet?",
                    {"options": ["Mercury", "Venus", "Mars", "Jupiter"]},
                    {"answer_points": [0, 0, 1000, 0]},
                ),
                q(
                    "true_false",
                    "The Pacific is the largest ocean.",
                    {},
                    {"answer_points": {"true": 1000, "false": 0}},
                ),
                q(
                    "fill_in_the_blank",
                    "The chemical symbol for gold is ___",
                    {},
                    {
                        "acceptedAnswers": ["Au"],
                        "answerPoints": [1000],
                        "editDistance": 0,
                    },
                ),
                q(
                    "multiple_choice",
                    "Which season do you like best?",
                    {"options": ["Spring", "Summer", "Autumn", "Winter"]},
                    {},
                    grading="COMPLETENESS",
                ),
            ],
            "B": [
                q(
                    "multi_select",
                    "Which of these are prime?",
                    {"options": ["2", "4", "7", "9"]},
                    {"answer_points": [500, -250, 500, -250]},
                )
            ],
            "C": [
                q(
                    "pin_drop",
                    "Plot the vertex of y = (x − 2)² − 3",
                    {"grid": grid, "snap": True},
                    {"target": {"x": 2, "y": -3}, "fullRadius": 1, "zeroRadius": 3},
                )
            ],
            "D": [
                q(
                    "pin_drop",
                    "Where is the lake?",
                    {"image": {"imageId": self.images["map"]}},
                    {
                        "target": {"x": 0.30, "y": 0.55},
                        "fullRadius": 0.05,
                        "zeroRadius": 0.15,
                    },
                )
            ],
            "E": [
                q(
                    "estimate",
                    "How many bones are in the adult human body?",
                    {"integer": True},
                    {
                        "answer": 206,
                        "tolerance": {"mode": "relative", "full": 5, "zero": 25},
                    },
                )
            ],
            "F": [
                q(
                    "multiple_choice",
                    "Which picture shows a triangle?",
                    {
                        "options": ["Circle", "Triangle", "Square", "Star"],
                        "optionImages": [
                            self.images[k]
                            for k in ("circle", "triangle", "square", "star")
                        ],
                        "promptImageId": self.images["prompt"],
                    },
                    {"answer_points": [0, 1000, 0, 0]},
                )
            ],
        }
        titles = {
            "A": "Classic",
            "B": "Multi-select",
            "C": "Pin It (grid)",
            "D": "Pin It (picture)",
            "E": "Estimate",
            "F": "Picture options",
        }
        for key, questions in self.questions.items():
            gid = api.ok(
                "POST",
                "/admin/games",
                json={
                    "course_id": self.course,
                    "title": f"{titles[key]} ({key})",
                    "description": "UI capture fixture",
                },
            )["id"]
            self.games[key] = gid
            for question in questions:
                api.ok("POST", f"/admin/games/{gid}/questions", json=question)

    def cleanup(self) -> None:
        # Users first: deleting a user right after their game can hit a backend race.
        for uid in self.user_ids:
            self.api.delete(f"/admin/users/{uid}")
        for gid in self.games.values():
            self.api.delete(f"/admin/games/{gid}")
        for iid in self.images.values():
            self.api.delete(f"/host/images/{iid}")


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


class Shooter:
    def __init__(
        self,
        out: Path,
        themes: list[str],
        legacy: bool,
        only: set[str],
        visual_theme: str = "aurora",
    ) -> None:
        self.out, self.themes, self.legacy, self.only = out, themes, legacy, only
        self.visual_theme = visual_theme
        self.taken: list[str] = []

    def wants(self, *names: str) -> bool:
        return any(n in self.only for n in names)

    def __call__(self, page: Page, name: str, full_page: bool = True) -> None:
        assert name in NAMES, name
        if name not in self.only:
            return
        page.wait_for_timeout(400)  # images and fonts settle
        if self.legacy:
            path = self.out / f"{name}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path), full_page=full_page)
        else:
            for theme in self.themes:
                app = (
                    "host"
                    if ":5173" in page.url
                    else "player"
                    if ":5174" in page.url
                    else "admin"
                )
                page.evaluate(
                    "([app, mode, visual]) => { try { localStorage.setItem('buzzer-theme-' + app, mode); localStorage.setItem('buzzer-visual-theme-' + app, visual); } catch (e) {} document.documentElement.dataset.theme = mode; document.documentElement.dataset.visualTheme = visual; window.dispatchEvent(new CustomEvent('buzzer-theme-change')); }",
                    [app, theme, self.visual_theme],
                )
                page.evaluate(
                    "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
                )
                page.wait_for_timeout(250)
                path = self.out / theme / f"{name}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(path), full_page=full_page)
        self.taken.append(name)


class SocketPlayer:
    """A guest answering through the same events as scripts/simulate_players.py."""

    def __init__(self, token: str, room: str) -> None:
        self.questions: list[int] = []
        self.sio = socketio.Client()
        self.sio.on(
            "new_question", lambda data: self.questions.append(data["questionId"])
        )
        self.sio.connect(
            BACKEND,
            auth={"token": token},
            socketio_path="/socket.io",
            headers={"Origin": HOST_APP},
        )
        self.sio.emit("join_room", {"room_code": room, "role": "PLAYER"})

    def answer(self, answer: dict, count: int) -> None:
        end = time.time() + 15
        while len(self.questions) < count and time.time() < end:
            time.sleep(0.1)
        assert len(self.questions) >= count, "socket player never got the question"
        self.sio.emit(
            "submit_answer",
            {
                "question_id": self.questions[count - 1],
                "answer_data": answer,
                "answer_time_ms": 1500,
            },
        )
        time.sleep(0.3)

    def close(self) -> None:
        with suppress(Exception):
            self.sio.disconnect()


def login_page(page: Page, app: str, token: str) -> None:
    page.goto(f"{app}/")
    page.evaluate("t => localStorage.setItem('token', t)", token)


class Run:
    def __init__(
        self, browser, api: Api, fx: Fixtures, shoot: Shooter, theme_start: str
    ) -> None:
        self.api, self.fx, self.shoot = api, fx, shoot
        desk = {"viewport": {"width": 1440, "height": 900}, "color_scheme": theme_start}
        self.host = browser.new_context(**desk).new_page()
        self.admin = browser.new_context(**desk).new_page()
        self.player_ctx = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            has_touch=True,
            color_scheme=theme_start,
        )
        self.player = self.player_ctx.new_page()
        login_page(self.host, HOST_APP, api.token)
        login_page(self.admin, ADMIN_APP, api.token)

    # -- rooms ---------------------------------------------------------------
    def room(self, key: str) -> tuple[str, list[SocketPlayer]]:
        code = self.api.ok("POST", "/game/rooms", json={"game_id": self.fx.games[key]})[
            "room_code"
        ]
        token, uid = guest(self.api, code, "Pat Player")
        self.fx.user_ids.append(uid)
        self.player.goto(f"{PLAYER_APP}/")
        self.player.evaluate("t => localStorage.setItem('token', t)", token)
        self.host.goto(f"{HOST_APP}/game/{code}/lobby")
        self.player.goto(f"{PLAYER_APP}/game/{code}/lobby")
        sockets = []
        for name in ("Sam Socket", "Riley Socket"):
            t, uid = guest(self.api, code, name)
            self.fx.user_ids.append(uid)
            sockets.append(SocketPlayer(t, code))
        expect(self.host.get_by_role("button", name="Start Game")).to_be_enabled(
            timeout=TIMEOUT
        )
        self.host.wait_for_timeout(500)
        return code, sockets

    def click_host(self, name: str) -> None:
        self.host.get_by_role("button", name=name).click()

    # -- flows ---------------------------------------------------------------
    def logged_out(self, code: str) -> None:
        if not self.shoot.wants(
            "admin-login",
            "host-login",
            "player-join",
            "player-name",
            "player-login",
            "player-name-netid",
            "player-name-local",
            "player-login-error",
        ):
            return
        browser = self.host.context.browser
        desk = browser.new_context(viewport={"width": 1440, "height": 900})
        page = desk.new_page()
        page.goto(f"{ADMIN_APP}/login")
        self.shoot(page, "admin-login")
        page.goto(f"{HOST_APP}/login")
        self.shoot(page, "host-login")
        phone = browser.new_context(
            viewport={"width": 390, "height": 844}, device_scale_factor=2
        ).new_page()
        phone.goto(f"{PLAYER_APP}/join")
        self.shoot(phone, "player-join")
        phone.goto(f"{PLAYER_APP}/login?from=oauth2&error=Preview")
        self.shoot(phone, "player-login")
        self.shoot(phone, "player-login-error")
        phone.goto(f"{PLAYER_APP}/name/{code}")
        self.shoot(phone, "player-name")
        if self.shoot.wants("player-name-netid", "player-name-local"):
            phone.get_by_role("button", name="Sign In", exact=True).click()
            self.shoot(phone, "player-name-netid")
            phone.get_by_role("button", name="Use local account instead").click()
            self.shoot(phone, "player-name-local")
        desk.close()
        phone.context.close()

    def manage(self) -> None:
        fx, h = self.fx, self.host

        def example_session(i: int) -> dict[str, str]:
            return {
                "session_id": f"ui-scroll-{i}",
                "room_code": f"DEMO{i:02d}",
                "status": "LOBBY",
                "game_title": f"Review Quiz {i}",
                "course_name": COURSE_NAME,
                "course_semester": "Demo",
            }

        h.route(
            "**/api/game/my-active-sessions",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps([example_session(1)]),
            ),
        )
        h.goto(f"{HOST_APP}/home")
        course = h.locator("#host-home-course")
        expect(course).to_be_visible(timeout=TIMEOUT)
        course.click()
        h.get_by_role("option", name=re.compile(COURSE_NAME)).first.click()
        h.wait_for_timeout(500)
        h.locator("#host-home-quiz").click()
        h.get_by_role("option", name="Classic (A)").click()
        self.shoot(h, "host-home")
        if self.shoot.wants("host-home-quiz-open"):
            h.locator("#host-home-quiz").click()
            self.shoot(h, "host-home-quiz-open", full_page=False)
            h.get_by_role("option", name="Classic (A)").click()
        if self.shoot.wants("host-home-sessions-scroll"):
            sessions = [example_session(i) for i in range(1, 9)]
            h.unroute("**/api/game/my-active-sessions")
            h.route(
                "**/api/game/my-active-sessions",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(sessions),
                ),
            )
            h.reload()
            expect(h.get_by_label("8 active sessions")).to_be_visible(timeout=TIMEOUT)
            self.shoot(h, "host-home-sessions-scroll", full_page=False)
            h.unroute("**/api/game/my-active-sessions")
        h.goto(f"{HOST_APP}/manage/games?course={fx.course}")
        expect(h.get_by_text("Classic (A)")).to_be_visible(timeout=TIMEOUT)
        self.shoot(h, "host-manage-games")
        if self.shoot.wants("host-manage-new-game"):
            h.get_by_role("button", name="New Game").click()
            expect(h.get_by_role("heading", name="Create Game")).to_be_visible(
                timeout=TIMEOUT
            )
            self.shoot(h, "host-manage-new-game")
        h.goto(f"{HOST_APP}/manage/images?course={fx.course}")
        expect(h.get_by_role("button", name="View map.png")).to_be_visible(
            timeout=TIMEOUT
        )
        self.shoot(h, "host-manage-images")
        h.goto(f"{HOST_APP}/manage/rosters")
        expect(h.get_by_text(COURSE_NAME).first).to_be_visible(timeout=TIMEOUT)
        # One row per course the user can host (every course, for the admin token used here),
        # so like the admin lists it is shot at viewport size.
        self.shoot(h, "host-manage-rosters", full_page=False)
        h.goto(f"{HOST_APP}/manage/courses/{fx.course}/roster")
        expect(h.get_by_text("Ada Lovelace")).to_be_visible(timeout=TIMEOUT)
        self.shoot(h, "host-manage-roster")
        h.goto(f"{HOST_APP}/manage/games/{fx.games['A']}/questions")
        expect(h.get_by_text("Which planet is known as the Red Planet?")).to_be_visible(
            timeout=TIMEOUT
        )
        self.shoot(h, "host-question-editor")
        if self.shoot.wants("host-focus"):
            h.get_by_role("button", name="Add Question").click()
            add_image = h.get_by_role("button", name="Add image", exact=True).first
            expect(add_image).to_be_visible()
            for _ in range(60):
                h.keyboard.press("Tab")
                if add_image.evaluate("el => el === document.activeElement"):
                    break
            self.shoot(h, "host-focus", full_page=False)
        h.goto(f"{HOST_APP}/manage/games/{fx.games['F']}/questions")
        expect(h.get_by_text("Which picture shows a triangle?")).to_be_visible(
            timeout=TIMEOUT
        )
        h.get_by_role("button", name="Edit").first.click()
        expect(h.get_by_text("Text / alt text")).to_be_visible(timeout=TIMEOUT)
        self.shoot(h, "host-question-editor-images")
        if self.shoot.wants("host-image-picker"):
            h.get_by_role("button", name="Change").first.click()
            expect(h.get_by_role("dialog")).to_be_visible()
            h.wait_for_timeout(600)
            self.shoot(h, "host-image-picker", full_page=False)
            h.keyboard.press("Escape")

    def game_a(self) -> None:
        h, p = self.host, self.player
        code, (p2, p3) = self.room("A")
        expect(p.get_by_text(re.compile("waiting", re.I)).first).to_be_visible(
            timeout=TIMEOUT
        )
        self.shoot(h, "host-lobby", full_page=False)
        self.shoot(p, "player-lobby", full_page=False)

        def question(
            n: int, p1_answer, p2_answer, p3_answer, host_q: str, host_r: str | None
        ) -> None:
            if n == 1:
                self.click_host("Start Game")
            else:
                self.click_host("Next Question")
            h.wait_for_timeout(800)
            p1_answer()
            p2.answer(p2_answer, n)
            h.wait_for_timeout(600)
            self.shoot(h, host_q, full_page=False)
            p3.answer(p3_answer, n)
            self.click_host("Show Results")
            h.wait_for_timeout(1000)
            if host_r:
                self.shoot(h, host_r, full_page=False)

        def mc_mars():
            expect(p.get_by_role("button", name=re.compile("Mars"))).to_be_visible(
                timeout=TIMEOUT
            )
            self.shoot(p, "player-question-mc", full_page=False)
            p.get_by_role("button", name=re.compile("Mars")).click()
            p.wait_for_timeout(600)
            self.shoot(p, "player-feedback", full_page=False)

        question(
            1,
            mc_mars,
            {"selectedIndex": 1},
            {"selectedIndex": 2},
            "host-question-mc",
            "host-results-mc",
        )
        p.wait_for_timeout(600)
        self.shoot(p, "player-results", full_page=False)

        def tf_true():
            self.shoot(p, "player-question-tf", full_page=False)
            p.get_by_role("button", name="True", exact=True).click()

        question(
            2,
            tf_true,
            {"selectedValue": True},
            {"selectedValue": False},
            "host-question-tf",
            "host-results-tf",
        )

        def fitb():
            box = p.get_by_placeholder(re.compile("Type your answer"))
            expect(box).to_be_visible(timeout=TIMEOUT)
            box.fill("Au")
            self.shoot(p, "player-question-fitb", full_page=False)
            p.get_by_role("button", name="Submit").click()

        question(
            3,
            fitb,
            {"text": "Ag"},
            {"text": "au"},
            "host-question-fitb",
            "host-results-fitb-wordcloud",
        )

        def autumn():
            p.get_by_role("button", name=re.compile("Autumn")).click()

        question(
            4,
            autumn,
            {"selectedIndex": 1},
            {"selectedIndex": 2},
            "host-question-mc-participation",
            None,
        )
        self.click_host("Show Final Results")
        h.wait_for_timeout(1500)
        self.shoot(h, "host-gameover")
        p.wait_for_timeout(800)
        self.shoot(p, "player-gameover")
        for s in (p2, p3):
            s.close()

    def one_question(
        self,
        key: str,
        before_p1,
        p2_answer,
        p3_answer,
        host_q: str | None,
        p1_answer=None,
        results: tuple[str, ...] = (),
    ) -> None:
        h, p = self.host, self.player
        _, (p2, p3) = self.room(key)
        self.click_host("Start Game")
        h.wait_for_timeout(1000)
        before_p1()
        if host_q:
            self.shoot(h, host_q, full_page=False)
        if p1_answer:
            p1_answer()
        p2.answer(p2_answer, 1)
        p3.answer(p3_answer, 1)
        self.click_host("Show Results")
        h.wait_for_timeout(1200)
        for name in results:
            page = h if name.startswith("host-") else p
            self.shoot(page, name, full_page=False)
        for s in (p2, p3):
            s.close()

    def games_b_to_f(self) -> None:
        p = self.player

        def ms_select():
            expect(p.get_by_text("Select all that apply")).to_be_visible(
                timeout=TIMEOUT
            )
            p.get_by_role("button", name=re.compile(r"^\W*[A-D]?\s*2$")).click()
            p.get_by_role("button", name=re.compile(r"^\W*[A-D]?\s*7$")).click()
            self.shoot(p, "player-question-multiselect", full_page=False)

        if self.shoot.wants("host-question-multiselect", "player-question-multiselect"):
            self.one_question(
                "B",
                ms_select,
                {"selectedIndices": [0, 1]},
                {"selectedIndices": [2]},
                "host-question-multiselect",
                p1_answer=lambda: p.get_by_role(
                    "button", name=re.compile(r"Submit")
                ).click(),
            )

        def pin_grid():
            canvas = p.get_by_role("application", name=re.compile("Coordinate grid"))
            expect(canvas).to_be_visible(timeout=TIMEOUT)
            canvas.focus()
            for key in (
                "ArrowRight",
                "ArrowRight",
                "ArrowDown",
                "ArrowDown",
                "ArrowDown",
            ):
                p.keyboard.press(key)
            self.shoot(p, "player-question-pin", full_page=False)

        if self.shoot.wants("host-question-pin-grid", "player-question-pin"):
            self.one_question(
                "C",
                pin_grid,
                {"point": {"x": 1, "y": -2}},
                {"point": {"x": -3, "y": 4}},
                "host-question-pin-grid",
                p1_answer=lambda: p.get_by_role("button", name="Submit").click(),
            )

        def pin_image():
            canvas = p.get_by_role("application", name=re.compile("Picture"))
            expect(canvas).to_be_visible(timeout=TIMEOUT)
            expect(p.get_by_role("status")).to_have_count(
                0, timeout=TIMEOUT
            )  # image loaded
            canvas.focus()
            for _ in range(10):
                p.keyboard.press("ArrowLeft")
            p.keyboard.press("ArrowDown")

        if self.shoot.wants(
            "host-question-pin-image", "host-results-pin", "player-results-pin"
        ):
            self.one_question(
                "D",
                pin_image,
                {"point": {"x": 0.40, "y": 0.50}},
                {"point": {"x": 0.80, "y": 0.20}},
                "host-question-pin-image",
                p1_answer=lambda: p.get_by_role("button", name="Submit").click(),
                results=("host-results-pin", "player-results-pin"),
            )

        def estimate():
            box = p.locator("#estimate-input")
            expect(box).to_be_visible(timeout=TIMEOUT)
            box.fill("210")
            self.shoot(p, "player-question-estimate", full_page=False)

        if self.shoot.wants(
            "host-question-estimate",
            "player-question-estimate",
            "host-results-estimate",
        ):
            self.one_question(
                "E",
                estimate,
                {"value": 180},
                {"value": 300},
                "host-question-estimate",
                p1_answer=lambda: p.get_by_role("button", name="Submit").click(),
                results=("host-results-estimate",),
            )

        def picture_options():
            expect(p.get_by_role("button", name=re.compile("Triangle"))).to_be_visible(
                timeout=TIMEOUT
            )
            p.wait_for_timeout(800)
            self.shoot(p, "player-question-image-options", full_page=False)

        if self.shoot.wants(
            "host-question-image-options", "player-question-image-options"
        ):
            self.one_question(
                "F",
                picture_options,
                {"selectedIndex": 2},
                {"selectedIndex": 1},
                "host-question-image-options",
                p1_answer=lambda: p.get_by_role(
                    "button", name=re.compile("Triangle")
                ).click(),
            )

    def after_game(self) -> None:
        fx, h, a = self.fx, self.host, self.admin
        h.goto(f"{HOST_APP}/manage/sessions?course={fx.course}")
        expect(h.get_by_text("Classic (A)").first).to_be_visible(timeout=TIMEOUT)
        self.shoot(h, "host-manage-sessions")
        if self.shoot.wants("host-session-detail"):
            h.get_by_role("button", name="View details").first.click()
            expect(h.get_by_text("Session report").first).to_be_visible(timeout=TIMEOUT)
            self.shoot(h, "host-session-detail", full_page=False)
        # The admin lists grow with whatever the database holds (thousands of test rows on a
        # dev machine), so they are shot at viewport size, not as a full page.
        a.goto(f"{ADMIN_APP}/users")
        expect(a.get_by_text(UI_HOST_USERNAME).first).to_be_visible(timeout=TIMEOUT)
        self.shoot(a, "admin-users", full_page=False)
        a.goto(f"{ADMIN_APP}/courses")
        expect(a.get_by_text(COURSE_NAME).first).to_be_visible(timeout=TIMEOUT)
        self.shoot(a, "admin-courses", full_page=False)
        a.goto(f"{ADMIN_APP}/guests")
        expect(a.get_by_text("Pat Player").first).to_be_visible(timeout=TIMEOUT)
        self.shoot(a, "admin-guests", full_page=False)
        a.goto(f"{ADMIN_APP}/users/{fx.ui_host}")
        expect(a.get_by_text(UI_HOST_USERNAME).first).to_be_visible(timeout=TIMEOUT)
        self.shoot(a, "admin-user-detail")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default="docs/ui/after")
    parser.add_argument("--themes", default="light,dark")
    parser.add_argument(
        "--visual-theme",
        choices=["aurora", "pixel-cats", "pixel-classroom"],
        default="aurora",
    )
    parser.add_argument(
        "--only", default="", help="comma-separated screen names (default: all)"
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="capture the current UI once, without themes",
    )
    args = parser.parse_args()

    only = {n.strip() for n in args.only.split(",") if n.strip()} or set(NAMES)
    unknown = only - set(NAMES)
    assert not unknown, f"unknown screen names: {sorted(unknown)}"
    themes = [t.strip() for t in args.themes.split(",") if t.strip()]
    shoot = Shooter(ROOT / args.out, themes, args.legacy, only, args.visual_theme)

    api = Api()
    fx = Fixtures(api)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            run = Run(
                browser,
                api,
                fx,
                shoot,
                theme_start=themes[0] if not args.legacy else "dark",
            )
            if shoot.wants(
                "host-home",
                "host-home-quiz-open",
                "host-home-sessions-scroll",
                "host-manage-games",
                "host-manage-new-game",
                "host-manage-images",
                "host-manage-rosters",
                "host-manage-roster",
                "host-question-editor",
                "host-focus",
                "host-question-editor-images",
                "host-image-picker",
            ):
                run.manage()
            if shoot.wants(
                "admin-login",
                "host-login",
                "player-join",
                "player-name",
                "player-login",
                "player-name-netid",
                "player-name-local",
                "player-login-error",
            ):
                # A spare lobby room for the logged-out Name page.
                code = api.ok("POST", "/game/rooms", json={"game_id": fx.games["A"]})[
                    "room_code"
                ]
                run.logged_out(code)
            if shoot.wants(
                "host-lobby",
                "player-lobby",
                "host-question-mc",
                "host-results-mc",
                "player-question-mc",
                "player-feedback",
                "player-results",
                "host-question-tf",
                "host-results-tf",
                "host-question-fitb",
                "host-results-fitb-wordcloud",
                "host-question-mc-participation",
                "host-gameover",
                "player-gameover",
                "host-session-detail",
                "player-question-tf",
                "player-question-fitb",
            ):
                run.game_a()
            run.games_b_to_f()
            if shoot.wants(
                "host-manage-sessions",
                "admin-users",
                "admin-courses",
                "admin-guests",
                "admin-user-detail",
                "host-session-detail",
            ):
                run.after_game()
            browser.close()
    finally:
        fx.cleanup()
    missing = sorted(only - set(shoot.taken))
    print(
        f"captured {len(shoot.taken)} screen(s) into {args.out}"
        + (f"; not captured: {missing}" if missing else "")
    )


if __name__ == "__main__":
    main()
