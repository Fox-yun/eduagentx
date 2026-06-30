"""Add refresh_tokens table for proper token rotation.

Revision ID: 010
Revises: 009
Create Date: 2026-06-24
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "010"
down_revision = "009_task_worker"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create refresh_tokens table."""
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("auth_sessions.id"), nullable=False, index=True),
        sa.Column("token_family_id", sa.String(36), nullable=False, index=True),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("jti", sa.String(36), nullable=False, unique=True),
        sa.Column("parent_jti", sa.String(36), nullable=True),
        sa.Column("replaced_by_jti", sa.String(36), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Create indexes for efficient queries
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])


def downgrade() -> None:
    """Drop refresh_tokens table."""
    op.drop_table("refresh_tokens")
