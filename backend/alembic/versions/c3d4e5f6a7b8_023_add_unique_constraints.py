"""023 add unique constraints for assessments, learning_progress, mastery_snapshots

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-04 18:00:00.000000
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Assessment: UNIQUE(user_id, path_version_id, node_id, purpose)
    #    Prevents duplicate assessments for the same node+purpose in a version.
    #    First, remove duplicates: keep the latest created_at per group.
    bind.execute(
        sa.text(
            """
        DELETE FROM assessments a
        USING assessments b
        WHERE a.user_id = b.user_id
          AND a.path_version_id = b.path_version_id
          AND a.node_id = b.node_id
          AND a.purpose = b.purpose
          AND a.id < b.id
        """
        )
    )
    op.create_unique_constraint(
        "uq_assessment_user_version_node_purpose",
        "assessments",
        ["user_id", "path_version_id", "node_id", "purpose"],
    )

    # 2. LearningProgress: UNIQUE(user_id, path_id, node_id)
    #    Prevents duplicate progress rows that would crash scalar_one_or_none().
    bind.execute(
        sa.text(
            """
        DELETE FROM learning_progress lp
        USING learning_progress lp2
        WHERE lp.user_id = lp2.user_id
          AND lp.path_id = lp2.path_id
          AND lp.node_id = lp2.node_id
          AND lp.id < lp2.id
        """
        )
    )
    op.create_unique_constraint(
        "uq_learning_progress_user_path_node",
        "learning_progress",
        ["user_id", "path_id", "node_id"],
    )

    # 3. MasterySnapshot: UNIQUE(source_type, source_id)
    #    Prevents duplicate snapshots from the same attempt/diagnostic.
    bind.execute(
        sa.text(
            """
        DELETE FROM mastery_snapshots ms
        USING mastery_snapshots ms2
        WHERE ms.source_type = ms2.source_type
          AND ms.source_id = ms2.source_id
          AND ms.id < ms2.id
        """
        )
    )
    op.create_unique_constraint(
        "uq_mastery_snapshot_source",
        "mastery_snapshots",
        ["source_type", "source_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_mastery_snapshot_source", "mastery_snapshots", type_="unique")
    op.drop_constraint("uq_learning_progress_user_path_node", "learning_progress", type_="unique")
    op.drop_constraint("uq_assessment_user_version_node_purpose", "assessments", type_="unique")
