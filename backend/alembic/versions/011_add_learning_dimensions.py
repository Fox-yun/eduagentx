"""add learning_dimensions to user_profiles

Revision ID: 011
Revises: 53a0e1a455be
Create Date: 2026-06-25 10:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: str | None = "53a0e1a455be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("learning_dimensions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_profiles", "learning_dimensions")
