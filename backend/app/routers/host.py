"""Host management API — rosters, games, questions and session downloads.

Every route is scoped to courses/games the caller hosts (common/dependencies.py);
ADMIN passes every check. Logic is shared with routers/admin.py via services.
"""

from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.dependencies import (
    get_downloadable_session,
    get_hosted_course,
    get_manageable_game,
    get_manageable_image,
    require_user,
)
from ..common.exceptions import ConflictError
from ..database import get_db
from ..models.course import Course, CourseRoster
from ..models.game import Game, Question
from ..models.image import Image
from ..models.session import GameSession
from ..models.user import User
from ..redis_client import get_redis
from ..schemas.admin import (
    GameCreate,
    GameResponse,
    GameUpdate,
    HostSessionItem,
    ImageResponse,
    ImageUploadResponse,
    QuestionCreate,
    QuestionReorder,
    QuestionResponse,
    QuestionUpdate,
    RosterEntryPatch,
    RosterEntryResponse,
    RosterImportPayload,
    RosterUploadResult,
    SessionDetail,
)
from ..services import (
    content_service,
    feedback_service,
    game_service,
    image_service,
    roster_service,
)
from ..services.export_service import build_session_export
from ..services.report_service import build_session_report

router = APIRouter(prefix="/host", tags=["host"])

CurrentUser = Annotated[User, Depends(require_user)]
Db = Annotated[AsyncSession, Depends(get_db)]
HostedCourse = Annotated[Course, Depends(get_hosted_course)]
ManageableGame = Annotated[Game, Depends(get_manageable_game)]
DownloadableSession = Annotated[GameSession, Depends(get_downloadable_session)]
ManageableImage = Annotated[Image, Depends(get_manageable_image)]


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/roster", response_model=list[RosterEntryResponse])
async def list_roster(course: HostedCourse, db: Db) -> list[CourseRoster]:
    return await roster_service.list_roster(db, course.id)


@router.post("/courses/{course_id}/roster", response_model=RosterUploadResult)
async def upload_roster(
    course: HostedCourse,
    file: Annotated[UploadFile, File(description="Canvas gradebook CSV export")],
    db: Db,
) -> RosterUploadResult:
    return await roster_service.process_roster_csv(db, course.id, await file.read())


@router.post("/courses/{course_id}/roster/import", response_model=RosterUploadResult)
async def import_roster_rows(
    course: HostedCourse, payload: RosterImportPayload, db: Db
) -> RosterUploadResult:
    rows = [
        {"netid": r.netid, "full_name": r.full_name, "email": r.email}
        for r in payload.rows
    ]
    return await roster_service.process_roster_rows(db, course.id, rows)


@router.patch(
    "/courses/{course_id}/roster/{roster_id}", response_model=RosterEntryResponse
)
async def patch_roster_entry(
    roster_id: int, body: RosterEntryPatch, course: HostedCourse, db: Db
) -> CourseRoster:
    return await roster_service.patch_roster_entry(db, course.id, roster_id, body)


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/games", response_model=list[GameResponse])
async def list_course_games(
    course: HostedCourse, user: CurrentUser, db: Db
) -> list[Game]:
    stmt = select(Game).where(Game.course_id == course.id).order_by(Game.title)
    if user.role != "ADMIN":
        stmt = stmt.where(Game.id.in_(game_service.manageable_game_ids(user)))
    return (await db.execute(stmt)).scalars().all()


@router.post("/games", response_model=GameResponse, status_code=201)
async def create_game(body: GameCreate, user: CurrentUser, db: Db) -> Game:
    # course_id comes from the body, not the path, so get_hosted_course can't guard it.
    await game_service.assert_host_can_use_course(db, user, body.course_id)
    return await content_service.create_game(
        db,
        creator=user,
        course_id=body.course_id,
        title=body.title,
        description=body.description,
        max_players=body.max_players,
    )


