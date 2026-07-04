"""024 add profile conversation tables

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-04 21:00:00.000000

Creates three new tables for the Phase 3.6 conversational 8-dimensional
learner profile:
  - student_profiles: versioned 8-dimensional profile per user
  - profile_conversation_sessions: multi-turn conversation sessions
  - profile_conversation_messages: individual messages in a session
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- student_profiles ---
    op.create_table(
        "student_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("profile_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("dimensions", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_student_profiles_user_id", "student_profiles", ["user_id"], unique=True)
    op.create_index("ix_student_profiles_status", "student_profiles", ["status"])

    # --- profile_conversation_sessions ---
    op.create_table(
        "profile_conversation_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("learning_goal_id", sa.String(36), sa.ForeignKey("learning_goals.id"), nullable=True),
        sa.Column("profile_id", sa.String(36), sa.ForeignKey("student_profiles.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("turn_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("extracted_dimensions", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("completion_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_profile_conversation_sessions_user_id", "profile_conversation_sessions", ["user_id"])
    op.create_index(
        "ix_profile_conversation_sessions_learning_goal_id", "profile_conversation_sessions", ["learning_goal_id"]
    )
    op.create_index("ix_profile_conversation_sessions_profile_id", "profile_conversation_sessions", ["profile_id"])
    op.create_index("ix_profile_conversation_sessions_status", "profile_conversation_sessions", ["status"])

    # --- profile_conversation_messages ---
    op.create_table(
        "profile_conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("profile_conversation_sessions.id"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("extracted_signals", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_profile_conversation_messages_session_id", "profile_conversation_messages", ["session_id"])


def downgrade() -> None:
    op.drop_table("profile_conversation_messages")
    op.drop_table("profile_conversation_sessions")
    op.drop_table("student_profiles")
