from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

import structlog
from redis.asyncio import Redis
from sqlalchemy import Select, func, select
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from ..models.course import Course, CourseRoster, UserCourseAccess
from ..models.game import Game, Question, UserGameAccess
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..schemas.game import ScoreResult
from . import feedback_service, question_types
from . import state_service as state

logger = structlog.get_logger()

# Character set from spec: unambiguous alphanumeric (no 0/O/1/I/L)
_ROOM_CHARSET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
_MAX_CODE_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Room code generation
# ---------------------------------------------------------------------------


async def generate_room_code(redis: Redis) -> str:
    for _ in range(_MAX_CODE_ATTEMPTS):
        code = "".join(secrets.choice(_ROOM_CHARSET) for _ in range(6))
        if not await redis.exists(f"room:{code}"):
            return code
    raise ConflictError("Could not generate a unique room code — try again")


# ---------------------------------------------------------------------------
# Access validation helpers
# ---------------------------------------------------------------------------


async def _is_course_host(db: AsyncSession, user: User, course_id: int) -> bool:
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.course_id == course_id,
            UserCourseAccess.role == "HOST",
        )
    )
    return result.scalar_one_or_none() is not None


async def assert_host_can_use_course(
    db: AsyncSession, user: User, course_id: int
) -> Course:
    """Admin can use any course; USER must have HOST role in user_course_access."""
    if user.role != "ADMIN" and not await _is_course_host(db, user, course_id):
        raise ForbiddenError("You do not have HOST access to this course")
    course = await db.get(Course, course_id)
    if not course:
        raise NotFoundError(f"Course {course_id} not found")
    return course


async def can_act_as_session_host(
    db: AsyncSession, user: User, session: GameSession
) -> bool:
    """ADMIN, or the session's host while still a HOST of the session's course."""
    if user.role == "ADMIN":
        return True
    return session.host_user_id == user.id and await _is_course_host(
        db, user, session.course_id
    )


def hosted_course_ids(user: User) -> Select:
    """Ids of courses where the user currently has the HOST role, for IN filters."""
    return select(UserCourseAccess.course_id).where(
        UserCourseAccess.user_id == user.id, UserCourseAccess.role == "HOST"
    )


def manageable_game_ids(user: User) -> Select:
    """Ids of games a non-admin can manage (HOST of the course AND granted), for IN filters."""
    g = aliased(Game)
    return (
        select(g.id)
        .join(
            UserGameAccess,
            (UserGameAccess.game_id == g.id) & (UserGameAccess.user_id == user.id),
        )
        .join(
            UserCourseAccess,
            (UserCourseAccess.course_id == g.course_id)
            & (UserCourseAccess.user_id == user.id)
            & (UserCourseAccess.role == "HOST"),
        )
    )


async def assert_host_can_use_game(db: AsyncSession, user: User, game_id: int) -> Game:
    """Admin can use any game; USER needs HOST role in the game's course AND a game grant."""
    game = await db.get(Game, game_id)
    if not game:
        raise NotFoundError(f"Game {game_id} not found")
    if user.role == "ADMIN":
        return game

    granted = await db.execute(
        select(UserGameAccess).where(
            UserGameAccess.user_id == user.id,
            UserGameAccess.game_id == game_id,
        )
    )
    if granted.scalar_one_or_none() is None or not await _is_course_host(
        db, user, game.course_id
    ):
        raise ForbiddenError("You do not have access to this game")
    return game


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


