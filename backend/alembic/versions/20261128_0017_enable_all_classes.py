"""已有数据集补上尚未启用的项目类别。新建类别之后由服务追加。

Revision ID: 20261128_0017
Revises: 20261128_0016
Create Date: 2026-11-28
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261128_0017"
down_revision: Union[str, None] = "20261128_0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO dataset_class_refs (dataset_id, class_id, idx)
        SELECT d.id,
               pc.id,
               COALESCE(
                   (SELECT MAX(r.idx) FROM dataset_class_refs r WHERE r.dataset_id = d.id),
                   -1
               ) + ROW_NUMBER() OVER (
                   PARTITION BY d.id ORDER BY pc.created_at, pc.name
               )
        FROM datasets d
        JOIN project_classes pc ON pc.project_id = d.project_id
        WHERE NOT EXISTS (
            SELECT 1
            FROM dataset_class_refs r
            WHERE r.dataset_id = d.id AND r.class_id = pc.id
        )
        """
    )


def downgrade() -> None:
    pass
