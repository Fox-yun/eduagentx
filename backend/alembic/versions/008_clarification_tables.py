"""Clarification tables

Revision ID: 008_clarification
Revises: 007_knowledge_base
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "008_clarification"
down_revision: str | None = "007_knowledge_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "goal_clarification_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("goal_id", sa.String(36), sa.ForeignKey("learning_goals.id"), nullable=False, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "goal_clarification_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("set_id", sa.String(36), sa.ForeignKey("goal_clarification_sets.id"), nullable=False, index=True),
        sa.Column("question_type", sa.String(20), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("min_value", sa.Integer(), nullable=True),
        sa.Column("max_value", sa.Integer(), nullable=True),
        sa.Column("question_order", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "goal_clarification_answers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("goal_clarification_questions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("goal_id", sa.String(36), sa.ForeignKey("learning_goals.id"), nullable=False, index=True),
        sa.Column("answer_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("goal_clarification_answers")
    op.drop_table("goal_clarification_questions")
    op.drop_table("goal_clarification_sets")
