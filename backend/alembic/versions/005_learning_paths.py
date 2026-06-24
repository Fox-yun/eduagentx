"""Learning paths, versions, stages, nodes, edges

Revision ID: 005_learning_paths
Revises: 004_background_tasks
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "005_learning_paths"
down_revision: str | None = "004_background_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_paths",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("goal_id", sa.String(36), sa.ForeignKey("learning_goals.id"), nullable=False, index=True),
        sa.Column("active_version_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "learning_path_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False, index=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(36), nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default="initial_generation"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("estimated_total_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("generation_metadata", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="system"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "learning_stages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("learning_path_versions.id"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=True),
    )

    op.create_table(
        "learning_nodes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("learning_path_versions.id"), nullable=False, index=True),
        sa.Column("stage_id", sa.String(36), sa.ForeignKey("learning_stages.id"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("node_order", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("difficulty", sa.String(20), nullable=False, server_default="beginner"),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(20), nullable=False, server_default="locked"),
        sa.Column("mastery", sa.Float(), nullable=False, server_default="0"),
        sa.Column("content_status", sa.String(20), nullable=False, server_default="not_generated"),
        sa.Column("learning_outcomes", sa.Text(), nullable=True),
        sa.Column("assessment_strategy", sa.Text(), nullable=True),
        sa.Column("generation_reason", sa.Text(), nullable=True),
    )

    op.create_table(
        "learning_edges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), sa.ForeignKey("learning_path_versions.id"), nullable=False, index=True),
        sa.Column("source_node_id", sa.String(36), nullable=False),
        sa.Column("target_node_id", sa.String(36), nullable=False),
    )

    op.create_table(
        "learning_path_revision_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("revision_request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("learning_path_revision_requests")
    op.drop_table("learning_edges")
    op.drop_table("learning_nodes")
    op.drop_table("learning_stages")
    op.drop_table("learning_path_versions")
    op.drop_table("learning_paths")
