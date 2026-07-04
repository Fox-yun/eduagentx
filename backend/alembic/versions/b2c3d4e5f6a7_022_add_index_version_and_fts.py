"""022 add index_version, content_hash, tsv to knowledge chunks; active_index_version to documents

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-04 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add index_version to knowledge_documents
    op.add_column(
        "knowledge_documents",
        sa.Column("active_index_version", sa.Integer(), nullable=True),
    )

    # Add index_version, content_hash, tsv to knowledge_chunks
    op.add_column(
        "knowledge_chunks",
        sa.Column("index_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "knowledge_chunks",
        sa.Column("tsv", TSVECTOR(), nullable=True),
    )

    # Index for efficient version-based queries
    op.create_index(
        "ix_knowledge_chunks_doc_version",
        "knowledge_chunks",
        ["document_id", "index_version"],
    )

    # GIN index for full-text search
    op.create_index(
        "ix_knowledge_chunks_tsv",
        "knowledge_chunks",
        ["tsv"],
        postgresql_using="gin",
    )

    # Backfill tsv for existing chunks
    op.execute("UPDATE knowledge_chunks SET tsv = to_tsvector('simple', content) WHERE tsv IS NULL")

    # Create trigger to auto-update tsv on INSERT/UPDATE
    op.execute(
        """
        CREATE OR REPLACE FUNCTION knowledge_chunks_tsv_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.tsv := to_tsvector('simple', COALESCE(NEW.content, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER knowledge_chunks_tsv_update
        BEFORE INSERT OR UPDATE OF content ON knowledge_chunks
        FOR EACH ROW EXECUTE FUNCTION knowledge_chunks_tsv_trigger();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS knowledge_chunks_tsv_update ON knowledge_chunks")
    op.execute("DROP FUNCTION IF EXISTS knowledge_chunks_tsv_trigger()")
    op.drop_index("ix_knowledge_chunks_tsv", table_name="knowledge_chunks")
    op.drop_index("ix_knowledge_chunks_doc_version", table_name="knowledge_chunks")
    op.drop_column("knowledge_chunks", "tsv")
    op.drop_column("knowledge_chunks", "content_hash")
    op.drop_column("knowledge_chunks", "index_version")
    op.drop_column("knowledge_documents", "active_index_version")
