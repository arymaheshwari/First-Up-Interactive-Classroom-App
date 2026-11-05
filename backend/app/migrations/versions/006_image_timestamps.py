"""Microsecond timestamps on images (T8)

Revision ID: 006
Revises: 005
Create Date: 2026-10-06

Dedupe sends a re-upload to the *oldest* image with the same bytes, ordered by
(created_at, id). With whole-second DATETIMEs, two uploads in the same second tied
and the random id decided. DATETIME(6) keeps them in upload order.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in ("created_at", "updated_at"):
        op.alter_column(
            "images",
            column,
            existing_type=mysql.DATETIME(),
            type_=mysql.DATETIME(fsp=6),
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
            existing_nullable=True,
        )


def downgrade() -> None:
    for column in ("created_at", "updated_at"):
        op.alter_column(
            "images",
            column,
            existing_type=mysql.DATETIME(fsp=6),
            type_=mysql.DATETIME(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            existing_nullable=True,
        )
