"""
Question feedback — a player's optional thumbs up/down and "hard" flag per question,
and the private session detail built on it (docs/plans/question-feedback.md).

Players send feedback over the socket (websocket/gateway.py::on_question_feedback);
the host sees counts on Game Over and in the session report, and the per-player detail
on /manage/sessions/:id.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import case, delete, func, select, tuple_, update
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.course import Course
from ..models.game import Game, Question
from ..models.session import GameSession, QuestionFeedback, SessionScore
from ..models.user import User

RATINGS = ("UP", "DOWN")


def empty_counts() -> dict[str, int]:
    return {"up": 0, "down": 0, "flagged": 0}


async def save_feedback(
    db: AsyncSession,
    *,
    session_id: str,
    question_id: int,
    user_id: str,
    rating: str | None,
    flagged: bool,
) -> None:
    """Store a player's response; clearing both thumbs and the flag deletes the row."""
    if rating is None and not flagged:
        await db.execute(
            delete(QuestionFeedback).where(
                QuestionFeedback.session_id == session_id,
                QuestionFeedback.question_id == question_id,
                QuestionFeedback.user_id == user_id,
            )
        )
        return
    # One statement, so two quick taps can't race into a duplicate-key error.
    stmt = insert(QuestionFeedback).values(
        session_id=session_id,
        question_id=question_id,
        user_id=user_id,
        rating=rating,
        flagged=flagged,
    )
    await db.execute(
        stmt.on_duplicate_key_update(
            rating=stmt.inserted.rating,
            flagged=stmt.inserted.flagged,
            updated_at=func.now(),
        )
    )


async def feedback_counts(
    db: AsyncSession, session_id: str
) -> dict[int, dict[str, int]]:
    """Question id -> {"up", "down", "flagged"} for one session (questions with any feedback)."""

    # Count with integer CASEs: SQLAlchemy types SUM(<boolean>) as a boolean, which
    # turned a count of 2 into True (= 1).
    def count(condition) -> object:
        return func.sum(case((condition, 1), else_=0))

    rows = await db.execute(
        select(
            QuestionFeedback.question_id,
            count(QuestionFeedback.rating == "UP"),
            count(QuestionFeedback.rating == "DOWN"),
            count(QuestionFeedback.flagged.is_(True)),
        )
        .where(QuestionFeedback.session_id == session_id)
        .group_by(QuestionFeedback.question_id)
    )
    return {
        qid: {"up": int(up or 0), "down": int(down or 0), "flagged": int(flagged or 0)}
        for qid, up, down, flagged in rows
    }


async def move_feedback(db: AsyncSession, from_user_id: str, to_user_id: str) -> None:
    """Re-attribute a merged guest's feedback; the real user's own row wins a clash.

    Plain SQL statements, run now: the guest's row is about to be deleted, and its
    feedback would cascade away if that delete were flushed first.
    """
    taken = (
        await db.execute(
            select(QuestionFeedback.session_id, QuestionFeedback.question_id).where(
                QuestionFeedback.user_id == to_user_id
            )
        )
    ).all()
    if taken:
        await db.execute(
            delete(QuestionFeedback).where(
                QuestionFeedback.user_id == from_user_id,
                tuple_(QuestionFeedback.session_id, QuestionFeedback.question_id).in_(
                    [tuple(t) for t in taken]
                ),
            )
        )
    await db.execute(
        update(QuestionFeedback)
        .where(QuestionFeedback.user_id == from_user_id)
        .values(user_id=to_user_id)
    )


def _identity(user: User) -> tuple[str, str]:
    """(kind, identifier) shown on the detail page."""
    if user.netid:
        return "netid", user.netid
    if user.role == "GUEST":
        return "guest", user.email or ""
    return "local", user.username or ""


async def session_detail(db: AsyncSession, session: GameSession) -> dict:
    """Everything the private session detail page shows (spec §4.6)."""
    game = await db.get(Game, session.game_id)
    course = await db.get(Course, session.course_id)
    host = await db.get(User, session.host_user_id) if session.host_user_id else None

    questions = (
        (
            await db.execute(
                select(Question)
                .where(Question.game_id == session.game_id)
                .order_by(Question.order_index)
            )
        )
        .scalars()
        .all()
    )
    scores = (
        (
            await db.execute(
                select(SessionScore).where(SessionScore.session_id == session.id)
            )
        )
        .scalars()
        .all()
    )
    feedback = (
        (
            await db.execute(
                select(QuestionFeedback).where(
                    QuestionFeedback.session_id == session.id
                )
            )
        )
        .scalars()
        .all()
    )

    user_ids = {s.user_id for s in scores} | {f.user_id for f in feedback}
    users = (
        {
            u.id: u
            for u in (await db.execute(select(User).where(User.id.in_(user_ids))))
            .scalars()
            .all()
        }
        if user_ids
        else {}
    )

    totals: dict[str, float] = defaultdict(float)
    responses: dict[int, dict[str, dict]] = defaultdict(dict)

    def response(qid: int, uid: str) -> dict:
        return responses[qid].setdefault(
            uid,
            {
                "user_id": uid,
                "answer_data": None,
                "is_correct": None,
                "points": None,
                "answer_time_ms": None,
                "rating": None,
                "flagged": False,
            },
        )

    for s in scores:
        totals[s.user_id] += s.points_awarded or 0.0
        r = response(s.question_id, s.user_id)
        r.update(
            answer_data=s.answer_data,
            is_correct=s.is_correct,
            points=s.points_awarded,
            answer_time_ms=s.answer_time_ms,
        )
    counts: dict[int, dict[str, int]] = defaultdict(empty_counts)
    for f in feedback:
        r = response(f.question_id, f.user_id)
        r.update(rating=f.rating, flagged=f.flagged)
        c = counts[f.question_id]
        c["up"] += f.rating == "UP"
        c["down"] += f.rating == "DOWN"
        c["flagged"] += bool(f.flagged)

    players = []
    for uid in user_ids:
        user = users.get(uid)
        kind, identifier = _identity(user) if user else ("guest", "")
        players.append(
            {
                "user_id": uid,
                "display_name": (user.display_name or identifier or "Player")
                if user
                else "Deleted player",
                "identifier": identifier,
                "kind": kind,
                "total_points": round(totals[uid], 2),
            }
        )
    players.sort(key=lambda p: (-p["total_points"], p["display_name"].lower()))
    order = {p["user_id"]: i for i, p in enumerate(players)}

    return {
        "session": {
            "session_id": session.id,
            "room_code": session.room_code,
            "status": session.status,
            "game_title": game.title if game else "Unknown",
            "course_name": course.name if course else "Unknown",
            "course_semester": course.semester if course else "",
            "created_at": session.created_at,
            "completed_at": session.completed_at,
            "host_display_name": (host.display_name or host.username or host.netid)
            if host
            else None,
        },
        "players": players,
        "questions": [
            {
                "question_id": q.id,
                "order_index": q.order_index,
                "type": q.type,
                "grading_type": q.grading_type,
                "prompt": q.prompt,
                "config": q.config or {},
                "answer_data": q.answer_data or {},
                "points_value": q.points_value,
                "feedback": counts.get(q.id, empty_counts()),
                "responses": sorted(
                    responses[q.id].values(), key=lambda r: order[r["user_id"]]
                ),
            }
            for q in questions
        ],
    }
