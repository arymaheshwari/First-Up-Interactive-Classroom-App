"""
Question feedback (thumbs up/down and the "hard" flag) and the private session detail.

Scenario ids (Q1…Q7) match docs/plans/question-feedback.md §5.
Runs against the live stack, like the rest of tests/integration.
"""

from __future__ import annotations

import asyncio

import pytest

from .helpers import Tracker
from .test_question_types import EST_ABS, PIN, LiveGame, first_of

MC = {
    "type": "multiple_choice",
    "grading_type": "ACCURACY",
    "prompt": "Which planet is known as the Red Planet?",
    "config": {"options": ["Venus", "Mars", "Jupiter"]},
    "answer_data": {"answer_points": [0, 1, 0]},
    "points_value": 10,
    "time_limit_seconds": 30,
}
QUESTIONS = [MC, PIN, EST_ABS]


@pytest.fixture
def t(docker_stack, base_url, admin_token):
    tracker = Tracker(base_url, admin_token)
    yield tracker
    tracker.cleanup()


async def vote(game: LiveGame, player: int, question_id, rating=None, flagged=False):
    client = game.players[player]
    await client.emit(
        "question_feedback",
        {"question_id": question_id, "rating": rating, "flagged": flagged},
    )
    return await first_of(client, "question_feedback_saved", "question_feedback_error")


def detail(t: Tracker, session_id: str, token: str | None = None):
    return t.call("GET", f"/host/sessions/{session_id}/detail", token or t.admin_token)


def responses_by_question(body: dict) -> dict[int, list[dict]]:
    return {q["question_id"]: q["responses"] for q in body["questions"]}


# ---------------------------------------------------------------------------
# Q1 — save, change, clear
# ---------------------------------------------------------------------------


def test_q1_vote_is_saved_changed_and_cleared(t, base_url):
    async def run():
        async with LiveGame(t, base_url, QUESTIONS, players=2) as game:
            host_q, _ = await game.next_question()
            qid = host_q["questionId"]
            kind, _ = await game.answer(0, qid, {"selectedIndex": 1})
            assert kind == "answer_received"

            kind, saved = await vote(game, 0, qid, "UP", True)
            assert kind == "question_feedback_saved", saved
            assert saved == {"questionId": qid, "rating": "UP", "flagged": True}
            # The second player only votes, without answering.
            kind, _ = await vote(game, 1, qid, "DOWN", False)
            assert kind == "question_feedback_saved"

            await game.results()
            body = detail(t, game.session_id).json()
            rows = {r["user_id"]: r for r in responses_by_question(body)[qid]}
            assert len(rows) == 2
            voters = sorted((r["rating"], r["flagged"]) for r in rows.values())
            assert voters == [("DOWN", False), ("UP", True)]
            answered = [r for r in rows.values() if r["answer_data"] is not None]
            assert len(answered) == 1
            assert answered[0]["answer_data"] == {"selectedIndex": 1}
            assert answered[0]["points"] is not None
            only_voted = [r for r in rows.values() if r["answer_data"] is None]
            assert only_voted[0]["points"] is None

            # Change, then clear: a cleared vote leaves no feedback behind.
            kind, saved = await vote(game, 0, qid, "DOWN", False)
            assert saved["rating"] == "DOWN" and saved["flagged"] is False
            q = next(x for x in detail(t, game.session_id).json()["questions"])
            assert q["feedback"] == {"up": 0, "down": 2, "flagged": 0}

            kind, saved = await vote(game, 1, qid, None, False)
            assert kind == "question_feedback_saved"
            body = detail(t, game.session_id).json()
            rows = responses_by_question(body)[qid]
            assert len(rows) == 1  # player 1 answered nothing and now said nothing
            assert body["questions"][0]["feedback"] == {
                "up": 0,
                "down": 1,
                "flagged": 0,
            }

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Q2 — what the server refuses
# ---------------------------------------------------------------------------


def test_q2_rejects_unshown_questions_bad_payloads_and_the_host(t, base_url):
    async def run():
        async with LiveGame(t, base_url, QUESTIONS, players=1) as game:
            host_q, _ = await game.next_question()
            qid = host_q["questionId"]
            later = qid + 1  # the pin question, not shown yet

            kind, err = await vote(game, 0, later, "UP")
            assert kind == "question_feedback_error"
            assert "hasn't been shown" in err["message"] and err["questionId"] == later

            for bad in (
                {"question_id": qid, "rating": "MEH", "flagged": False},
                {"question_id": str(qid), "rating": "UP", "flagged": False},
                {"question_id": qid, "rating": "UP", "flagged": "yes"},
                {"question_id": True, "rating": "UP", "flagged": False},
            ):
                await game.players[0].emit("question_feedback", bad)
                kind, err = await first_of(
                    game.players[0],
                    "question_feedback_saved",
                    "question_feedback_error",
                )
                assert kind == "question_feedback_error", bad
                assert err["message"] == "Invalid feedback", bad

            # None of these used the generic error event, which ends the player's screen.
            with pytest.raises(asyncio.TimeoutError):
                await game.players[0].wait_for("error", 1.0)

            # The host's socket is ignored: nothing is echoed and nothing stored.
            await game.host.emit(
                "question_feedback",
                {"question_id": qid, "rating": "UP", "flagged": True},
            )
            with pytest.raises(asyncio.TimeoutError):
                await game.host.wait_for("question_feedback_saved", 2.0)

            body = detail(t, game.session_id).json()
            assert all(q["responses"] == [] for q in body["questions"])

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Q3 — Game Over counts, then voting is closed
# ---------------------------------------------------------------------------


