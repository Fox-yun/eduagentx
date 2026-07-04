"""025 add learning_goal_text and target_context to profile_conversation_sessions

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-05 10:00:00.000000

Adds two nullable TEXT columns to ``profile_conversation_sessions`` so that
the user's original learning goal and optional target context are persisted
on the session row — eliminating the need to reverse-engineer the goal from
the first assistant message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile_conversation_sessions",
        sa.Column("learning_goal_text", sa.Text, nullable=True),
    )
    op.add_column(
        "profile_conversation_sessions",
        sa.Column("target_context", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profile_conversation_sessions", "target_context")
    op.drop_column("profile_conversation_sessions", "learning_goal_text")
