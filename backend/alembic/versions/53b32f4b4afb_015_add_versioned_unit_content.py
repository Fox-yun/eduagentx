"""015 add versioned unit content and resources

Creates LearningUnitContentVersion table and adds versioning fields
to LearningUnitContent. Existing content is backfilled as Version 1.

Migration order (to avoid circular FK):
  1. Create learning_unit_content_versions (FK → learning_unit_contents)
  2. Add columns to learning_unit_contents (no FK initially)
  3. Change node_id to UNIQUE
  4. Backfill existing content as Version 1
  5. Set active_version_id on each unit content
  6. Add FK constraint on active_version_id

Revision ID: 53b32f4b4afb
Revises: 014
Create Date: 2026-06-30 18:41:51.920772
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "53b32f4b4afb"
down_revision: str | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: Create version table (FK to unit_contents, which already exists)
    op.create_table(
        "learning_unit_content_versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("unit_content_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="generating"),
        sa.Column("source", sa.String(20), nullable=False, server_default="llm"),
        sa.Column("quality_status", sa.String(20), nullable=False, server_default="final"),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("generation_metadata", sa.JSON(), nullable=True),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["unit_content_id"],
            ["learning_unit_contents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
        sa.UniqueConstraint("unit_content_id", "version_number", name="uq_version_per_content"),
    )
    op.create_index(
        op.f("ix_learning_unit_content_versions_unit_content_id"),
        "learning_unit_content_versions",
        ["unit_content_id"],
        unique=False,
    )

    # Step 2: Add new columns to learning_unit_contents (no FK yet)
    op.add_column(
        "learning_unit_contents",
        sa.Column("active_task_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "learning_unit_contents",
        sa.Column("active_version_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "learning_unit_contents",
        sa.Column("last_error_code", sa.String(50), nullable=True),
    )
    op.add_column(
        "learning_unit_contents",
        sa.Column("last_error_message", sa.Text(), nullable=True),
    )

    # Step 3: Change node_id index to UNIQUE
    op.drop_index("ix_learning_unit_contents_node_id", table_name="learning_unit_contents")
    op.create_index(
        op.f("ix_learning_unit_contents_node_id"),
        "learning_unit_contents",
        ["node_id"],
        unique=True,
    )

    # Step 4: Backfill existing ready content as Version 1
    connection = op.get_bind()
    _backfill_versions(connection)

    # Step 5: Add FK constraint on active_version_id
    op.create_foreign_key(
        "fk_active_version",
        "learning_unit_contents",
        "learning_unit_content_versions",
        ["active_version_id"],
        ["id"],
    )


def downgrade() -> None:
    # Reverse order
    # Drop FK
    op.drop_constraint("fk_active_version", "learning_unit_contents", type_="foreignkey")

    # Clear active_version_id
    op.execute("UPDATE learning_unit_contents SET active_version_id = NULL")

    # Delete backfilled versions
    op.execute("DELETE FROM learning_unit_content_versions")

    # Drop added columns
    op.drop_column("learning_unit_contents", "last_error_message")
    op.drop_column("learning_unit_contents", "last_error_code")
    op.drop_column("learning_unit_contents", "active_version_id")
    op.drop_column("learning_unit_contents", "active_task_id")

    # Restore node_id index to non-unique
    op.drop_index("ix_learning_unit_contents_node_id", table_name="learning_unit_contents")
    op.create_index(
        op.f("ix_learning_unit_contents_node_id"),
        "learning_unit_contents",
        ["node_id"],
        unique=False,
    )

    # Drop version table
    op.drop_index(
        op.f("ix_learning_unit_content_versions_unit_content_id"),
        table_name="learning_unit_content_versions",
    )
    op.drop_table("learning_unit_content_versions")


def _backfill_versions(connection) -> None:
    """Backfill existing unit content as Version 1.

    Rules:
      - status = 'ready' and content IS NOT NULL → create Version 1, set active_version_id
      - status = 'generating'/'regenerating' with non-null content → create as 'ready'
      - status = 'failed', 'not_generated', or null content → no version created
    """
    import uuid
    from datetime import datetime

    rows = connection.execute(
        sa.text(
            "SELECT id, content, version_number, generation_metadata, created_at, status "
            "FROM learning_unit_contents "
            "WHERE content IS NOT NULL "
            "AND status IN ('ready', 'generating', 'regenerating')"
        )
    ).fetchall()

    if not rows:
        return

    version_rows = []
    update_pairs = []

    for row in rows:
        if row.status in ("generating", "regenerating"):
            version_status = "ready"
            source = "llm"
        else:
            version_status = "ready"
            source = "llm"

        version_id = str(uuid.uuid4())
        vnum = row.version_number if row.version_number and row.version_number >= 1 else 1

        # Use the original created_at or now; ensure no tz for naive DB columns
        created = row.created_at.replace(tzinfo=None) if row.created_at else datetime.utcnow()

        version_rows.append(
            {
                "id": version_id,
                "unit_content_id": row.id,
                "version_number": vnum,
                "status": version_status,
                "source": source,
                "quality_status": "final",
                "content": row.content,
                "generation_metadata": row.generation_metadata,
                "task_id": None,
                "error_code": None,
                "error_message": None,
                "created_at": created,
                "completed_at": created,
                "activated_at": created,
            }
        )
        update_pairs.append((version_id, row.id))

    # Batch insert versions
    stmt = sa.insert(
        sa.table(
            "learning_unit_content_versions",
            sa.column("id", sa.String),
            sa.column("unit_content_id", sa.String),
            sa.column("version_number", sa.Integer),
            sa.column("status", sa.String),
            sa.column("source", sa.String),
            sa.column("quality_status", sa.String),
            sa.column("content", sa.JSON),
            sa.column("generation_metadata", sa.JSON),
            sa.column("task_id", sa.String),
            sa.column("error_code", sa.String),
            sa.column("error_message", sa.Text),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("completed_at", sa.DateTime(timezone=True)),
            sa.column("activated_at", sa.DateTime(timezone=True)),
        )
    )
    connection.execute(stmt, version_rows)

    # Update active_version_id
    for version_id, content_id in update_pairs:
        connection.execute(
            sa.text("UPDATE learning_unit_contents SET active_version_id = :vid, status = 'ready' WHERE id = :cid"),
            {"vid": version_id, "cid": content_id},
        )
