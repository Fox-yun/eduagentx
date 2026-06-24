"""Knowledge base tables

Revision ID: 007_knowledge_base
Revises: 006_unit_assessment_progress
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_knowledge_base"
down_revision: str | None = "006_unit_assessment_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Knowledge documents
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("scope", sa.String(20), nullable=False, server_default="personal"),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploaded", index=True),
        sa.Column("operation_status", sa.String(20), nullable=False, server_default="idle"),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("index_task_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Knowledge chunks
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(200), nullable=True),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
