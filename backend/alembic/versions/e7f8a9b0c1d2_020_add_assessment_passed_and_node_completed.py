"""020 add assessment_passed and node_completed columns

Revision ID: e7f8a9b0c1d2
Revises: c6b759223c19
Create Date: 2026-07-01 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "c6b759223c19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_attempts",
        sa.Column("assessment_passed", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "assessment_attempts",
        sa.Column("node_completed", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assessment_attempts", "node_completed")
    op.drop_column("assessment_attempts", "assessment_passed")
