"""dataset_imports table for YOLO zip import

Revision ID: 20261127_0014
Revises: 20261127_0013
Create Date: 2026-11-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261127_0014"
down_revision: Union[str, None] = "20261127_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("package_name", sa.String(512), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=True),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.String(2048), nullable=True),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["datasets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_dataset_imports_project_id", "dataset_imports", ["project_id"])
    op.create_index("ix_dataset_imports_dataset_id", "dataset_imports", ["dataset_id"])
    op.create_index("ix_dataset_imports_job_id", "dataset_imports", ["job_id"])
    op.create_index("ix_dataset_imports_status", "dataset_imports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_dataset_imports_status", table_name="dataset_imports")
    op.drop_index("ix_dataset_imports_job_id", table_name="dataset_imports")
    op.drop_index("ix_dataset_imports_dataset_id", table_name="dataset_imports")
    op.drop_index("ix_dataset_imports_project_id", table_name="dataset_imports")
    op.drop_table("dataset_imports")
