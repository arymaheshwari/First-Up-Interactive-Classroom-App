"""Game and question authoring shared by the admin and host routers.

Callers authorize first (require_admin, or the host dependencies); these functions
only enforce content rules.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid

import bleach
import structlog
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from ..common.exceptions import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnprocessableError,
    UnsupportedMediaError,
)
from ..models.course import Course
from ..models.game import Game, Question, UserGameAccess
from ..models.image import Image
from ..models.session import GameSession, SessionScore
from ..models.user import User
from ..schemas.admin import (
    GameMetadata,
    GameUpdate,
    QuestionCreate,
    QuestionUpdate,
    validate_question_structure,
)
from . import image_service, question_types
from . import state_service as state

logger = structlog.get_logger()

SUPPORTED_IMPORT_VERSIONS = frozenset({1, 2})
_PROMPT_TAGS = ["b", "i", "br", "u"]
_LIVE_STATUSES = ("LOBBY", "IN_PROGRESS")


def clean_prompt(prompt: str) -> str:
    return bleach.clean(prompt, tags=_PROMPT_TAGS, attributes={}, strip=True)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


async def create_game(
    db: AsyncSession,
    *,
    creator: User,
    course_id: int,
    title: str,
    description: str,
    max_players: int,
) -> Game:
    if not await db.get(Course, course_id):
        raise NotFoundError(f"Course {course_id} not found")
    game = Game(
        course_id=course_id,
        title=title,
        description=description,
        max_players=max_players,
    )
    db.add(game)
    await db.flush()
    if creator.role != "ADMIN":
        db.add(UserGameAccess(user_id=creator.id, game_id=game.id))
        await db.flush()
    await db.refresh(game)
    logger.info("game_created", game_id=game.id, course_id=course_id, title=title)
    return game


def update_game(game: Game, body: GameUpdate) -> Game:
    if body.title is not None:
        game.title = body.title
    if body.description is not None:
        game.description = body.description
    if body.max_players is not None:
        game.max_players = body.max_players
    return game


async def delete_game(
    db: AsyncSession, redis: Redis, game: Game, *, allow_active: bool
) -> None:
    sessions = (
        (await db.execute(select(GameSession).where(GameSession.game_id == game.id)))
        .scalars()
        .all()
    )
    if not allow_active and any(s.status in _LIVE_STATUSES for s in sessions):
        raise ConflictError("Game has an active session — end it before deleting")

    for s in sessions:
        await state.delete_room_state(redis, s.room_code, s.id)
    # game_sessions.game_id is NOT NULL with no DB cascade, so sessions and their
    # scores must be removed explicitly before the game (see models/CLAUDE.md).
    if sessions:
        await db.execute(
            delete(SessionScore).where(
                SessionScore.session_id.in_([s.id for s in sessions])
            )
        )
    await db.execute(delete(GameSession).where(GameSession.game_id == game.id))
    await db.delete(game)
    logger.info("game_deleted", game_id=game.id, sessions_removed=len(sessions))


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


async def resolve_image_refs(
    db: AsyncSession, course_id: int, q_type: str, config: dict
) -> dict:
    """
    Check every image a question references exists in the game's course, and fill a
    pin_drop image's width/height from the stored image (T8 D4/D5). Runs after
    structure validation on create, update and import.

    The referenced rows are read FOR SHARE, so a concurrent replace/delete of the
    same image waits for this request to commit (D6).
    """
    config = dict(config)
    if config.get("promptImageId") is None:
        config.pop("promptImageId", None)
    option_images = config.get("optionImages")
    if isinstance(option_images, list) and all(i is None for i in option_images):
        config.pop("optionImages")

    refs = question_types.referenced_image_ids(config)
    wanted = {i for i in (refs["prompt"], refs["pin_drop"], *refs["options"]) if i}
    if not wanted:
        return config
    rows = (
        await db.execute(
            select(Image.id, Image.width, Image.height)
            .where(Image.id.in_(wanted), Image.course_id == course_id)
            .with_for_update(read=True)
        )
    ).all()
    found = {row.id: row for row in rows}
    missing = sorted(wanted - found.keys())
    if missing:
        raise UnprocessableError(f"Image {missing[0]} was not found in this course")
    if refs["pin_drop"] and q_type == "pin_drop":
        row = found[refs["pin_drop"]]
        config["image"] = {"imageId": row.id, "width": row.width, "height": row.height}
    return config


async def list_questions(db: AsyncSession, game: Game) -> list[Question]:
    result = await db.execute(
        select(Question)
        .where(Question.game_id == game.id)
        .order_by(Question.order_index)
    )
    return list(result.scalars().all())


async def get_question(db: AsyncSession, game: Game, question_id: int) -> Question:
    result = await db.execute(
        select(Question).where(Question.id == question_id, Question.game_id == game.id)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise NotFoundError(f"Question {question_id} not found in game {game.id}")
    return question


async def create_question(
    db: AsyncSession, game: Game, body: QuestionCreate
) -> Question:
    if body.order_index is None:
        result = await db.execute(
            select(Question.order_index)
            .where(Question.game_id == game.id)
            .order_by(Question.order_index.desc())
            .limit(1)
        )
        max_idx = result.scalar_one_or_none()
        order_index = (max_idx + 1) if max_idx is not None else 0
    else:
        order_index = body.order_index

    config = await resolve_image_refs(db, game.course_id, body.type, body.config)
    question = Question(
        game_id=game.id,
        type=body.type,
        grading_type=body.grading_type,
        prompt=clean_prompt(body.prompt),
        config=config,
        answer_data=body.answer_data,
        time_limit_seconds=body.time_limit_seconds,
        points_value=body.points_value,
        order_index=order_index,
    )
    db.add(question)
    await db.flush()
    await db.refresh(question)
    return question


async def update_question(
    db: AsyncSession, game: Game, question: Question, body: QuestionUpdate
) -> Question:
    # Validate the merged result, not the partial body; skipped for non-structural
    # edits so rows saved before update validation existed can still be renamed/retimed.
    resolved_config = None
    if body.touches_structure():
        merged_type = body.type if body.type is not None else question.type
        merged_config = body.config if body.config is not None else question.config
        try:
            validate_question_structure(
                merged_type,
                body.grading_type
                if body.grading_type is not None
                else question.grading_type,
                merged_config,
                body.answer_data
                if body.answer_data is not None
                else question.answer_data,
            )
        except ValueError as exc:
            raise RequestValidationError(
                [
                    {
                        "type": "value_error",
                        "loc": ("body",),
                        "msg": f"Value error, {exc}",
                        "input": body.model_dump(exclude_none=True),
                    }
                ]
            ) from exc
        # The stored config is re-checked too when only the type changes (T8 D4).
        resolved_config = await resolve_image_refs(
            db, game.course_id, merged_type, merged_config or {}
        )

    if body.type is not None:
        question.type = body.type
    if body.grading_type is not None:
        question.grading_type = body.grading_type
    if body.prompt is not None:
        question.prompt = clean_prompt(body.prompt)
    # Saved when config was sent or the type changed (the resolved form drops nulls).
    if resolved_config is not None and (
        body.config is not None or body.type is not None
    ):
        question.config = resolved_config
    if body.answer_data is not None:
        question.answer_data = body.answer_data
    if body.time_limit_seconds is not None:
        question.time_limit_seconds = body.time_limit_seconds
    if body.points_value is not None:
        question.points_value = body.points_value
    if body.order_index is not None:
        question.order_index = body.order_index
    return question


async def delete_question(db: AsyncSession, question: Question) -> None:
    await db.delete(question)


async def reorder_questions(db: AsyncSession, game: Game, order: list[int]) -> None:
    result = await db.execute(select(Question).where(Question.game_id == game.id))
    questions = {q.id: q for q in result.scalars().all()}
    if set(order) != set(questions.keys()):
        raise ConflictError(
            "order list must contain exactly the IDs of all questions in this game"
        )
    for idx, qid in enumerate(order):
        questions[qid].order_index = idx


# ---------------------------------------------------------------------------
# Import / export — format "buzzer/game". Version 1 has no images; version 2
# embeds every referenced image as base64 (T8 D7). Neither carries a course.
# ---------------------------------------------------------------------------

_MAX_REF_LENGTH = 64
#: Allowance for the question JSON on top of the base64 images (D7 estimate).
_EXPORT_OVERHEAD = 1024 * 1024


def _image_refs_in_order(configs: list[dict]) -> list[str]:
    """Every image id the configs reference, first use first, no repeats."""
    seen: dict[str, None] = {}
    for config in configs:
        refs = question_types.referenced_image_ids(config)
        for image_id in (refs["prompt"], *refs["options"], refs["pin_drop"]):
            if image_id:
                seen.setdefault(image_id, None)
    return list(seen)


def _encode_bundle(bundle: dict, blobs: dict[str, bytes]) -> bytes:
    """Base64 the images and serialise (threadpool: tens of MB of work)."""
    for entry in bundle.get("images", []):
        entry["data"] = base64.b64encode(blobs[entry["ref"]]).decode("ascii")
    return json.dumps(bundle, indent=2, ensure_ascii=False).encode()


async def export_game(db: AsyncSession, game: Game) -> tuple[str, bytes]:
    questions = await list_questions(db, game)
    image_ids = _image_refs_in_order([q.config or {} for q in questions])
    bundle: dict = {
        "format": "buzzer/game",
        "version": 2 if image_ids else 1,
        "game": {
            "title": game.title,
            "description": game.description,
            "max_players": game.max_players,
        },
        "questions": [
            {
                "type": q.type,
                "grading_type": q.grading_type,
                "prompt": q.prompt,
                "config": q.config,
                "answer_data": q.answer_data,
                "time_limit_seconds": q.time_limit_seconds,
                "points_value": q.points_value,
            }
            for q in questions
        ],
    }
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in game.title)
    if not image_ids:
        return f"{safe_title}.json", json.dumps(
            bundle, indent=2, ensure_ascii=False
        ).encode()

    # Size first, from metadata only, so an oversized export never loads the blobs.
    sizes = (
        await db.execute(
            select(Image.id, Image.byte_size).where(
                Image.id.in_(image_ids), Image.course_id == game.course_id
            )
        )
    ).all()
    estimate = sum(row.byte_size for row in sizes) * 4 // 3 + _EXPORT_OVERHEAD
    if estimate > image_service.MAX_IMPORT_BYTES:
        raise ConflictError(
            f"This game's images make a file of about {estimate // (1024 * 1024)} MB, "
            "over the 60 MB import limit — use fewer or smaller images"
        )
    rows = (
        await db.execute(
            select(Image)
            .options(undefer(Image.data))
            .where(Image.id.in_(image_ids), Image.course_id == game.course_id)
        )
    ).scalars()
    by_id = {image.id: image for image in rows}
    bundle["images"] = [
        {
            "ref": image_id,
            "filename": by_id[image_id].filename,
            "contentType": by_id[image_id].content_type,
        }
        for image_id in image_ids
        if image_id in by_id
    ]
    blobs = {image_id: image.data for image_id, image in by_id.items()}
    content = await image_service.run_image_job(_encode_bundle, bundle, blobs)
    return f"{safe_title}.json", content


def _bad_import(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


def _parse_image_entries(images: object) -> dict[str, dict]:
    """Shape-check a v2 `images` list (nothing decoded yet) → {ref: entry}."""
    if not isinstance(images, list):
        raise _bad_import("images must be a list")
    if len(images) > image_service.MAX_IMPORT_IMAGES:
        raise _bad_import(
            f"A game file can embed at most {image_service.MAX_IMPORT_IMAGES} images"
        )
    entries: dict[str, dict] = {}
    for i, entry in enumerate(images):
        where = f"images[{i}]"
        if not isinstance(entry, dict):
            raise _bad_import(f"{where} must be an object")
        ref = entry.get("ref")
        if not isinstance(ref, str) or not 1 <= len(ref) <= _MAX_REF_LENGTH:
            raise _bad_import(
                f"{where}: ref must be text of 1–{_MAX_REF_LENGTH} characters"
            )
        if not isinstance(entry.get("data"), str):
            raise _bad_import(f"{where} ({ref}): data must be base64 text")
        if not isinstance(entry.get("filename", ""), str):
            raise _bad_import(f"{where} ({ref}): filename must be text")
        if ref in entries:
            raise _bad_import(f"{where}: ref {ref!r} appears more than once")
        entries[ref] = entry
    return entries


def _question_refs(number: int, raw: object) -> list[str]:
    """The image refs one raw (unvalidated) question uses; 422 on a wrong shape."""
    config = raw.get("config") if isinstance(raw, dict) else None
    if not isinstance(config, dict):
        return []  # QuestionCreate reports the real problem
    prompt = config.get("promptImageId")
    options = config.get("optionImages")
    image = config.get("image")
    ok = (
        (prompt is None or isinstance(prompt, str))
        and (
            options is None
            or (
                isinstance(options, list)
                and all(o is None or isinstance(o, str) for o in options)
            )
        )
        and (
            image is None
            or (isinstance(image, dict) and isinstance(image.get("imageId"), str))
        )
    )
    if not ok:
        raise _bad_import(f"Question {number}: invalid image reference")
    refs = question_types.referenced_image_ids(config)
    return [r for r in (refs["prompt"], *refs["options"], refs["pin_drop"]) if r]


def _rewrite_refs(raw: dict, mapping: dict[str, str]) -> dict:
    """A copy of a raw question with every image ref replaced by mapping[ref]."""
    config = raw.get("config")
    if not isinstance(config, dict):
        return raw
    config = dict(config)
    if isinstance(config.get("promptImageId"), str):
        config["promptImageId"] = mapping[config["promptImageId"]]
    if isinstance(config.get("optionImages"), list):
        config["optionImages"] = [
            mapping[o] if isinstance(o, str) else o for o in config["optionImages"]
        ]
    if isinstance(config.get("image"), dict):
        config["image"] = {
            **config["image"],
            "imageId": mapping[config["image"]["imageId"]],
        }
    return {**raw, "config": config}


def _b64decode(data: str) -> bytes:
    return base64.b64decode(data, validate=True)


def _validate_questions(raw_questions: list) -> list[QuestionCreate]:
    validated: list[QuestionCreate] = []
    for i, q in enumerate(raw_questions):
        try:
            validated.append(QuestionCreate(**q))
        except Exception as exc:
            raise _bad_import(f"Question {i + 1} invalid: {exc}") from exc
    return validated


async def _store_embedded_images(
    db: AsyncSession,
    creator: User,
    course_id: int,
    entries: dict[str, dict],
    used: list[str],
) -> dict[str, str]:
    """Decode, process and store each used entry in the target course → {ref: id}."""
    mapping: dict[str, str] = {}
    for ref in used:
        entry = entries[ref]
        try:
            raw = await image_service.run_image_job(_b64decode, entry["data"])
        except (binascii.Error, ValueError) as exc:
            raise _bad_import(f"Image {ref!r}: data isn't valid base64") from exc
        try:
            processed = await image_service.process_upload_async(
                raw, entry.get("filename") or "image"
            )
        except (PayloadTooLargeError, UnsupportedMediaError, UnprocessableError) as exc:
            raise _bad_import(f"Image {ref!r}: {exc.message}") from exc
        image, _ = await image_service.create_image(db, course_id, creator, processed)
        mapping[ref] = image.id
    return mapping


async def import_game(
    db: AsyncSession, *, creator: User, course_id: int, raw: bytes
) -> Game:
    try:
        bundle = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _bad_import(f"Invalid JSON: {exc}") from exc
    if not isinstance(bundle, dict) or bundle.get("format") != "buzzer/game":
        raise _bad_import("Unrecognised file format")
    version = bundle.get("version")
    if version not in SUPPORTED_IMPORT_VERSIONS:
        raise _bad_import(
            f"Unsupported version {version!r}; server supports versions "
            + ", ".join(str(v) for v in sorted(SUPPORTED_IMPORT_VERSIONS))
        )
    if version == 1 and "images" in bundle:
        raise _bad_import("images requires version 2")

    try:
        meta = GameMetadata(**bundle.get("game", {}))
    except Exception as exc:
        raise _bad_import(f"Invalid game metadata: {exc}") from exc

    raw_questions = bundle.get("questions", [])
    if not isinstance(raw_questions, list):
        raise _bad_import("questions must be a list")

    if version == 2:
        entries = _parse_image_entries(bundle.get("images", []))
        used: dict[str, None] = {}
        for i, q in enumerate(raw_questions):
            for ref in _question_refs(i + 1, q):
                if ref not in entries:
                    raise _bad_import(
                        f"Question {i + 1}: image {ref!r} isn't in the file's images"
                    )
                used.setdefault(ref, None)
        # Validate the questions with stand-in ids first, so a bad question costs no
        # image processing; then store the images and validate the real ids.
        stand_ins = {ref: uuid.uuid4().hex for ref in used}
        _validate_questions([_rewrite_refs(q, stand_ins) for q in raw_questions])
        mapping = await _store_embedded_images(
            db, creator, course_id, entries, list(used)
        )
        raw_questions = [_rewrite_refs(q, mapping) for q in raw_questions]

    validated = _validate_questions(raw_questions)
    configs: list[dict] = []
    for i, q in enumerate(validated):
        try:
            configs.append(await resolve_image_refs(db, course_id, q.type, q.config))
        except UnprocessableError as exc:
            raise UnprocessableError(f"Question {i + 1}: {exc.message}") from exc

    game = await create_game(
        db,
        creator=creator,
        course_id=course_id,
        title=meta.title,
        description=meta.description,
        max_players=meta.max_players,
    )
    for idx, q in enumerate(validated):
        db.add(
            Question(
                game_id=game.id,
                type=q.type,
                grading_type=q.grading_type,
                prompt=clean_prompt(q.prompt),
                config=configs[idx],
                answer_data=q.answer_data,
                time_limit_seconds=q.time_limit_seconds,
                points_value=q.points_value,
                order_index=idx,
            )
        )
    await db.flush()
    logger.info(
        "game_imported", game_id=game.id, course_id=course_id, questions=len(validated)
    )
    return game
