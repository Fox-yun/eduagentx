"""019 finalization fields and profile evidence

Revision ID: c6b759223c19
Revises: c135eb0b510e
Create Date: 2026-07-01 14:45:38.395059
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = "c6b759223c19"
down_revision: str | None = "c135eb0b510e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # AssessmentAttempt finalization fields
    op.add_column("assessment_attempts", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assessment_attempts", sa.Column("progress_applied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("assessment_attempts", sa.Column("mastery_before", sa.Float(), nullable=True))
    op.add_column("assessment_attempts", sa.Column("mastery_after", sa.Float(), nullable=True))

    # StudentProfileEvidence table
    op.create_table(
        "student_profile_evidence",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("dimension", sa.String(50), nullable=False),
        sa.Column("evidence_type", sa.String(50), nullable=False),
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("metadata", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_student_profile_evidence_user_id")),
        sa.UniqueConstraint("evidence_type", "evidence_id", "dimension", name="uq_evidence_per_dimension"),
    )
    op.create_index(
        op.f("ix_student_profile_evidence_user_id"),
        "student_profile_evidence",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    # StudentProfileEvidence
    op.drop_index(op.f("ix_student_profile_evidence_user_id"), table_name="student_profile_evidence")
    op.drop_table("student_profile_evidence")

    # AssessmentAttempt
    op.drop_column("assessment_attempts", "mastery_after")
    op.drop_column("assessment_attempts", "mastery_before")
    op.drop_column("assessment_attempts", "progress_applied_at")
    op.drop_column("assessment_attempts", "finalized_at")
