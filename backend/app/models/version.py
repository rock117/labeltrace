"""不可变数据集版本。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    classes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    enabled_annotation_types: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    member_sources: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    change_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
