"""add outbox retry fields

Revision ID: 53a0e1a455be
Revises: 010
Create Date: 2026-06-24 21:00:07.777031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "53a0e1a455be"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add retry-related columns to outbox_events
    op.add_column("outbox_events", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("outbox_events", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("outbox_events", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("outbox_events", sa.Column("last_error", sa.Text(), nullable=True))

    # Change payload from JSON to Text for consistency (JSON is fine too, but Text is more portable)
    # Skip this - leave as-is to avoid data loss


def downgrade() -> None:
    op.drop_column("outbox_events", "last_error")
    op.drop_column("outbox_events", "available_at")
    op.drop_column("outbox_events", "max_attempts")
    op.drop_column("outbox_events", "attempt_count")
