"""
Course image library (T8) — the upload pipeline and image helpers.

Every upload (and every image embedded in an imported game) is decoded, shrunk and
re-encoded here before it is stored, so EXIF/GPS metadata, polyglots and multi-MB
photos never reach the database or the players. See docs/plans/t8-image-support.md
D2 for the rules this module implements.

CPU-heavy work never runs on the event loop the live game shares: callers use the
async wrappers, which run one job at a time in the threadpool (`IMAGE_WORK`).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import quote

from fastapi import UploadFile
from PIL import Image as PILImage
from PIL import UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ..common.exceptions import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    UnprocessableError,
    UnsupportedMediaError,
)
from ..models.game import Game, Question
from ..models.image import Image
from ..models.session import GameSession
from ..models.user import User
from . import question_types

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_IMPORT_BYTES = 60 * 1024 * 1024
MAX_IMPORT_IMAGES = 100
MAX_LONG_SIDE = 1600
MAX_SIDE = 12_000
COURSE_QUOTA_BYTES = 200 * 1024 * 1024

# Per-format pixel caps (D2): JPEG decodes at reduced scale via draft(), so big phone
# photos stay cheap; the others decode at full size (~225 MB peak at 25 MP, measured).
PIXEL_CAPS = {
    "JPEG": 50_000_000,
    "PNG": 25_000_000,
    "GIF": 25_000_000,
    "WEBP": 25_000_000,
}
# Second line of defence: above 2x this, Pillow raises DecompressionBombError itself.
PILImage.MAX_IMAGE_PIXELS = 50_000_000

# Stored format per input format, and its media type.
_OUTPUT = {"JPEG": "JPEG", "PNG": "PNG", "GIF": "PNG", "WEBP": "WEBP"}
_MEDIA_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
_SIXTEEN_BIT = {"I;16", "I;16B", "I;16L", "I;16N", "I"}
_ALPHA_MODES = {"RGBA", "LA", "PA", "La", "RGBa"}
# EXIF orientation → the transpose that undoes it (same table as ImageOps.exif_transpose).
_ORIENTATION = {
    2: PILImage.Transpose.FLIP_LEFT_RIGHT,
    3: PILImage.Transpose.ROTATE_180,
    4: PILImage.Transpose.FLIP_TOP_BOTTOM,
    5: PILImage.Transpose.TRANSPOSE,
    6: PILImage.Transpose.ROTATE_270,
    7: PILImage.Transpose.TRANSVERSE,
    8: PILImage.Transpose.ROTATE_90,
}

# One image job at a time in this process (D2): bounds memory and keeps the
# threadpool free for everything else.
IMAGE_WORK = asyncio.Semaphore(1)

T = TypeVar("T")


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    content_type: str
    width: int
    height: int
    sha256: str
    filename: str


# ---------------------------------------------------------------------------
# Upload pipeline (synchronous — run it through process_upload_async)
# ---------------------------------------------------------------------------


def process_upload(raw: bytes, filename: str | None) -> ProcessedImage:
    """
    Validate, shrink and re-encode one image (D2). Raises:
    PayloadTooLargeError (413) over 5 MB; UnsupportedMediaError (415) if it isn't a
    PNG, JPEG, GIF or WebP; UnprocessableError (422) for corrupt or oversized images.
    """
    if len(raw) > MAX_UPLOAD_BYTES:
        raise PayloadTooLargeError("Images can be at most 5 MB")

    try:
        im = PILImage.open(io.BytesIO(raw))
    except UnidentifiedImageError as exc:
        raise UnsupportedMediaError("Not a PNG, JPEG, GIF or WebP image") from exc
    except PILImage.DecompressionBombError as exc:
        raise UnprocessableError("Image has too many pixels") from exc

    fmt = im.format
    if fmt not in PIXEL_CAPS:
        raise UnsupportedMediaError("Not a PNG, JPEG, GIF or WebP image")

    # 1. Header checks, before any pixel data is decoded.
    width, height = im.size
    if width * height > PIXEL_CAPS[fmt] or max(width, height) > MAX_SIDE:
        raise UnprocessableError(
            f"Image is too large ({width}×{height}); the limit is "
            f"{PIXEL_CAPS[fmt] // 1_000_000} megapixels and {MAX_SIDE} px per side"
        )
    try:
        orientation = im.getexif().get(0x0112) if fmt != "GIF" else None

        # 2. First frame only (animated GIF / WebP / APNG).
        im.seek(0)

        # 3. JPEG: decode at reduced scale when it will be shrunk anyway.
        target = _target_size(width, height)
        if fmt == "JPEG" and target != (width, height):
            im.draft(im.mode, target)

        # 4. Decode, and make the mode resizable.
        im.load()
        im = _normalise_mode(im)

        # 5. Downscale, never upscale.
        target = _target_size(*im.size)
        if target != im.size:
            im = im.resize(target, PILImage.Resampling.LANCZOS)

        # 6. Orientation, applied to the small image.
        if orientation in _ORIENTATION:
            im = im.transpose(_ORIENTATION[orientation])

        # 7. Drop an alpha channel no pixel uses.
        if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] == 255:
            im = im.convert("RGB")

        # 8. Encode (no EXIF, no ICC profile).
        out_fmt = _OUTPUT[fmt]
        if out_fmt != "JPEG" and im.mode == "L":
            im = im.convert("RGB")
        buf = io.BytesIO()
        if out_fmt == "JPEG":
            im.save(buf, "JPEG", quality=85, optimize=True)
        elif out_fmt == "PNG":
            im.save(buf, "PNG", optimize=True)
        else:
            im.save(buf, "WEBP", quality=85, method=6)
    except PILImage.DecompressionBombError as exc:
        raise UnprocessableError("Image has too many pixels") from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise UnprocessableError("Image is corrupt or truncated") from exc

    data = buf.getvalue()
    return ProcessedImage(
        data=data,
        content_type=_MEDIA_TYPES[out_fmt],
        width=im.width,
        height=im.height,
        sha256=hashlib.sha256(data).hexdigest(),
        filename=sanitize_filename(filename),
    )


def _target_size(width: int, height: int) -> tuple[int, int]:
    longest = max(width, height)
    if longest <= MAX_LONG_SIDE:
        return width, height
    scale = MAX_LONG_SIDE / longest
    return max(1, round(width * scale)), max(1, round(height * scale))


def _normalise_mode(im: PILImage.Image) -> PILImage.Image:
    """D2 step 4: end in L, RGB or RGBA (all of which resize with LANCZOS)."""
    if im.mode in _SIXTEEN_BIT:
        # Scale 0..65535 to 0..255. convert("L") alone would clip to white.
        return im.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    if im.mode in _ALPHA_MODES or "transparency" in im.info:
        return im.convert("RGBA")
    if im.mode not in ("L", "RGB"):
        return im.convert("RGB")
    return im


# ---------------------------------------------------------------------------
# Off-loop wrappers
# ---------------------------------------------------------------------------


async def run_image_job(fn: Callable[..., T], *args: Any) -> T:
    """Run CPU-heavy image work in the threadpool, one job at a time (D2)."""
    async with IMAGE_WORK:
        return await run_in_threadpool(fn, *args)


async def process_upload_async(raw: bytes, filename: str | None) -> ProcessedImage:
    return await run_image_job(process_upload, raw, filename)


# ---------------------------------------------------------------------------
# Filenames and HTTP helpers
# ---------------------------------------------------------------------------


#: Report thumbnails are at most this wide (D8).
THUMBNAIL_WIDTH = 480


def thumbnail_data_uri(
    data: bytes, content_type: str, max_width: int = THUMBNAIL_WIDTH
) -> str:
    """
    A small copy of a stored image as a data: URI, for the standalone report (D8):
    at most `max_width` wide (never upscaled), JPEG q80 when opaque, PNG otherwise.
    Stored images are already L, RGB or RGBA, with alpha only when it's used.
    """
    with PILImage.open(io.BytesIO(data)) as im:
        im.load()
        if im.width > max_width:
            height = max(1, round(im.height * max_width / im.width))
            im = im.resize((max_width, height), PILImage.Resampling.LANCZOS)
        buf = io.BytesIO()
        if "A" in im.getbands():
            im.save(buf, "PNG", optimize=True)
            media_type = "image/png"
        else:
            im.convert("RGB").save(buf, "JPEG", quality=80)
            media_type = "image/jpeg"
    return f"data:{media_type};base64," + base64.b64encode(buf.getvalue()).decode()


def sanitize_filename(name: str | None) -> str:
    """Display-only name: no path parts, control characters, quotes or backslashes."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(
        ch for ch in base if unicodedata.category(ch)[0] != "C" and ch not in '"\\'
    )
    return cleaned.strip()[:255] or "image"


