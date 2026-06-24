"""Background tasks and task events

Revision ID: 004_background_tasks
Revises: 003_learning_goals
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "004_background_tasks"
down_revision: str | None = "003_learning_goals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("task_type", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending", index=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_stage", sa.String(100), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("target_metadata", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("idempotency_key", sa.String(255), unique=True, nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "task_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("background_tasks.id"), nullable=False, index=True),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(100), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("task_id", "sequence_number", name="uq_task_event_sequence"),
    )


def downgrade() -> None:
    op.drop_table("task_events")
    op.drop_table("background_tasks")
