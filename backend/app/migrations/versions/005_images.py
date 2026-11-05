"""Course image library (T8)

Revision ID: 005
Revises: 004
Create Date: 2026-10-06

Images are stored entirely in the database (MEDIUMBLOB, ≤ 16 MB; uploads are
re-encoded to ≤ 1600 px first). Each belongs to one course; there is no course
deletion, so course_id has no cascade. uploaded_by is SET NULL so deleting a user
never blocks on their uploads. See docs/plans/t8-image-support.md.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("course_id", sa.Integer, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("data", mysql.MEDIUMBLOB, nullable=False),
        sa.Column("width", sa.Integer, nullable=False),
        sa.Column("height", sa.Integer, nullable=False),
        sa.Column("byte_size", sa.Integer, nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column(
            "uploaded_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_images_course_sha256", "images", ["course_id", "sha256"])


def downgrade() -> None:
    # Dropping the table drops its indexes; dropping ix_images_course_sha256 first
    # fails (MySQL 1553) because the course_id foreign key relies on it.
    op.drop_table("images")