def content_disposition(filename: str) -> str:
    """RFC 6266 / 5987 inline header with an ASCII fallback and the UTF-8 name."""
    fallback = "".join(
        ch if 32 <= ord(ch) < 127 and ch not in '"\\' else "_" for ch in filename
    )
    return (
        f"inline; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"
    )


def etag_matches(if_none_match: str | None, sha256: str) -> bool:
    """RFC 9110 weak comparison of If-None-Match against an image's ETag."""
    if not if_none_match:
        return False
    for item in if_none_match.split(","):
        tag = item.strip()
        if tag == "*":
            return True
        if tag.startswith("W/"):
            tag = tag[2:]
        if tag == f'"{sha256}"':
            return True
    return False


# ---------------------------------------------------------------------------
# Library (database) helpers — none of these commit; the request's get_db does
# ---------------------------------------------------------------------------

#: Room statuses that count as live (as content_service.delete_game uses them).
_LIVE_STATUSES = ("LOBBY", "IN_PROGRESS")
is_image_id = question_types.is_image_id
QUOTA_MESSAGE = (
    "This course's image library is full (200 MB). Delete unused images first."
)


async def read_bounded(file: UploadFile, limit: int, message: str) -> bytes:
    """Read at most `limit` bytes of an upload; anything longer is a 413."""
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLargeError(message)
    return data


