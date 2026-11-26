"""initial empty schema

Revision ID: 20261126_0001
Revises:
Create Date: 2026-11-26

空库基线迁移；领域表在后续任务中 autogenerate / 手写追加。
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261126_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 基线：仅建立 alembic_version；业务表随任务 2.x+ 追加
    op.execute("SELECT 1")


def downgrade() -> None:
    pass
