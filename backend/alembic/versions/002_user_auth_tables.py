"""User and auth tables

Revision ID: 002_user_auth
Revises: 001_initial
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002_user_auth"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("email_normalized", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_verification"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # User profiles table
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(30), nullable=False, server_default="student"),
        sa.Column("preferred_language", sa.String(10), nullable=False, server_default="zh"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("weekly_hours", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("learning_interests", sa.Text(), nullable=True),
        sa.Column("learning_preferences", sa.Text(), nullable=True),
        sa.Column("use_diagnostic", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("use_knowledge_base", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Auth sessions table
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("refresh_token_hash", sa.String(255), nullable=False),
        sa.Column("refresh_token_jti", sa.String(36), unique=True, nullable=False),
        sa.Column("token_family_id", sa.String(36), nullable=False, index=True),
        sa.Column("previous_refresh_jti", sa.String(36), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("device_name", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(100), nullable=True),
    )

    # Verification tokens table
    op.create_table(
        "verification_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Auth audit logs table
    op.create_table(
        "auth_audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("event_type", sa.String(50), nullable=False, index=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("session_id", sa.String(36), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("auth_audit_logs")
    op.drop_table("verification_tokens")
    op.drop_table("auth_sessions")
    op.drop_table("user_profiles")
    op.drop_table("users")
