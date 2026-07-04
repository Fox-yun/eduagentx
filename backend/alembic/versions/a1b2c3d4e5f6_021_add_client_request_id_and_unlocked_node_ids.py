"""021 add client_request_id and unlocked_node_ids to assessment_attempts

Revision ID: a1b2c3d4e5f6
Revises: e7f8a9b0c1d2
Create Date: 2026-07-03 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_attempts",
        sa.Column("client_request_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "assessment_attempts",
        sa.Column("unlocked_node_ids", sa.JSON(), nullable=True),
    )
    # Unique constraint for idempotent attempt creation
    # PostgreSQL treats NULLs as distinct, so multiple NULL client_request_id
    # entries are allowed (backward compatibility).
    op.create_unique_constraint(
        "uq_attempt_user_assessment_request",
        "assessment_attempts",
        ["user_id", "assessment_id", "client_request_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_attempt_user_assessment_request",
        "assessment_attempts",
        type_="unique",
    )
    op.drop_column("assessment_attempts", "unlocked_node_ids")
    op.drop_column("assessment_attempts", "client_request_id")
