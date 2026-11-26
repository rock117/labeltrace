"""assets table

Revision ID: 20261126_0006
Revises: 20261126_0005
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261126_0006"
down_revision: Union[str, None] = "20261126_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("media_kind", sa.String(16), nullable=False),
        sa.Column(
            "parent_video_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("frame_index", sa.Integer(), nullable=True),
        sa.Column("extract_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column(
            "folder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "library_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_backend", sa.String(32), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("source_path", sa.String(2048), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("mime", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "project_id", "content_hash", name="uq_asset_project_content_hash"
        ),
    )
    op.create_index("ix_assets_project_id", "assets", ["project_id"])
    op.create_index("ix_assets_media_kind", "assets", ["media_kind"])
    op.create_index("ix_assets_folder_id", "assets", ["folder_id"])
    op.create_index("ix_assets_parent_video_id", "assets", ["parent_video_id"])
    op.create_index("ix_assets_extract_job_id", "assets", ["extract_job_id"])
    op.create_index("ix_assets_import_id", "assets", ["import_id"])


def downgrade() -> None:
    op.drop_index("ix_assets_import_id", table_name="assets")
    op.drop_index("ix_assets_extract_job_id", table_name="assets")
    op.drop_index("ix_assets_parent_video_id", table_name="assets")
    op.drop_index("ix_assets_folder_id", table_name="assets")
    op.drop_index("ix_assets_media_kind", table_name="assets")
    op.drop_index("ix_assets_project_id", table_name="assets")
    op.drop_table("assets")
