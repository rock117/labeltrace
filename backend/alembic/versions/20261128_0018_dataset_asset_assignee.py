"""dataset_assets.assignee_user_id 任务分配。

Revision ID: 20261128_0018
Revises: 20261128_0017
Create Date: 2026-11-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261128_0018"
down_revision: Union[str, None] = "20261128_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_assets",
        sa.Column("assignee_user_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_dataset_assets_assignee_user_id",
        "dataset_assets",
        ["assignee_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_assets_assignee_user_id", table_name="dataset_assets")
    op.drop_column("dataset_assets", "assignee_user_id")
