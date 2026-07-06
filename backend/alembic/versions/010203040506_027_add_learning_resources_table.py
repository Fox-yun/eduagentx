"""Add learning_resources table for multimodal artifacts.

Phase 3.9: Multimodal Resource Expansion
- PPTX presentations
- Code ZIP archives
- Interactive learning resources
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "010203040506"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_resources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("path_id", sa.String(36), sa.ForeignKey("learning_paths.id"), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="not_generated",
        ),
        sa.Column("active_task_id", sa.String(36), nullable=True),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=True),
        sa.Column("storage_provider", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "path_id",
            "node_id",
            "resource_type",
            name="uq_resource_user_path_node_type",
        ),
    )

    op.create_index("idx_resources_user_type", "learning_resources", ["user_id", "resource_type"])
    op.create_index("idx_resources_node_type", "learning_resources", ["node_id", "resource_type"])


def downgrade() -> None:
    op.drop_index("idx_resources_node_type", table_name="learning_resources")
    op.drop_index("idx_resources_user_type", table_name="learning_resources")
    op.drop_table("learning_resources")
