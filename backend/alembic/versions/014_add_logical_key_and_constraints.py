"""add logical_key to learning_nodes, enhance revision request constraints

Revision ID: 014
Revises: 013
Create Date: 2026-06-30 14:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Add logical_key to learning_nodes for stable cross-version identification
    op.add_column("learning_nodes", sa.Column("logical_key", sa.String(100), nullable=True))
    op.create_index(
        "ix_learning_nodes_version_logical_key", "learning_nodes", ["version_id", "logical_key"], unique=True
    )

    # Make source_version_id NOT NULL on revision requests
    op.alter_column("learning_path_revision_requests", "source_version_id", existing_type=sa.String(36), nullable=False)

    # Add index on (path_id, status) for efficient active revision lookup
    op.create_index(
        "ix_revision_requests_path_status",
        "learning_path_revision_requests",
        ["path_id", "status"],
    )

    # Add index on task_id for efficient join lookups
    op.create_index("ix_revision_requests_task_id", "learning_path_revision_requests", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_revision_requests_task_id", table_name="learning_path_revision_requests")
    op.drop_index("ix_revision_requests_path_status", table_name="learning_path_revision_requests")
    op.alter_column("learning_path_revision_requests", "source_version_id", existing_type=sa.String(36), nullable=True)
    op.drop_index("ix_learning_nodes_version_logical_key", table_name="learning_nodes")
    op.drop_column("learning_nodes", "logical_key")
