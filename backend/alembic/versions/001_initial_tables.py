"""Initial tables: idempotency_records, outbox_events

Revision ID: 001_initial
Revises: None
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotency records table
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("user_id", sa.String(36), nullable=True, index=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )

    # Outbox events table
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("idempotency_records")
