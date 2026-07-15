"""Add concurrency constraints for diagnostic question caching.

Revision ID: 028diagcache
Revises: 010203040506
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "028diagcache"
down_revision: str | None = "010203040506"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep one cached question per sequence before enforcing uniqueness.
    op.execute(
        """
        DELETE FROM diagnostic_questions AS question
        USING diagnostic_questions AS duplicate
        WHERE question.diagnostic_id = duplicate.diagnostic_id
          AND question.sequence = duplicate.sequence
          AND question.id > duplicate.id
        """
    )
    op.create_unique_constraint(
        "uq_diagnostic_question_sequence",
        "diagnostic_questions",
        ["diagnostic_id", "sequence"],
    )

    # Retain the newest active attempt and close older duplicates.
    op.execute(
        """
        WITH ranked_attempts AS (
            SELECT id,
                   row_number() OVER (
                       PARTITION BY user_id, goal_id
                       ORDER BY created_at DESC, id DESC
                   ) AS row_number
            FROM diagnostic_attempts
            WHERE status IN ('draft', 'submitted', 'grading')
        )
        UPDATE diagnostic_attempts AS attempt
        SET status = 'failed', updated_at = now()
        FROM ranked_attempts AS ranked
        WHERE attempt.id = ranked.id AND ranked.row_number > 1
        """
    )
    op.create_index(
        "uq_diagnostic_attempt_active_user_goal",
        "diagnostic_attempts",
        ["user_id", "goal_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('draft', 'submitted', 'grading')"),
    )


def downgrade() -> None:
    op.drop_index("uq_diagnostic_attempt_active_user_goal", table_name="diagnostic_attempts")
    op.drop_constraint(
        "uq_diagnostic_question_sequence",
        "diagnostic_questions",
        type_="unique",
    )
