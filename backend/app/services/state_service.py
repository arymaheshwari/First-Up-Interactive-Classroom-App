"""
Redis-backed game state management with MySQL fallback.

Key namespaces:
  room:{code}                    → room metadata JSON          TTL: 90 min (reset on any activity)
  session:{id}:players           → Set of active user_ids
  session:{id}:player:{user_id}  → player metadata JSON
  session:{id}:question          → current question state JSON
  session:{id}:answered:{qid}    → Set of user_ids who answered question qid
  session:{id}:dist:{qid}        → Hash of answer_key → count (e.g. "0"→5, "true"→8)
"""

from __future__ import annotations

import json
from datetime import datetime

import structlog
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.session import GameSession, SessionScore
from ..models.game import Question

logger = structlog.get_logger()

ROOM_TTL = 90 * 60  # 90 minutes in seconds


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def _room_key(code: str) -> str:
    return f"room:{code}"


def _players_key(session_id: str) -> str:
    return f"session:{session_id}:players"


def _player_key(session_id: str, user_id: str) -> str:
    return f"session:{session_id}:player:{user_id}"


def _question_key(session_id: str) -> str:
    return f"session:{session_id}:question"


def _answered_key(session_id: str, question_id: int) -> str:
    return f"session:{session_id}:answered:{question_id}"


def _dist_key(session_id: str, question_id: int) -> str:
    return f"session:{session_id}:dist:{question_id}"


# ---------------------------------------------------------------------------
# Room state
# ---------------------------------------------------------------------------


async def set_room_state(redis: Redis, code: str, data: dict) -> None:
    await redis.set(_room_key(code), json.dumps(data), ex=ROOM_TTL)


async def get_room_state(redis: Redis, code: str) -> dict | None:
    raw = await redis.get(_room_key(code))
    return json.loads(raw) if raw else None


async def refresh_room_ttl(redis: Redis, code: str) -> None:
    """Reset the 90-minute inactivity timer. Called on every WebSocket message."""
    await redis.expire(_room_key(code), ROOM_TTL)


async def delete_room_state(redis: Redis, code: str, session_id: str) -> None:
    """Clean up all keys for a completed/abandoned room."""
    keys = [_room_key(code), _players_key(session_id), _question_key(session_id)]
    answered_keys = await redis.keys(f"session:{session_id}:answered:*")
    dist_keys = await redis.keys(f"session:{session_id}:dist:*")
    player_keys = await redis.keys(f"session:{session_id}:player:*")
    all_keys = keys + answered_keys + dist_keys + player_keys
    if all_keys:
        await redis.delete(*all_keys)


# ---------------------------------------------------------------------------
# Player management
# ---------------------------------------------------------------------------


async def add_player(
    redis: Redis,
    session_id: str,
    user_id: str,
    display_name: str,
    is_guest: bool,
    score: int = 0,
) -> None:
    player_data = {
        "user_id": user_id,
        "display_name": display_name,
        "is_guest": is_guest,
        "score": score,
        "is_connected": True,
    }
    await redis.sadd(_players_key(session_id), user_id)
    await redis.set(_player_key(session_id, user_id), json.dumps(player_data))


async def update_player_score(
    redis: Redis, session_id: str, user_id: str, delta: int
) -> int:
    """Add delta to a player's score and return the new total."""
    raw = await redis.get(_player_key(session_id, user_id))
    if not raw:
        return 0
    data = json.loads(raw)
    data["score"] = data.get("score", 0) + delta
    await redis.set(_player_key(session_id, user_id), json.dumps(data))
    return data["score"]


async def set_player_connected(
    redis: Redis, session_id: str, user_id: str, connected: bool
) -> None:
    raw = await redis.get(_player_key(session_id, user_id))
    if raw:
        data = json.loads(raw)
        data["is_connected"] = connected
        await redis.set(_player_key(session_id, user_id), json.dumps(data))


async def remove_player(redis: Redis, session_id: str, user_id: str) -> None:
    await redis.srem(_players_key(session_id), user_id)
    await redis.delete(_player_key(session_id, user_id))


async def get_player(redis: Redis, session_id: str, user_id: str) -> dict | None:
    raw = await redis.get(_player_key(session_id, user_id))
    return json.loads(raw) if raw else None


