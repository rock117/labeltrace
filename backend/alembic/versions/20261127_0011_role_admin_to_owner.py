"""rename membership role admin -> owner

Revision ID: 20261127_0011
Revises: 20261126_0010
Create Date: 2026-11-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261127_0011"
down_revision: Union[str, None] = "20261126_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE memberships SET role = 'owner' WHERE role = 'admin'")


def downgrade() -> None:
    op.execute("UPDATE memberships SET role = 'admin' WHERE role = 'owner'")
