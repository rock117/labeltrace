"""frame_extract_jobs

Revision ID: 20261126_0007
Revises: 20261126_0006
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261126_0007"
down_revision: Union[str, None] = "20261126_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "frame_extract_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "video_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("stride", sa.Integer(), nullable=True),
        sa.Column("interval_ms", sa.Integer(), nullable=True),
        sa.Column(
            "options",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="pending"
        ),
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
    )
    op.create_index(
        "ix_frame_extract_jobs_project_id", "frame_extract_jobs", ["project_id"]
    )
    op.create_index(
        "ix_frame_extract_jobs_video_asset_id",
        "frame_extract_jobs",
        ["video_asset_id"],
    )
    op.create_index(
        "ix_frame_extract_jobs_job_id", "frame_extract_jobs", ["job_id"]
    )
    op.create_index(
        "ix_frame_extract_jobs_status", "frame_extract_jobs", ["status"]
    )


def downgrade() -> None:
    op.drop_index("ix_frame_extract_jobs_status", table_name="frame_extract_jobs")
    op.drop_index("ix_frame_extract_jobs_job_id", table_name="frame_extract_jobs")
    op.drop_index(
        "ix_frame_extract_jobs_video_asset_id", table_name="frame_extract_jobs"
    )
    op.drop_index(
        "ix_frame_extract_jobs_project_id", table_name="frame_extract_jobs"
    )
    op.drop_table("frame_extract_jobs")
