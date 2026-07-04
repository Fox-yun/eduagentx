"""018 enhance attempt and answer models

Revision ID: c135eb0b510e
Revises: 017_enhance_assessment_models
Create Date: 2026-07-01 14:15:34.422990
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c135eb0b510e"
down_revision: str | None = "017_enhance_assessment_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # AssessmentAttempt new fields
    op.add_column("assessment_attempts", sa.Column("grading_quality", sa.String(length=20), nullable=True))
    op.add_column("assessment_attempts", sa.Column("active_task_id", sa.String(length=36), nullable=True))
    op.create_index(
        op.f("ix_assessment_attempts_active_task_id"), "assessment_attempts", ["active_task_id"], unique=False
    )

    # AssessmentAnswer new fields
    op.add_column("assessment_answers", sa.Column("max_score", sa.Float(), nullable=True))
    op.add_column("assessment_answers", sa.Column("grading_source", sa.String(length=20), nullable=True))
    op.add_column("assessment_answers", sa.Column("grading_status", sa.String(length=20), nullable=True))
    op.create_unique_constraint("uq_answer_per_question", "assessment_answers", ["attempt_id", "question_id"])


def downgrade() -> None:
    # AssessmentAnswer
    op.drop_constraint("uq_answer_per_question", "assessment_answers", type_="unique")
    op.drop_column("assessment_answers", "grading_status")
    op.drop_column("assessment_answers", "grading_source")
    op.drop_column("assessment_answers", "max_score")

    # AssessmentAttempt
    op.drop_index(op.f("ix_assessment_attempts_active_task_id"), table_name="assessment_attempts")
    op.drop_column("assessment_attempts", "active_task_id")
    op.drop_column("assessment_attempts", "grading_quality")
