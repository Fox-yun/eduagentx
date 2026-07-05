"""Add learning_resources table for multimodal artifacts.

Phase 3.9: Multimodal Resource Expansion
- PPTX presentations
- Code ZIP archives
- Interactive learning resources
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import String, Text, Boolean, DateTime, JSON
from sqlalchemy.sql import func, text

# revision identifiers
revision = "010203040506"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create learning_resources table
    op.create_table(
        "learning_resources",
        op.Column("id", String(36), primary_key=True),
        op.Column("user_id", String(36), nullable=False, index=True),
        op.Column("path_id", String(36), nullable=False, index=True),
        op.Column("node_id", String(36), nullable=False, index=True),
        op.Column(
            "resource_type",
            String(30),
            nullable=False,
            index=True,
            comment="pptx, code_zip, interactive_cards, walkthrough, simulation",
        ),
        op.Column(
            "status",
            String(20),
            nullable=False,
            default="not_generated",
            comment="not_generated, generating, ready, failed",
        ),
        op.Column("active_task_id", String(36), nullable=True),
        op.Column("content", JSON, nullable=True, comment="Resource-specific data (e.g., slide count)"),
        op.Column("error_code", String(50), nullable=True),
        op.Column("error_message", Text, nullable=True),
        op.Column("storage_key", String(500), nullable=True, comment="MinIO storage key for binary files"),
        op.Column(
            "storage_provider",
            String(20),
            nullable=True,
            comment="minio, local",
        ),
        op.Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
        op.Column(
            "updated_at",
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        ),
    )

    # Add foreign key constraints
    op.create_foreign_key(
        "fk_resource_user",
        "learning_resources",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_resource_path",
        "learning_resources",
        "learning_paths",
        ["path_id"],
        ["id"],
    )

    # Add unique constraint: one resource of each type per node
    op.create_unique_constraint(
        "uq_resource_per_node_type",
        "learning_resources",
        ["node_id", "resource_type"],
    )

    # Add indexes
    op.create_index("idx_resources_user_type", "learning_resources", ["user_id", "resource_type"])
    op.create_index("idx_resources_node_type", "learning_resources", ["node_id", "resource_type"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_resources_node_type", table_name="learning_resources")
    op.drop_index("idx_resources_user_type", table_name="learning_resources")

    # Drop unique constraint
    op.drop_constraint("uq_resource_per_node_type", "learning_resources", type_="unique")

    # Drop foreign keys
    op.drop_constraint("fk_resource_path", "learning_resources", type_="foreignkey")
    op.drop_constraint("fk_resource_user", "learning_resources", type_="foreignkey")

    # Drop table
    op.drop_table("learning_resources")