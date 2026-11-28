"""项目类别词表 + 数据集有序引用。不迁移旧 dataset_classes。

Revision ID: 20261128_0016
Revises: 20261128_0015
Create Date: 2026-11-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261128_0016"
down_revision: Union[str, None] = "20261128_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("color", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_project_class_name"),
    )
    op.create_index(
        "ix_project_classes_project_id", "project_classes", ["project_id"]
    )
    op.create_table(
        "dataset_class_refs",
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "class_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("project_classes.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "dataset_id", "idx", name="uq_dataset_class_ref_idx"
        ),
    )
    op.drop_index("ix_dataset_classes_dataset_id", table_name="dataset_classes")
    op.drop_table("dataset_classes")


def downgrade() -> None:
    op.create_table(
        "dataset_classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("color", sa.String(32), nullable=True),
        sa.UniqueConstraint("dataset_id", "idx", name="uq_dataset_class_idx"),
        sa.UniqueConstraint("dataset_id", "name", name="uq_dataset_class_name"),
    )
    op.create_index(
        "ix_dataset_classes_dataset_id", "dataset_classes", ["dataset_id"]
    )
    op.drop_table("dataset_class_refs")
    op.drop_index("ix_project_classes_project_id", table_name="project_classes")
    op.drop_table("project_classes")
