"""job lease columns for pg queue

Revision ID: 20261126_0004
Revises: 20261126_0003
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261126_0004"
down_revision: Union[str, None] = "20261126_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("jobs", sa.Column("locked_by", sa.String(128), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_lease_until", "jobs", ["lease_until"])


def downgrade() -> None:
    op.drop_index("ix_jobs_lease_until", table_name="jobs")
    op.drop_column("jobs", "lease_until")
    op.drop_column("jobs", "locked_by")
    op.drop_column("jobs", "attempt")
