"""extend learning_path_revision_requests with task tracking fields

Revision ID: 013
Revises: 012
Create Date: 2026-06-30 10:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("learning_path_revision_requests", sa.Column("task_id", sa.String(36), nullable=True, unique=True))
    op.add_column("learning_path_revision_requests", sa.Column("source_version_id", sa.String(36), nullable=True))
    op.add_column("learning_path_revision_requests", sa.Column("generated_version_id", sa.String(36), nullable=True))
    op.add_column("learning_path_revision_requests", sa.Column("error", sa.Text(), nullable=True))
    op.add_column(
        "learning_path_revision_requests",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "learning_path_revision_requests",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "learning_path_revision_requests",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_revision_task_id", "learning_path_revision_requests", ["task_id"])
    op.create_unique_constraint(
        "uq_revision_generated_version_id", "learning_path_revision_requests", ["generated_version_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_revision_generated_version_id", "learning_path_revision_requests", type_="unique")
    op.drop_constraint("uq_revision_task_id", "learning_path_revision_requests", type_="unique")
    op.drop_column("learning_path_revision_requests", "updated_at")
    op.drop_column("learning_path_revision_requests", "completed_at")
    op.drop_column("learning_path_revision_requests", "started_at")
    op.drop_column("learning_path_revision_requests", "error")
    op.drop_column("learning_path_revision_requests", "generated_version_id")
    op.drop_column("learning_path_revision_requests", "source_version_id")
    op.drop_column("learning_path_revision_requests", "task_id")
