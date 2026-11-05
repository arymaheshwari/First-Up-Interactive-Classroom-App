"""Course-scoped games, per-course guest policy, guest session binding

Revision ID: 004
Revises: 003
Create Date: 2026-09-25

Existing courses get guest_policy OPEN (today's behavior); new courses default to
ROSTER_ONLY. Each existing game is attached to the course it was played in most often
(ties -> lowest course id); games never played go to an "Unassigned" course (created here
if it doesn't already exist).

Downgrade leaves the "Unassigned" course row in place; a later upgrade reuses it.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GUEST_POLICY = sa.Enum("ROSTER_ONLY", "OPEN", "DISABLED", name="guest_policy")


def upgrade() -> None:
    op.add_column("courses", sa.Column("guest_policy", _GUEST_POLICY, nullable=True))
    op.execute("UPDATE courses SET guest_policy = 'OPEN'")
    op.alter_column(
        "courses",
        "guest_policy",
        existing_type=_GUEST_POLICY,
        nullable=False,
        server_default="ROSTER_ONLY",
    )

    op.add_column("users", sa.Column("guest_session_id", sa.String(36), nullable=True))

    op.add_column("games", sa.Column("course_id", sa.Integer(), nullable=True))
    op.create_index("ix_games_course_id", "games", ["course_id"])
    op.create_foreign_key(
        "fk_games_course_id", "games", "courses", ["course_id"], ["id"]
    )

    conn = op.get_bind()
    best: dict[int, tuple[int, int]] = {}
    for game_id, course_id, plays in conn.execute(
        sa.text(
            "SELECT game_id, course_id, COUNT(*) FROM game_sessions "
            "GROUP BY game_id, course_id"
        )
    ):
        current = best.get(game_id)
        if (
            current is None
            or plays > current[1]
            or (plays == current[1] and course_id < current[0])
        ):
            best[game_id] = (course_id, plays)
    for game_id, (course_id, _) in best.items():
        conn.execute(
            sa.text("UPDATE games SET course_id = :course WHERE id = :game"),
            {"course": course_id, "game": game_id},
        )

    unplayed = conn.execute(
        sa.text("SELECT COUNT(*) FROM games WHERE course_id IS NULL")
    ).scalar()
    if unplayed:
        unassigned_id = conn.execute(
            sa.text(
                "SELECT id FROM courses WHERE name = 'Unassigned' AND semester = 'N/A' "
                "ORDER BY id LIMIT 1"
            )
        ).scalar()
        if unassigned_id is None:
            conn.execute(
                sa.text(
                    "INSERT INTO courses (name, semester, guest_policy) "
                    "VALUES ('Unassigned', 'N/A', 'DISABLED')"
                )
            )
            unassigned_id = conn.execute(sa.text("SELECT LAST_INSERT_ID()")).scalar()
        conn.execute(
            sa.text("UPDATE games SET course_id = :course WHERE course_id IS NULL"),
            {"course": unassigned_id},
        )

    op.alter_column("games", "course_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_games_course_id", "games", type_="foreignkey")
    op.drop_index("ix_games_course_id", table_name="games")
    op.drop_column("games", "course_id")
    op.drop_column("users", "guest_session_id")
    op.drop_column("courses", "guest_policy")
