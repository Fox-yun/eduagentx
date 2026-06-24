"""Learning goals table

Revision ID: 003_learning_goals
Revises: 002_user_auth
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "003_learning_goals"
down_revision: str | None = "002_user_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_goals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("normalized_goal", sa.Text(), nullable=True),
        sa.Column("current_level", sa.String(50), nullable=True),
        sa.Column("target_level", sa.String(50), nullable=True),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weekly_hours", sa.Integer(), nullable=True),
        sa.Column("preferences", sa.Text(), nullable=True),
        sa.Column("use_diagnostic", sa.Boolean(), server_default="true"),
        sa.Column("use_knowledge_base", sa.Boolean(), server_default="false"),
        sa.Column("content_language", sa.String(10), server_default="zh"),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft", index=True),
        sa.Column("active_task_id", sa.String(36), nullable=True),
        sa.Column("current_path_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("learning_goals")
