"""Question feedback: a player's thumbs up/down and "hard" flag per question

Revision ID: 007
Revises: 006
Create Date: 2026-10-07

One row per (session, question, player). Every foreign key cascades on delete, so
deleting a session, question or user removes its feedback without changes to those
delete paths (docs/plans/question-feedback.md §4.1).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("game_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id",
            sa.Integer(),
            sa.ForeignKey("questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rating", sa.Enum("UP", "DOWN", name="feedback_rating"), nullable=True
        ),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "session_id",
            "question_id",
            "user_id",
            name="uq_feedback_session_question_user",
        ),
    )
    op.create_index(
        "ix_feedback_session_question",
        "question_feedback",
        ["session_id", "question_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_session_question", table_name="question_feedback")
    op.drop_table("question_feedback")