async def create_room(
    db: AsyncSession,
    redis: Redis,
    host: User,
    game_id: int,
    course_id: int | None = None,
    max_rooms: int = 50,
) -> GameSession:
    game = await assert_host_can_use_game(db, host, game_id)
    if course_id is not None and course_id != game.course_id:
        raise BadRequestError("Game belongs to a different course")
    course_id = game.course_id
    await assert_host_can_use_course(db, host, course_id)

    # Enforce global room limit — count only LOBBY/IN_PROGRESS rooms.
    # COMPLETED/ABANDONED rooms may linger in Redis briefly for reconnection
    # but do not consume a concurrent-room slot.
    all_room_keys = await redis.keys("room:*")
    room_count = 0
    for key in all_room_keys:
        key_str = key if isinstance(key, str) else key.decode()
        if len(key_str) != 11:  # "room:" (5 chars) + 6-char code
            continue
        room_state_data = await state.get_room_state(redis, key_str[5:])
        if room_state_data and room_state_data.get("status") in (
            "LOBBY",
            "IN_PROGRESS",
        ):
            room_count += 1
    if room_count >= max_rooms:
        raise ConflictError(f"Maximum of {max_rooms} concurrent rooms reached")

    await db.get(Game, game_id)
    room_code = await generate_room_code(redis)

    session = GameSession(
        id=str(uuid.uuid4()),
        room_code=room_code,
        game_id=game_id,
        course_id=course_id,
        host_user_id=host.id,
        status="LOBBY",
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    # Store room state in Redis
    await state.set_room_state(
        redis,
        room_code,
        {
            "session_id": session.id,
            "game_id": game_id,
            "course_id": course_id,
            "host_user_id": host.id,
            "status": "LOBBY",
            "reactions_enabled": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    logger.info(
        "room_created",
        room_code=room_code,
        session_id=session.id,
        host_id=host.id,
        game_id=game_id,
        course_id=course_id,
    )
    return session


async def get_session_by_code(
    db: AsyncSession, redis: Redis, room_code: str
) -> tuple[GameSession, dict | None]:
    """
    Return (session, redis_state). redis_state is None if Redis has no record
    (session may still be in MySQL as COMPLETED/ABANDONED).
    """
    redis_state = await state.get_room_state(redis, room_code)

    result = await db.execute(
        select(GameSession)
        .where(GameSession.room_code == room_code)
        .options(selectinload(GameSession.game))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError(f"Room '{room_code}' not found or has expired")

    return session, redis_state


async def start_game(
    db: AsyncSession, redis: Redis, session: GameSession
) -> list[Question]:
    """Transition LOBBY → IN_PROGRESS. Returns ordered question list."""
    if session.status != "LOBBY":
        raise ConflictError(f"Cannot start a game in '{session.status}' state")

    result = await db.execute(
        select(Question)
        .where(Question.game_id == session.game_id)
        .order_by(Question.order_index)
    )
    questions = result.scalars().all()
    if not questions:
        raise ConflictError(
            "This game has no questions — add questions before starting"
        )

    session.status = "IN_PROGRESS"
    # Commit immediately so concurrent on_submit_answer handlers in separate DB
    # sessions see IN_PROGRESS rather than the unflushed LOBBY status.
    await db.commit()

    # Update Redis status
    room_state = await state.get_room_state(redis, session.room_code)
    if room_state:
        room_state["status"] = "IN_PROGRESS"
        await state.set_room_state(redis, session.room_code, room_state)

    logger.info("game_started", session_id=session.id, question_count=len(questions))
    return list(questions)


async def complete_game(db: AsyncSession, redis: Redis, session: GameSession) -> None:
    session.status = "COMPLETED"
    session.completed_at = datetime.now(timezone.utc)
    # Commit so player join attempts racing with game_over see COMPLETED.
    await db.commit()
    logger.info("game_completed", session_id=session.id)
    # Keep Redis state 10 more minutes for reconnection, then let it expire naturally


async def abandon_game(db: AsyncSession, redis: Redis, session: GameSession) -> None:
    session.status = "ABANDONED"
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()
    await state.delete_room_state(redis, session.room_code, session.id)
    logger.info("game_abandoned", session_id=session.id)


# ---------------------------------------------------------------------------
# Player authorisation at join time
# ---------------------------------------------------------------------------


async def admit_guest_to_course(
    db: AsyncSession, course: Course, email: str
) -> str | None:
    """
    Apply the course's guest policy to a guest's email. Raises ForbiddenError if the
    guest is not allowed; returns the roster name under ROSTER_ONLY, None under OPEN.
    """
    if course.guest_policy == "DISABLED":
        raise ForbiddenError("Guests are not allowed in this course")
    if course.guest_policy == "ROSTER_ONLY":
        result = await db.execute(
            select(CourseRoster).where(
                CourseRoster.course_id == course.id,
                func.lower(CourseRoster.email) == email.lower(),
                CourseRoster.is_active == True,  # noqa: E712
            )
        )
        entry = result.scalars().first()
        if entry is None:
            raise ForbiddenError("Your email is not on this course's roster")
        return entry.full_name
    return None


async def authorise_player(db: AsyncSession, user: User, session: GameSession) -> str:
    """
    Check whether the player is permitted to join this session.
    Returns the display name to use for the player.
    Raises ForbiddenError / NotFoundError if not authorised.
    """
    if user.role == "GUEST":
        if user.guest_session_id != session.id:
            raise ForbiddenError("This guest pass is for a different room")
        course = await db.get(Course, session.course_id)
        roster_name = await admit_guest_to_course(db, course, user.email or "")
        return roster_name or user.display_name or "Guest"

    if user.role == "ADMIN":
        return user.display_name or user.username or "Admin"

    # OAuth2 user — check course roster
    if user.netid:
        result = await db.execute(
            select(CourseRoster).where(
                CourseRoster.course_id == session.course_id,
                CourseRoster.netid == user.netid,
                CourseRoster.is_active == True,  # noqa: E712
            )
        )
        roster_entry = result.scalar_one_or_none()
        if roster_entry:
            return roster_entry.full_name  # first name from CSV

    # Local account with explicit PLAYER role for this course
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.course_id == session.course_id,
            UserCourseAccess.role == "PLAYER",
        )
    )
    if result.scalar_one_or_none():
        return user.display_name or user.username or "Player"

    # Local account with HOST role can also join as player
    result = await db.execute(
        select(UserCourseAccess).where(
            UserCourseAccess.user_id == user.id,
            UserCourseAccess.course_id == session.course_id,
            UserCourseAccess.role == "HOST",
        )
    )
    if result.scalar_one_or_none():
        return user.display_name or user.username or "Host"

    raise ForbiddenError("You are not enrolled in the course roster for this game")


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def calculate_score(question: Question, answer_data: dict) -> ScoreResult:
    """
    Calculate points for a player's answer.
    COMPLETENESS: any answer = full points, no answer = 0
    ACCURACY:     the question type's own rule (services/question_types.py)
    """
    return question_types.score_answer(question, answer_data)


async def record_answer(
    db: AsyncSession,
    redis: Redis,
    session_id: str,
    user_id: str,
    question: Question,
    answer_data: dict,
    answer_time_ms: int | None,
) -> ScoreResult:
    """
    Score an answer, write it to MySQL immediately, and update Redis score.
    Returns the score result.
    """
    result = calculate_score(question, answer_data)

    # Persist to MySQL immediately (per-question persistence guarantee)
    score_row = SessionScore(
        session_id=session_id,
        user_id=user_id,
        question_id=question.id,
        points_awarded=result.points_awarded,
        answer_time_ms=answer_time_ms,
        is_correct=result.is_correct,
        answer_data=answer_data or None,
    )
    db.add(score_row)
    await db.flush()

    # Update Redis running score and answered set
    await state.update_player_score(redis, session_id, user_id, result.points_awarded)
    await state.mark_answered(redis, session_id, question.id, user_id)

    # Increment per-option distribution counters for the results bar chart
    for key in question_types.answer_keys(question.type, answer_data):
        await state.increment_answer_dist(redis, session_id, question.id, key)

    return result


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


async def get_leaderboard(db: AsyncSession, session_id: str) -> list[dict]:
    """
    Aggregate session_scores from MySQL to produce a leaderboard.
    Used for QUESTION_RESULTS and GAME_OVER broadcasts.
    """
    from sqlalchemy import func as sqlfunc

    rows = await db.execute(
        select(
            SessionScore.user_id,
            sqlfunc.sum(SessionScore.points_awarded).label("total_score"),
        )
        .where(SessionScore.session_id == session_id)
        .group_by(SessionScore.user_id)
        .order_by(sqlfunc.sum(SessionScore.points_awarded).desc())
    )
    return [{"user_id": r.user_id, "score": float(r.total_score or 0)} for r in rows]


async def get_player_question_summary(
    db: AsyncSession, session_id: str, user_id: str
) -> list[dict]:
    """
    Per-question breakdown for a single player — used in GAME_OVER payload.
    """
    rows = await db.execute(
        select(
            Question.id.label("question_id"),
            Question.prompt,
            Question.points_value,
            Question.type.label("q_type"),
            Question.grading_type,
            Question.config,
            Question.answer_data.label("q_answer_data"),
            SessionScore.points_awarded,
            SessionScore.answer_time_ms,
            SessionScore.answer_data.label("player_answer"),
        )
        .join(GameSession, GameSession.game_id == Question.game_id)
        .outerjoin(
            SessionScore,
            (SessionScore.question_id == Question.id)
            & (SessionScore.session_id == session_id)
            & (SessionScore.user_id == user_id),
        )
        .where(GameSession.id == session_id)
        .order_by(Question.order_index)
    )

    result = []
    for r in rows:
        q_type = r.q_type
        grading_type = r.grading_type
        q_ans = r.q_answer_data or {}
        pts_val = r.points_value

        reveal = question_types.reveal_answer(
            question_types.QuestionFacts(
                q_type, grading_type, r.config or {}, q_ans, pts_val
            )
        )

        result.append(
            {
                "questionId": r.question_id,
                "prompt": r.prompt,
                "type": q_type,
                "gradingType": grading_type,
                "config": r.config or {},
                "pointsAwarded": r.points_awarded or 0,
                "maxPoints": pts_val,
                "answerTimeMs": r.answer_time_ms,
                "playerAnswer": r.player_answer,
                "answerReveal": reveal,
            }
        )

    return result


async def get_host_question_summary(
    db: AsyncSession, session_id: str, total_players: int
) -> list[dict]:
    """Per-question breakdown for the host game-over screen.
    Returns prompt, answer reveal, distribution, and correct/answered counts."""
    from collections import defaultdict

    rows = await db.execute(
        select(
            Question.id.label("question_id"),
            Question.order_index,
            Question.prompt,
            Question.type.label("q_type"),
            Question.grading_type,
            Question.config,
            Question.answer_data.label("q_answer_data"),
            Question.points_value,
            SessionScore.user_id,
            SessionScore.points_awarded,
            SessionScore.answer_data.label("player_answer"),
            SessionScore.answer_time_ms,
            SessionScore.is_correct,
        )
        .join(GameSession, GameSession.game_id == Question.game_id)
        .outerjoin(
            SessionScore,
            (SessionScore.question_id == Question.id)
            & (SessionScore.session_id == session_id),
        )
        .where(GameSession.id == session_id)
        .order_by(Question.order_index)
    )

    questions_meta: dict[int, dict] = {}
    questions_order: list[int] = []
    scores_by_q: dict[int, list[dict]] = defaultdict(list)

    for r in rows:
        qid = r.question_id
        if qid not in questions_meta:
            questions_meta[qid] = {
                "order_index": r.order_index,
                "prompt": r.prompt,
                "type": r.q_type,
                "grading_type": r.grading_type,
                "config": r.config or {},
                "answer_data": r.q_answer_data or {},
                "points_value": r.points_value,
            }
            questions_order.append(qid)
        if r.user_id is not None:
            scores_by_q[qid].append(
                {
                    "player_answer": r.player_answer,
                    "is_correct": bool(r.is_correct),
                    "answer_time_ms": r.answer_time_ms,
                }
            )

    # Thumbs and flags are counts only here: Game Over is on the projector.
    feedback = await feedback_service.feedback_counts(db, session_id)

    result = []
    for qnum, qid in enumerate(questions_order, start=1):
        q = questions_meta[qid]
        scores = scores_by_q[qid]
        q_type = q["type"]
        q_ans = q["answer_data"]
        pts_val = q["points_value"]
        grading_type = q["grading_type"]

        reveal = question_types.reveal_answer(
            question_types.QuestionFacts(
                q_type, grading_type, q["config"], q_ans, pts_val
            )
        )

        dist: dict[str, int] = {}
        values: list = []
        correct_count = 0
        total_time = 0
        time_count = 0
        for s in scores:
            for k in question_types.answer_keys(q_type, s["player_answer"]):
                dist[k] = dist.get(k, 0) + 1
            value = question_types.answer_value(q_type, s["player_answer"])
            if value is not None:
                values.append(value)
            if s["is_correct"]:
                correct_count += 1
            if s["answer_time_ms"] is not None:
                total_time += s["answer_time_ms"]
                time_count += 1

        result.append(
            {
                "questionId": qid,
                "questionNumber": qnum,
                "prompt": q["prompt"],
                "type": q_type,
                "gradingType": grading_type,
                "config": q["config"],
                "pointsValue": pts_val,
                "answerReveal": reveal,
                "answerDistribution": dist,
                # Value-based types (pin_drop, estimate): every submitted value.
                "values": values,
                "totalAnswered": len(scores),
                "totalPlayers": total_players,
                "correctCount": correct_count,
                "avgAnswerTimeMs": round(total_time / time_count)
                if time_count
                else None,
                "feedback": feedback.get(qid, feedback_service.empty_counts()),
            }
        )

    return result


# ---------------------------------------------------------------------------
# Session listings (admin and host session pages)
# ---------------------------------------------------------------------------


async def describe_sessions(
    db: AsyncSession, sessions: list[GameSession]
) -> list[dict]:
    """Rows shaped for AdminSessionItem: names, host and distinct player count."""
    rows = []
    for s in sessions:
        game = await db.get(Game, s.game_id)
        course = await db.get(Course, s.course_id)
        host = await db.get(User, s.host_user_id) if s.host_user_id else None
        count_result = await db.execute(
            select(func.count(SessionScore.user_id.distinct())).where(
                SessionScore.session_id == s.id
            )
        )
        rows.append(
            {
                "session_id": s.id,
                "room_code": s.room_code,
                "status": s.status,
                "game_id": s.game_id,
                "game_title": game.title if game else "Unknown",
                "course_id": s.course_id,
                "course_name": course.name if course else "Unknown",
                "course_semester": course.semester if course else "",
                "host_display_name": (host.display_name or host.username or host.netid)
                if host
                else None,
                "created_at": s.created_at,
                "completed_at": s.completed_at,
                "player_count": count_result.scalar_one() or 0,
            }
        )
    return rows
