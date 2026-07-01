"""017 enhance assessment models for Phase 3.5

Adds purpose/active_task_id to assessments for background generation.
Adds difficulty, knowledge_point, explanation, reference_answer, rubric,
max_score to assessment_questions for structured question contracts.

Revision ID: 017_enhance_assessment_models
Revises: 356527c10db9
Create Date: 2026-07-01 00:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_enhance_assessment_models"
down_revision: Union[str, None] = "356527c10db9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- assessments ---
    op.add_column(
        "assessments",
        sa.Column("purpose", sa.String(20), nullable=False, server_default="quiz_bank"),
    )
    op.add_column(
        "assessments",
        sa.Column("active_task_id", sa.String(36), nullable=True),
    )
    op.create_index("ix_assessments_active_task_id", "assessments", ["active_task_id"])

    # --- assessment_questions ---
    op.add_column(
        "assessment_questions",
        sa.Column("difficulty", sa.String(10), nullable=True),
    )
    op.add_column(
        "assessment_questions",
        sa.Column("knowledge_point", sa.String(500), nullable=True),
    )
    op.add_column(
        "assessment_questions",
        sa.Column("explanation", sa.Text(), nullable=True),
    )
    op.add_column(
        "assessment_questions",
        sa.Column("reference_answer", sa.Text(), nullable=True),
    )
    op.add_column(
        "assessment_questions",
        sa.Column("rubric", sa.JSON(), nullable=True),
    )
    op.add_column(
        "assessment_questions",
        sa.Column("max_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    # --- assessment_questions ---
    op.drop_column("assessment_questions", "max_score")
    op.drop_column("assessment_questions", "rubric")
    op.drop_column("assessment_questions", "reference_answer")
    op.drop_column("assessment_questions", "explanation")
    op.drop_column("assessment_questions", "knowledge_point")
    op.drop_column("assessment_questions", "difficulty")

    # --- assessments ---
    op.drop_index("ix_assessments_active_task_id", table_name="assessments")
    op.drop_column("assessments", "active_task_id")
    op.drop_column("assessments", "purpose")
