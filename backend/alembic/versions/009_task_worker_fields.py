"""Add worker fields to background_tasks

Revision ID: 009_task_worker
Revises: 008_clarification
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_task_worker"
down_revision: str | None = "008_clarification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "background_tasks",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "background_tasks",
        sa.Column("next_event_sequence", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "background_tasks",
        sa.Column("worker_id", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("background_tasks", "worker_id")
    op.drop_column("background_tasks", "next_event_sequence")
    op.drop_column("background_tasks", "heartbeat_at")