async def course_bytes_used(db: AsyncSession, course_id: int) -> int:
    total = await db.execute(
        select(func.coalesce(func.sum(Image.byte_size), 0)).where(
            Image.course_id == course_id
        )
    )
    return int(total.scalar_one())


async def find_duplicate(db: AsyncSession, course_id: int, sha256: str) -> Image | None:
    """The oldest image in the course with these exact bytes (D2 dedupe)."""
    result = await db.execute(
        select(Image)
        .where(Image.course_id == course_id, Image.sha256 == sha256)
        .order_by(Image.created_at, Image.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_image(
    db: AsyncSession, course_id: int, user: User | None, processed: ProcessedImage
) -> tuple[Image, bool]:
    """Store a processed image: dedupe first, then the quota (D2 order). Flushes."""
    existing = await find_duplicate(db, course_id, processed.sha256)
    if existing is not None:
        return existing, False
    if (
        await course_bytes_used(db, course_id) + len(processed.data)
        > COURSE_QUOTA_BYTES
    ):
        raise ConflictError(QUOTA_MESSAGE)
    image = Image(
        id=uuid.uuid4().hex,
        course_id=course_id,
        filename=processed.filename,
        content_type=processed.content_type,
        data=processed.data,
        width=processed.width,
        height=processed.height,
        byte_size=len(processed.data),
        sha256=processed.sha256,
        uploaded_by=user.id if user is not None else None,
    )
    db.add(image)
    await db.flush()
    await db.refresh(image, ["created_at", "updated_at"])
    return image, True


async def lock_image(db: AsyncSession, image_id: str) -> Image:
    """
    End the request's snapshot, then take the image row FOR UPDATE (D6). Reads after
    this see every reference committed before the lock was granted.
    """
    await db.commit()
    image = (
        await db.execute(
            select(Image)
            .where(Image.id == image_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if image is None:
        raise NotFoundError("Image not found")
    return image


async def replace_image(
    db: AsyncSession, image: Image, processed: ProcessedImage
) -> Image:
    """Swap a (locked) image's bytes in place; the id stays. Flushes."""
    growth = len(processed.data) - image.byte_size
    if growth > 0:
        used = await course_bytes_used(db, image.course_id)
        if used + growth > COURSE_QUOTA_BYTES:
            raise ConflictError(QUOTA_MESSAGE)
    image.filename = processed.filename
    image.content_type = processed.content_type
    image.data = processed.data
    image.width = processed.width
    image.height = processed.height
    image.byte_size = len(processed.data)
    image.sha256 = processed.sha256
    image.updated_at = func.now(6)
    await _refresh_pin_drop_sizes(db, image)
    await db.flush()
    await db.refresh(image, ["created_at", "updated_at"])
    return image


async def _refresh_pin_drop_sizes(db: AsyncSession, image: Image) -> None:
    """pin_drop questions store their image's size for scoring; keep it current (D5)."""
    questions = (
        await db.execute(
            select(Question)
            .join(Game, Game.id == Question.game_id)
            .where(Game.course_id == image.course_id, Question.type == "pin_drop")
        )
    ).scalars()
    for question in questions:
        config = question.config or {}
        if question_types.referenced_image_ids(config)["pin_drop"] != image.id:
            continue
        # A new dict, so SQLAlchemy sees the JSON column change.
        question.config = {
            **config,
            "image": {
                "imageId": image.id,
                "width": image.width,
                "height": image.height,
            },
        }


async def delete_image(db: AsyncSession, image: Image) -> None:
    await db.delete(image)
    await db.flush()


async def usages_by_image(db: AsyncSession, course_id: int) -> dict[str, list[dict]]:
    """
    One scan of the course's questions → {image_id: [usage, ...]} (D6). One entry per
    (question, field); question_number is the 1-based rank the editor shows.
    """
    rows = await db.execute(
        select(Question.id, Question.game_id, Question.config, Game.title)
        .join(Game, Game.id == Question.game_id)
        .where(Game.course_id == course_id)
        .order_by(Question.game_id, Question.order_index, Question.id)
    )
    usages: dict[str, list[dict]] = {}
    rank: dict[int, int] = {}
    for row in rows:
        rank[row.game_id] = rank.get(row.game_id, 0) + 1
        refs = question_types.referenced_image_ids(row.config or {})
        fields = [("prompt", refs["prompt"]), ("pin_drop", refs["pin_drop"])]
        fields += [("option", image_id) for image_id in dict.fromkeys(refs["options"])]
        for field, image_id in fields:
            if image_id is None:
                continue
            entries = usages.setdefault(image_id, [])
            if any(e["question_id"] == row.id and e["field"] == field for e in entries):
                continue
            entries.append(
                {
                    "game_id": row.game_id,
                    "game_title": row.title,
                    "question_id": row.id,
                    "question_number": rank[row.game_id],
                    "field": field,
                }
            )
    return usages


async def image_usages(db: AsyncSession, image: Image) -> list[dict]:
    """Every question in the image's course that uses it."""
    return (await usages_by_image(db, image.course_id)).get(image.id, [])


async def live_games_using(db: AsyncSession, usages: list[dict]) -> set[int]:
    """The games among `usages` that have a LOBBY or IN_PROGRESS room."""
    game_ids = {u["game_id"] for u in usages}
    if not game_ids:
        return set()
    rows = await db.execute(
        select(GameSession.game_id)
        .where(
            GameSession.game_id.in_(game_ids),
            GameSession.status.in_(_LIVE_STATUSES),
        )
        .distinct()
    )
    return set(rows.scalars())


def question_count(usages: list[dict]) -> int:
    return len({u["question_id"] for u in usages})


def _titles(usages: list[dict]) -> str:
    return ", ".join(f"“{t}”" for t in dict.fromkeys(u["game_title"] for u in usages))


async def check_can_delete(db: AsyncSession, image: Image) -> None:
    """409 with `used_by` while any question references the image (D6)."""
    usages = await image_usages(db, image)
    if usages:
        n = question_count(usages)
        raise ConflictError(
            f"Image is used by {n} question{'s' if n != 1 else ''} in "
            f"{_titles(usages)} — remove it from them first",
            extra={"used_by": usages},
        )


async def check_can_replace(db: AsyncSession, image: Image) -> None:
    """409 while a game using the image has a live room — players may be on it (D6)."""
    usages = await image_usages(db, image)
    live = await live_games_using(db, usages)
    if live:
        live_usages = [u for u in usages if u["game_id"] in live]
        raise ConflictError(
            f"A live room of {_titles(live_usages)} is using this image — end it "
            "before replacing the image",
            extra={"used_by": live_usages},
        )


def image_response(image: Image, usages: list[dict]) -> dict:
    return {
        "id": image.id,
        "course_id": image.course_id,
        "filename": image.filename,
        "content_type": image.content_type,
        "width": image.width,
        "height": image.height,
        "byte_size": image.byte_size,
        "sha256": image.sha256,
        "created_at": image.created_at,
        "updated_at": image.updated_at,
        "url": f"/api/images/{image.id}",
        "used_by": usages,
    }