async def get_all_players(redis: Redis, session_id: str) -> list[dict]:
    user_ids = await redis.smembers(_players_key(session_id))
    players = []
    for uid in user_ids:
        raw = await redis.get(_player_key(session_id, uid))
        if raw:
            players.append(json.loads(raw))
    return sorted(players, key=lambda p: p.get("score", 0), reverse=True)


async def get_player_count(redis: Redis, session_id: str) -> int:
    return await redis.scard(_players_key(session_id))


# ---------------------------------------------------------------------------
# Current question state
# ---------------------------------------------------------------------------


async def set_current_question(
    redis: Redis,
    session_id: str,
    question_id: int,
    started_at: datetime,
    time_limit_seconds: int,
    question_number: int,
    total_questions: int,
) -> None:
    data = {
        "question_id": question_id,
        "started_at": started_at.isoformat(),
        "time_limit_seconds": time_limit_seconds,
        "question_number": question_number,
        "total_questions": total_questions,
    }
    await redis.set(_question_key(session_id), json.dumps(data))


async def get_current_question(redis: Redis, session_id: str) -> dict | None:
    raw = await redis.get(_question_key(session_id))
    return json.loads(raw) if raw else None


# ---------------------------------------------------------------------------
# Answer tracking
# ---------------------------------------------------------------------------


async def mark_answered(
    redis: Redis, session_id: str, question_id: int, user_id: str
) -> None:
    await redis.sadd(_answered_key(session_id, question_id), user_id)


async def has_answered(
    redis: Redis, session_id: str, question_id: int, user_id: str
) -> bool:
    return await redis.sismember(_answered_key(session_id, question_id), user_id)


async def get_answered_count(redis: Redis, session_id: str, question_id: int) -> int:
    return await redis.scard(_answered_key(session_id, question_id))


async def increment_answer_dist(
    redis: Redis, session_id: str, question_id: int, answer_key: str
) -> None:
    """Increment the per-option counter for a question's answer distribution."""
    await redis.hincrby(_dist_key(session_id, question_id), answer_key, 1)


async def get_answer_dist(
    redis: Redis, session_id: str, question_id: int
) -> dict[str, int]:
    """Return the full answer distribution as {answer_key: count}."""
    raw = await redis.hgetall(_dist_key(session_id, question_id))
    return {k: int(v) for k, v in raw.items()}


async def all_players_answered(redis: Redis, session_id: str, question_id: int) -> bool:
    total = await get_player_count(redis, session_id)
    if total == 0:
        return False
    answered = await get_answered_count(redis, session_id, question_id)
    return answered >= total


# ---------------------------------------------------------------------------
# MySQL fallback — restore state after Redis loss
# ---------------------------------------------------------------------------


async def restore_from_mysql(
    db: AsyncSession, redis: Redis, session: GameSession
) -> dict:
    """
    Rebuild Redis state for a session from MySQL after a Redis restart/flush.
    Returns a state dict describing what was restored.
    """
    session_id = session.id

    # Restore cumulative scores per player
    score_rows = await db.execute(
        select(
            SessionScore.user_id,
            func.sum(SessionScore.points_awarded).label("total"),
        )
        .where(SessionScore.session_id == session_id)
        .group_by(SessionScore.user_id)
    )
    player_scores = {row.user_id: row.total for row in score_rows}

    # Determine the last answered question by order_index
    last_answered_result = await db.execute(
        select(Question.order_index)
        .join(SessionScore, SessionScore.question_id == Question.id)
        .where(SessionScore.session_id == session_id)
        .order_by(Question.order_index.desc())
        .limit(1)
    )
    last_order = last_answered_result.scalar_one_or_none()

    # Find the next question to resume on
    if last_order is not None:
        next_q_result = await db.execute(
            select(Question)
            .where(
                Question.game_id == session.game_id,
                Question.order_index > last_order,
            )
            .order_by(Question.order_index)
            .limit(1)
        )
        next_question = next_q_result.scalar_one_or_none()
    else:
        next_q_result = await db.execute(
            select(Question)
            .where(Question.game_id == session.game_id)
            .order_by(Question.order_index)
            .limit(1)
        )
        next_question = next_q_result.scalar_one_or_none()

    logger.warning(
        "redis_state_lost_restored_from_mysql",
        session_id=session_id,
        players_restored=len(player_scores),
        resumed_question_id=next_question.id if next_question else None,
    )

    return {
        "player_scores": player_scores,
        "next_question": next_question,
        "restored": True,
    }
