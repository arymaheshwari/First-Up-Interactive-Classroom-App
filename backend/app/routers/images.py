"""Public image serving (T8 D3): no login, unguessable ids, ETag revalidation."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..common.exceptions import NotFoundError
from ..database import get_db
from ..models.image import Image
from ..services.image_service import content_disposition, etag_matches, is_image_id

router = APIRouter(prefix="/images", tags=["images"])

Db = Annotated[AsyncSession, Depends(get_db)]


@router.get("/{image_id}")
async def get_image(image_id: str, request: Request, db: Db) -> Response:
    if not is_image_id(image_id):
        raise NotFoundError("Image not found")
    # Metadata first: a revalidation (304) never reads the blob.
    meta = (
        await db.execute(
            select(Image.sha256, Image.content_type, Image.filename).where(
                Image.id == image_id
            )
        )
    ).first()
    if meta is None:
        raise NotFoundError("Image not found")

    headers = {
        "ETag": f'"{meta.sha256}"',
        "Cache-Control": "public, no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": content_disposition(meta.filename),
    }
    if etag_matches(request.headers.get("if-none-match"), meta.sha256):
        return Response(status_code=304, headers=headers)

    data = (
        await db.execute(select(Image.data).where(Image.id == image_id))
    ).scalar_one_or_none()
    if data is None:  # deleted between the two reads
        raise NotFoundError("Image not found")
    return Response(content=data, media_type=meta.content_type, headers=headers)
