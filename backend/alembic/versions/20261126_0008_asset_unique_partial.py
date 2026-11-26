"""partial unique: hash for image/video; frame by extract job + index

Revision ID: 20261126_0008
Revises: 20261126_0007
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261126_0008"
down_revision: Union[str, None] = "20261126_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_asset_project_content_hash", "assets", type_="unique")
    op.create_index(
        "uq_asset_project_hash_media",
        "assets",
        ["project_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("media_kind IN ('image', 'video')"),
    )
    op.create_index(
        "uq_frame_extract_frame_index",
        "assets",
        ["extract_job_id", "frame_index"],
        unique=True,
        postgresql_where=sa.text(
            "media_kind = 'frame' AND extract_job_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_frame_extract_frame_index", table_name="assets")
    op.drop_index("uq_asset_project_hash_media", table_name="assets")
    op.create_unique_constraint(
        "uq_asset_project_content_hash",
        "assets",
        ["project_id", "content_hash"],
    )
