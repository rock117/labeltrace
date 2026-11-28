"""已有未分配成员回填为项目 owner。

Revision ID: 20261128_0019
Revises: 20261128_0018
Create Date: 2026-11-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261128_0019"
down_revision: Union[str, None] = "20261128_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE dataset_assets AS da
        SET assignee_user_id = sub.user_id
        FROM (
            SELECT DISTINCT ON (d.id)
                   d.id AS dataset_id,
                   m.user_id
            FROM datasets d
            JOIN memberships m ON m.project_id = d.project_id
            WHERE m.roles @> '["owner"]'::jsonb
            ORDER BY d.id, m.created_at ASC
        ) AS sub
        WHERE da.dataset_id = sub.dataset_id
          AND da.assignee_user_id IS NULL
        """
    )


def downgrade() -> None:
    # 无法区分回填与用户主动分配，不做回滚清空
    pass
