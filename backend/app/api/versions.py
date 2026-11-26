"""发版与版本查询；memberSources 工作区摘要。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user, get_membership
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.version import DatasetVersion
from app.services.member_sources import build_member_sources
from app.services.versions import apply_version_to_workspace, publish_version

router = APIRouter(tags=["versions"])
logger = get_logger("labeltrace.api.versions")


class PublishIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    note: str | None = None
    parent_id: UUID | None = None


class VersionOut(BaseModel):
    id: UUID
    dataset_id: UUID
    name: str
    parent_id: UUID | None
    classes: list[str]
    enabled_annotation_types: list[Any]
    member_sources: list[Any]
    change_summary: dict[str, Any] | None
    created_by: str
    note: str | None
    created_at: datetime
    entry_count: int = 0

    model_config = {"from_attributes": True}


def _out(v: DatasetVersion) -> VersionOut:
    entries = (v.manifest or {}).get("entries") or []
    return VersionOut(
        id=v.id,
        dataset_id=v.dataset_id,
        name=v.name,
        parent_id=v.parent_id,
        classes=list(v.classes or []),
        enabled_annotation_types=list(v.enabled_annotation_types or []),
        member_sources=list(v.member_sources or []),
        change_summary=v.change_summary,
        created_by=v.created_by,
        note=v.note,
        created_at=v.created_at,
        entry_count=len(entries),
    )


@router.get("/datasets/{dataset_id}/member-sources")
def workspace_member_sources(
    dataset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return build_member_sources(db, dataset_id)


@router.post(
    "/datasets/{dataset_id}/versions",
    response_model=VersionOut,
    status_code=201,
)
def create_version(
    dataset_id: UUID,
    body: PublishIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> VersionOut:
    ver = publish_version(
        db,
        dataset_id=dataset_id,
        name=body.name,
        user_id=user.id,
        note=body.note,
        parent_id=body.parent_id,
    )
    return _out(ver)


@router.get("/datasets/{dataset_id}/versions", response_model=list[VersionOut])
def list_versions(
    dataset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[VersionOut]:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    rows = db.scalars(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.created_at.desc())
    ).all()
    return [_out(v) for v in rows]


@router.get("/versions/{version_id}", response_model=VersionOut)
def get_version(
    version_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> VersionOut:
    v = db.get(DatasetVersion, version_id)
    if v is None:
        raise NotFoundError("版本不存在")
    ds = db.get(Dataset, v.dataset_id)
    assert ds is not None
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return _out(v)


@router.get("/versions/{version_id}/manifest")
def get_manifest(
    version_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    v = db.get(DatasetVersion, version_id)
    if v is None:
        raise NotFoundError("版本不存在")
    ds = db.get(Dataset, v.dataset_id)
    assert ds is not None
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return v.manifest or {"entries": []}


class ApplyToWorkspaceOut(BaseModel):
    added: int
    overwritten: int
    skipped: int
    entryCount: int
    dataset_id: UUID


@router.post(
    "/versions/{version_id}/apply-to-workspace",
    response_model=ApplyToWorkspaceOut,
)
def apply_to_workspace(
    version_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApplyToWorkspaceOut:
    v = db.get(DatasetVersion, version_id)
    if v is None:
        raise NotFoundError("版本不存在")
    stats = apply_version_to_workspace(
        db, version_id=version_id, user_id=user.id
    )
    return ApplyToWorkspaceOut(
        added=stats["added"],
        overwritten=stats["overwritten"],
        skipped=stats["skipped"],
        entryCount=stats["entryCount"],
        dataset_id=v.dataset_id,
    )
