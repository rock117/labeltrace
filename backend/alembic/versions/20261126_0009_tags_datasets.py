"""tags and datasets

Revision ID: 20261126_0009
Revises: 20261126_0008
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261126_0009"
down_revision: Union[str, None] = "20261126_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "name", name="uq_tag_project_name"),
    )
    op.create_index("ix_tags_project_id", "tags", ["project_id"])

    op.create_table(
        "asset_tags",
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.UniqueConstraint("asset_id", "tag_id", name="uq_asset_tag"),
    )
    op.create_index("ix_asset_tags_tag_id", "asset_tags", ["tag_id"])

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column(
            "enabled_annotation_types",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[\"rect\"]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_datasets_project_id", "datasets", ["project_id"])

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
        sa.UniqueConstraint("dataset_id", "idx", name="uq_dataset_class_idx"),
        sa.UniqueConstraint("dataset_id", "name", name="uq_dataset_class_name"),
    )
    op.create_index(
        "ix_dataset_classes_dataset_id", "dataset_classes", ["dataset_id"]
    )

    op.create_table(
        "dataset_assets",
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("datasets.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "split", sa.String(32), nullable=False, server_default="unassigned"
        ),
        sa.UniqueConstraint("dataset_id", "asset_id", name="uq_dataset_asset"),
    )
    op.create_index(
        "ix_dataset_assets_asset_id", "dataset_assets", ["asset_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_assets_asset_id", table_name="dataset_assets")
    op.drop_table("dataset_assets")
    op.drop_index("ix_dataset_classes_dataset_id", table_name="dataset_classes")
    op.drop_table("dataset_classes")
    op.drop_index("ix_datasets_project_id", table_name="datasets")
    op.drop_table("datasets")
    op.drop_index("ix_asset_tags_tag_id", table_name="asset_tags")
    op.drop_table("asset_tags")
    op.drop_index("ix_tags_project_id", table_name="tags")
    op.drop_table("tags")
