"""016 add independent lecture table

Creates the learning_lectures table so lecture content is stored
independently from unit content JSON.

Revision ID: 356527c10db9
Revises: 53b32f4b4afb
Create Date: 2026-06-30 23:15:27.248368
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "356527c10db9"
down_revision: str | None = "53b32f4b4afb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learning_lectures",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("path_id", sa.String(36), nullable=False),
        sa.Column("node_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_generated"),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("active_task_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["path_id"], ["learning_paths.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_learning_lectures_node_id"), "learning_lectures", ["node_id"], unique=True)
    op.create_index(op.f("ix_learning_lectures_path_id"), "learning_lectures", ["path_id"], unique=False)
    op.create_index(op.f("ix_learning_lectures_user_id"), "learning_lectures", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_learning_lectures_user_id"), table_name="learning_lectures")
    op.drop_index(op.f("ix_learning_lectures_path_id"), table_name="learning_lectures")
    op.drop_index(op.f("ix_learning_lectures_node_id"), table_name="learning_lectures")
    op.drop_table("learning_lectures")
