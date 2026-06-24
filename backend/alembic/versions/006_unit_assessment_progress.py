"""Unit content, assessment, progress, mastery

Revision ID: 006_unit_assessment_progress
Revises: 005_learning_paths
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "006_unit_assessment_progress"
down_revision: str | None = "005_learning_paths"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Learning unit contents
    op.create_table(
        "learning_unit_contents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False, index=True),
        sa.Column("path_version_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=False, index=True),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_generated"),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("generation_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Assessments
    op.create_table(
        "assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False, index=True),
        sa.Column("path_version_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Assessment questions
    op.create_table(
        "assessment_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("assessments.id"), nullable=False, index=True),
        sa.Column("question_type", sa.String(30), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("correct_answer", sa.Text(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("question_order", sa.Integer(), nullable=False, server_default="0"),
    )

    # Assessment attempts
    op.create_table(
        "assessment_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("assessments.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("weak_concepts", sa.JSON(), nullable=True),
        sa.Column("explanations", sa.JSON(), nullable=True),
        sa.Column("recommended_actions", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Assessment answers
    op.create_table(
        "assessment_answers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("assessment_attempts.id"), nullable=False, index=True),
        sa.Column("question_id", sa.String(36), sa.ForeignKey("assessment_questions.id"), nullable=False),
        sa.Column("answer_value", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("points_earned", sa.Float(), nullable=False, server_default="0"),
        sa.Column("feedback", sa.Text(), nullable=True),
    )

    # Learning progress
    op.create_table(
        "learning_progress",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False, index=True),
        sa.Column("node_id", sa.String(36), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="locked"),
        sa.Column("mastery", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Mastery snapshots
    op.create_table(
        "mastery_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("node_id", sa.String(36), nullable=False, index=True),
        sa.Column("old_mastery", sa.Float(), nullable=False),
        sa.Column("new_mastery", sa.Float(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("source_type", sa.String(30), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Recommendations
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=True),
        sa.Column("recommendation_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("mastery_snapshots")
    op.drop_table("learning_progress")
    op.drop_table("assessment_answers")
    op.drop_table("assessment_attempts")
    op.drop_table("assessment_questions")
    op.drop_table("assessments")
    op.drop_table("learning_unit_contents")