@router.post("/games/import", status_code=201)
async def import_game(
    file: Annotated[UploadFile, File(description="buzzer/game JSON bundle")],
    course_id: Annotated[int, Form(gt=0, description="Course to attach the game to")],
    user: CurrentUser,
    db: Db,
) -> dict:
    await game_service.assert_host_can_use_course(db, user, course_id)
    game = await content_service.import_game(
        db,
        creator=user,
        course_id=course_id,
        raw=await image_service.read_bounded(
            file, image_service.MAX_IMPORT_BYTES, "Game files can be at most 60 MB"
        ),
    )
    return {"game_id": game.id}


@router.get("/games/{game_id}", response_model=GameResponse)
async def get_game(game: ManageableGame) -> Game:
    return game


@router.put("/games/{game_id}", response_model=GameResponse)
async def update_game(body: GameUpdate, game: ManageableGame) -> Game:
    return content_service.update_game(game, body)


@router.delete("/games/{game_id}", status_code=204)
async def delete_game(game: ManageableGame, db: Db, redis=Depends(get_redis)) -> None:
    await content_service.delete_game(db, redis, game, allow_active=False)


@router.get("/games/{game_id}/export")
async def export_game(game: ManageableGame, db: Db) -> StreamingResponse:
    filename, content = await content_service.export_game(db, game)
    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/json",
        headers=_attachment(filename),
    )


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------


@router.get("/games/{game_id}/questions", response_model=list[QuestionResponse])
async def list_questions(game: ManageableGame, db: Db) -> list[Question]:
    return await content_service.list_questions(db, game)


@router.post(
    "/games/{game_id}/questions", response_model=QuestionResponse, status_code=201
)
async def create_question(
    body: QuestionCreate, game: ManageableGame, db: Db
) -> Question:
    return await content_service.create_question(db, game, body)


@router.put("/games/{game_id}/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: int, body: QuestionUpdate, game: ManageableGame, db: Db
) -> Question:
    question = await content_service.get_question(db, game, question_id)
    return await content_service.update_question(db, game, question, body)


@router.delete("/games/{game_id}/questions/{question_id}", status_code=204)
async def delete_question(question_id: int, game: ManageableGame, db: Db) -> None:
    question = await content_service.get_question(db, game, question_id)
    await content_service.delete_question(db, question)


@router.post("/games/{game_id}/questions/reorder", status_code=204)
async def reorder_questions(
    body: QuestionReorder, game: ManageableGame, db: Db
) -> None:
    await content_service.reorder_questions(db, game, body.order)


