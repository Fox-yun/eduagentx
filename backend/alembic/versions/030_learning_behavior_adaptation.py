"""Add learning behaviour events and learner-confirmed path adaptation proposals.

Revision ID: 030behavior
Revises: 029agenttrace
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "030behavior"
down_revision: str | None = "029agenttrace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("path_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("client_event_id", sa.String(length=100), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "client_event_id", name="uq_learning_event_user_client_id"),
    )
    op.create_index("ix_learning_events_user_id", "learning_events", ["user_id"])
    op.create_index("ix_learning_events_path_id", "learning_events", ["path_id"])
    op.create_index("ix_learning_events_node_id", "learning_events", ["node_id"])
    op.create_index("ix_learning_events_event_type", "learning_events", ["event_type"])

    op.create_table(
        "learning_path_adaptation_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("path_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_node_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("proposed_changes", sa.JSON(), nullable=False),
        sa.Column("revision_request_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"]),
        sa.ForeignKeyConstraint(["revision_request_id"], ["learning_path_revision_requests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_adaptation_proposals_user_id", "learning_path_adaptation_proposals", ["user_id"])
    op.create_index("ix_adaptation_proposals_path_id", "learning_path_adaptation_proposals", ["path_id"])
    op.create_index("ix_adaptation_proposals_trigger_node_id", "learning_path_adaptation_proposals", ["trigger_node_id"])
    op.create_index("ix_adaptation_proposals_status", "learning_path_adaptation_proposals", ["status"])


def downgrade() -> None:
    op.drop_table("learning_path_adaptation_proposals")
    op.drop_table("learning_events")
