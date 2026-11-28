"""dataset_classes.color + no data migration (breaking shapes classId)

Revision ID: 20261128_0015
Revises: 20261127_0014
Create Date: 2026-11-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261128_0015"
down_revision: Union[str, None] = "20261127_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset_classes",
        sa.Column("color", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_classes", "color")
