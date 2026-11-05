from __future__ import annotations

from datetime import datetime

from sqlalchemy import CHAR, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.mysql import DATETIME, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Image(Base):
    """
    An image in a course's library (T8). The bytes are re-encoded by
    services/image_service.py and stored here — never on disk.

    `data` is deferred with raiseload: async SQLAlchemy can't lazy-load, so every
    path that needs the bytes must select them explicitly (`undefer(Image.data)` or
    selecting the column); an accidental access raises a clear error.
    """

    __tablename__ = "images"
    __table_args__ = (Index("ix_images_course_sha256", "course_id", "sha256"),)

    id: Mapped[str] = mapped_column(CHAR(32), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[bytes] = mapped_column(
        MEDIUMBLOB, nullable=False, deferred=True, deferred_raiseload=True
    )
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    uploaded_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Microseconds (migration 006): dedupe picks the *oldest* copy, so uploads in the
    # same second must still be ordered.
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), server_default=func.now(6)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=6), server_default=func.now(6), onupdate=func.now(6)
    )
