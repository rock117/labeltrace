"""membership role -> roles jsonb (multi-role per project)

Revision ID: 20261127_0012
Revises: 20261127_0011
Create Date: 2026-11-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261127_0012"
down_revision: Union[str, None] = "20261127_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column(
            "roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE memberships
        SET roles = jsonb_build_array(role)
        WHERE role IS NOT NULL AND role <> ''
        """
    )
    op.drop_column("memberships", "role")
    op.alter_column("memberships", "roles", server_default=None)


def downgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column("role", sa.String(length=32), nullable=True),
    )
    op.execute(
        """
        UPDATE memberships
        SET role = COALESCE(roles->>0, 'viewer')
        """
    )
    op.alter_column("memberships", "role", nullable=False)
    op.drop_column("memberships", "roles")
