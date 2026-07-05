"""Add recommendation_feedback table.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-05

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False, index=True),
        sa.Column("recommendation_key", sa.String(100), nullable=False),
        sa.Column("recommendation_type", sa.String(30), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "recommendation_key",
            name="uq_recommendation_feedback_user_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("recommendation_feedback")