# ---------------------------------------------------------------------------
# Sessions and downloads
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[HostSessionItem])
async def list_sessions(
    user: CurrentUser,
    db: Db,
    course_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[dict]:
    """
    Sessions the caller hosted in a course they still HOST, or whose game they manage
    (ADMIN: all), newest first.
    """
    stmt = select(GameSession).order_by(GameSession.created_at.desc())
    if course_id is not None:
        stmt = stmt.where(GameSession.course_id == course_id)
    if user.role != "ADMIN":
        stmt = stmt.where(
            or_(
                and_(
                    GameSession.host_user_id == user.id,
                    GameSession.course_id.in_(game_service.hosted_course_ids(user)),
                ),
                GameSession.game_id.in_(game_service.manageable_game_ids(user)),
            )
        )
    sessions = list((await db.execute(stmt)).scalars().all())
    rows = await game_service.describe_sessions(db, sessions)
    hosted = set((await db.execute(game_service.hosted_course_ids(user))).scalars())
    for session, row in zip(sessions, rows):
        row["can_delete"] = user.role == "ADMIN" or (
            session.host_user_id == user.id and session.course_id in hosted
        )
    return rows


def _require_completed(session: GameSession) -> None:
    if session.status != "COMPLETED":
        raise ConflictError("Downloads are available once the session has completed")


@router.get("/sessions/{session_id}/detail", response_model=SessionDetail)
async def session_detail(session: DownloadableSession, db: Db) -> dict:
    """
    Private per-session detail: every player's answers and question feedback
    (docs/plans/question-feedback.md §4.6). Same access as the downloads.
    """
    if session.status == "LOBBY":
        raise ConflictError("Nothing has been played in this session yet")
    return await feedback_service.session_detail(db, session)


@router.get("/sessions/{session_id}/report")
async def session_report(session: DownloadableSession, db: Db) -> Response:
    """Standalone HTML summary of a completed session (aggregate stats, no PII)."""
    _require_completed(session)
    filename, content = await build_session_report(db, session.id)
    return Response(
        content=content, media_type="text/html", headers=_attachment(filename)
    )


@router.get("/sessions/{session_id}/export")
async def export_session(
    session: DownloadableSession,
    db: Db,
    format: str = Query("canvas", description="'canvas' or 'raw'"),
    title: str | None = Query(
        None, description="Assignment column title (Canvas format)"
    ),
    sis_domain: str = Query(
        "", description="Domain appended to netid for SIS Login ID (e.g. wisc.edu)"
    ),
    roster_only: bool = Query(
        True, description="Exclude players without a netid (guests, local accounts)"
    ),
    per_question: bool = Query(
        False, description="One column per question instead of total"
    ),
) -> StreamingResponse:
    """Per-player scores CSV of a completed session (raw, or Canvas gradebook format)."""
    _require_completed(session)
    filename, content = await build_session_export(
        db,
        session.id,
        format=format,
        title=title,
        sis_domain=sis_domain,
        roster_only=roster_only,
        per_question=per_question,
    )
    return StreamingResponse(
        io.BytesIO(content), media_type="text/csv", headers=_attachment(filename)
    )


# ---------------------------------------------------------------------------
# Image library (T8) — any HOST of the course manages its images (D6)
# ---------------------------------------------------------------------------


@router.get("/courses/{course_id}/images", response_model=list[ImageResponse])
async def list_images(course: HostedCourse, db: Db) -> list[dict]:
    """The course's images, newest first, each with the questions that use it."""
    images = (
        (
            await db.execute(
                select(Image)
                .where(Image.course_id == course.id)
                .order_by(Image.created_at.desc(), Image.id)
            )
        )
        .scalars()
        .all()
    )
    usages = await image_service.usages_by_image(db, course.id)
    return [image_service.image_response(i, usages.get(i.id, [])) for i in images]


@router.post(
    "/courses/{course_id}/images",
    response_model=ImageUploadResponse,
    status_code=201,
)
async def upload_image(
    course: HostedCourse,
    file: Annotated[UploadFile, File(description="PNG, JPEG, GIF or WebP, ≤ 5 MB")],
    user: CurrentUser,
    db: Db,
    response: Response,
) -> dict:
    """201 for a new image; 200 with the existing one when it's already in the library."""
    raw = await image_service.read_bounded(
        file, image_service.MAX_UPLOAD_BYTES, "Images can be at most 5 MB"
    )
    processed = await image_service.process_upload_async(raw, file.filename)
    image, created = await image_service.create_image(db, course.id, user, processed)
    usages: list[dict] = []
    if not created:
        response.status_code = 200
        usages = await image_service.image_usages(db, image)
    return {**image_service.image_response(image, usages), "deduplicated": not created}


@router.put("/images/{image_id}", response_model=ImageResponse)
async def replace_image(
    image: ManageableImage,
    file: Annotated[UploadFile, File(description="PNG, JPEG, GIF or WebP, ≤ 5 MB")],
    db: Db,
) -> dict:
    """Swap an image's picture; the id (and every question using it) stays (D6)."""
    raw = await image_service.read_bounded(
        file, image_service.MAX_UPLOAD_BYTES, "Images can be at most 5 MB"
    )
    processed = await image_service.process_upload_async(raw, file.filename)
    locked = await image_service.lock_image(db, image.id)
    await image_service.check_can_replace(db, locked)
    locked = await image_service.replace_image(db, locked, processed)
    usages = await image_service.image_usages(db, locked)
    return image_service.image_response(locked, usages)


@router.delete("/images/{image_id}", status_code=204)
async def delete_image(image: ManageableImage, db: Db) -> None:
    """Blocked (409, with `used_by`) while any question uses the image (D6)."""
    locked = await image_service.lock_image(db, image.id)
    await image_service.check_can_delete(db, locked)
    await image_service.delete_image(db, locked)
