"""create diagnostic scoring tables (questions, attempts, answers, results)

Revision ID: 012
Revises: 011
Create Date: 2026-06-29 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostic_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("diagnostic_id", sa.String(36), nullable=False, index=True),
        sa.Column("question_type", sa.String(30), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("options", sa.JSON, nullable=True),
        sa.Column("correct_answer", sa.JSON, nullable=True),
        sa.Column("rubric", sa.Text, nullable=True),
        sa.Column("dimension", sa.String(100), nullable=True),
        sa.Column("difficulty", sa.String(30), nullable=True),
        sa.Column("max_score", sa.Float, nullable=False, server_default=sa.text("10.0")),
        sa.Column("sequence", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("required", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "diagnostic_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("diagnostic_id", sa.String(36), nullable=False, index=True),
        sa.Column("goal_id", sa.String(36), sa.ForeignKey("learning_goals.id"), nullable=False, index=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'"), index=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grading_quality", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_diagnostic_attempts_user_goal", "diagnostic_attempts", ["user_id", "goal_id"])

    op.create_table(
        "diagnostic_answers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("attempt_id", sa.String(36), sa.ForeignKey("diagnostic_attempts.id"), nullable=False, index=True),
        sa.Column("question_id", sa.String(36), nullable=False),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("score", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("max_score", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("is_correct", sa.Boolean, nullable=True),
        sa.Column("feedback", sa.Text, nullable=True),
        sa.Column("grading_source", sa.String(20), nullable=True),
        sa.Column("grading_status", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("attempt_id", "question_id", name="uq_diagnostic_answer_attempt_question"),
    )

    op.create_table(
        "diagnostic_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.String(36),
            sa.ForeignKey("diagnostic_attempts.id"),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column("total_score", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("percentage", sa.Float, nullable=False, server_default=sa.text("0.0")),
        sa.Column("dimension_scores", sa.JSON, nullable=True),
        sa.Column("strong_areas", sa.JSON, nullable=True),
        sa.Column("weak_areas", sa.JSON, nullable=True),
        sa.Column("readiness_level", sa.String(20), nullable=True),
        sa.Column("grading_quality", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("attempt_id", name="uq_diagnostic_result_attempt"),
    )


def downgrade() -> None:
    op.drop_table("diagnostic_results")
    op.drop_table("diagnostic_answers")
    op.drop_index("ix_diagnostic_attempts_user_goal", table_name="diagnostic_attempts")
    op.drop_table("diagnostic_attempts")
    op.drop_table("diagnostic_questions")
