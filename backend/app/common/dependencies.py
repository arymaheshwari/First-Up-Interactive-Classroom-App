from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from ..database import get_db
from ..models.course import Course
from ..models.game import Game
from ..models.image import Image
from ..models.session import GameSession
from ..models.user import User
from ..services import game_service, image_service
from ..services.auth_service import decode_token, get_user_by_id

logger = structlog.get_logger()

_bearer = HTTPBearer(auto_error=False)


async def _token_from_request(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    access_token: Annotated[str | None, Cookie()] = None,
) -> str | None:
    """Extract JWT from Authorization header or access_token cookie."""
    if credentials:
        return credentials.credentials
    return access_token


async def get_current_user(
    token: Annotated[str | None, Depends(_token_from_request)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if not token:
        raise UnauthorizedError("Authentication required")
    try:
        payload = decode_token(token)
    except JWTError:
        raise UnauthorizedError("Invalid or expired token")

    token_type = payload.get("token_type")
    if token_type not in ("access", "temp"):
        raise UnauthorizedError("Invalid token type")

    user = await get_user_by_id(db, payload["sub"])
    if not user:
        raise UnauthorizedError("User not found")
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != "ADMIN":
        raise ForbiddenError("Admin access required")
    return user


async def require_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Allow ADMIN and USER roles; reject GUEST."""
    if user.role == "GUEST":
        raise ForbiddenError("Authenticated account required")
    return user


# Host resource guards (ADMIN passes all three). Each reads its id from the path.


async def get_hosted_course(
    course_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Course:
    return await game_service.assert_host_can_use_course(db, user, course_id)


async def get_manageable_game(
    game_id: int,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Game:
    return await game_service.assert_host_can_use_game(db, user, game_id)


async def get_downloadable_session(
    session_id: str,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GameSession:
    """ADMIN, the session's host while still a course HOST, or anyone who manages its game."""
    session = await db.get(GameSession, session_id)
    if not session:
        raise NotFoundError(f"Session {session_id} not found")
    if not await game_service.can_act_as_session_host(db, user, session):
        await game_service.assert_host_can_use_game(db, user, session.game_id)
    return session


async def get_refresh_token(
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> str:
    if not refresh_token:
        raise UnauthorizedError("No refresh token")
    return refresh_token


async def get_manageable_image(
    image_id: str,
    user: Annotated[User, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Image:
    """
    Any HOST of the image's course (ADMIN always) may manage it — images are a course
    library, so no game grant is needed (T8 D6). The bytes are not loaded.
    """
    if not image_service.is_image_id(image_id):
        raise NotFoundError("Image not found")
    image = await db.get(Image, image_id)
    if image is None:
        raise NotFoundError("Image not found")
    await game_service.assert_host_can_use_course(db, user, image.course_id)
    return image