def test_q3_game_over_carries_counts_and_closes_voting(t, base_url):
    async def run():
        async with LiveGame(t, base_url, [MC], players=3) as game:
            host_q, _ = await game.next_question()
            qid = host_q["questionId"]
            for i, (rating, flagged) in enumerate(
                [("UP", False), ("UP", True), (None, True)]
            ):
                kind, _ = await vote(game, i, qid, rating, flagged)
                assert kind == "question_feedback_saved"
            await game.results()
            stored = detail(t, game.session_id).json()["questions"][0]
            assert stored["feedback"] == {"up": 2, "down": 0, "flagged": 2}, stored
            host_over, player_overs = await game.finish()

            summary = host_over["questionSummary"]
            assert summary[0]["feedback"] == {"up": 2, "down": 0, "flagged": 2}
            # Players' own Game Over payloads carry no one else's feedback.
            assert all(
                "feedback" not in q
                for over in player_overs
                for q in over["questionSummary"]
            )

            kind, err = await vote(game, 0, qid, "DOWN")
            assert kind == "question_feedback_error"
            assert err == {"questionId": qid, "message": "Feedback is closed"}

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Q4 — the detail endpoint: who may read it, and when
# ---------------------------------------------------------------------------


def test_q4_detail_access_and_lobby(t, base_url):
    course = t.course()
    game_id = t.game(course)
    from .test_question_types import add_questions

    add_questions(t, game_id, [MC])
    room = t.room(game_id)
    session_id = t.session_id(room)

    r = detail(t, session_id)
    assert r.status_code == 409, r.text  # nothing played yet

    other_course = t.course()
    _, outsider = t.host(other_course)
    _, insider = t.host(course)

    async def run():
        async with LiveGame(t, base_url, [MC], players=1) as game:
            host_q, _ = await game.next_question()
            await game.answer(0, host_q["questionId"], {"selectedIndex": 0})
            await vote(game, 0, host_q["questionId"], "UP", True)
            await game.results()

            assert detail(t, game.session_id, outsider).status_code in (403, 404)
            assert detail(t, "no-such-session").status_code == 404
            body = detail(t, game.session_id).json()
            assert body["session"]["status"] == "IN_PROGRESS"
            assert [p["kind"] for p in body["players"]] == ["guest"]
            assert body["players"][0]["identifier"].endswith("@example.com")
            response = body["questions"][0]["responses"][0]
            assert response["is_correct"] is False and response["flagged"] is True

    asyncio.run(run())
    # A HOST of the course who didn't host the session and doesn't manage the game
    # has no access, like the downloads.
    assert detail(t, session_id, insider).status_code in (403, 404)


# ---------------------------------------------------------------------------
# Q5 — the HTML report shows counts, and no names
# ---------------------------------------------------------------------------


def test_q5_report_has_feedback_counts(t, base_url):
    async def run():
        async with LiveGame(t, base_url, [MC], players=2) as game:
            host_q, _ = await game.next_question()
            qid = host_q["questionId"]
            await game.answer(0, qid, {"selectedIndex": 1})
            await vote(game, 0, qid, "UP", True)
            await vote(game, 1, qid, "DOWN", False)
            await game.results()
            await game.finish()
            return game.session_id

    session_id = asyncio.run(run())
    r = t.admin("GET", f"/host/sessions/{session_id}/report")
    assert r.status_code == 200, r.text
    assert "Feedback: &#128077; 1 · &#128078; 1 · &#128681; 1 flagged as hard" in r.text
    names = [p["display_name"] for p in detail(t, session_id).json()["players"]]
    assert names and not any(name in r.text for name in names)


# ---------------------------------------------------------------------------
# Q6 — deleting the session removes its feedback
# ---------------------------------------------------------------------------


def test_q6_session_delete_cascades(t, base_url):
    async def run():
        async with LiveGame(t, base_url, [MC], players=1) as game:
            host_q, _ = await game.next_question()
            await vote(game, 0, host_q["questionId"], "UP", True)
            await game.results()
            await game.finish()
            return game.session_id

    session_id = asyncio.run(run())
    assert detail(t, session_id).json()["questions"][0]["feedback"]["up"] == 1
    r = t.admin("DELETE", f"/game/sessions/{session_id}")
    assert r.status_code == 204, r.text
    assert detail(t, session_id).status_code == 404


# ---------------------------------------------------------------------------
# Q7 — a promoted guest keeps their feedback
# ---------------------------------------------------------------------------


def test_q7_merged_guest_keeps_feedback(t, base_url):
    async def run():
        async with LiveGame(t, base_url, [MC], players=1) as game:
            host_q, _ = await game.next_question()
            await vote(game, 0, host_q["questionId"], None, True)
            await game.results()
            await game.finish()
            return game.session_id

    session_id = asyncio.run(run())
    guest_id = detail(t, session_id).json()["players"][0]["user_id"]
    netid = f"fb{guest_id[:8]}"
    r = t.admin(
        "POST",
        "/admin/users/merge-guest",
        json={"guest_user_id": guest_id, "target_netid": netid},
    )
    assert r.status_code == 204, r.text
    t.user_ids.append(guest_id)  # now a netid USER; remove it with the rest
    body = detail(t, session_id).json()
    assert body["players"][0]["kind"] == "netid"
    assert body["players"][0]["identifier"] == netid
    assert body["questions"][0]["feedback"]["flagged"] == 1
