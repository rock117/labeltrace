"""发版与版本查询；memberSources 工作区摘要；YOLO 导出。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user, get_membership
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.jobs.service import JobService, get_job_service
from app.models.dataset import Dataset
from app.models.job import Job
from app.models.version import DatasetVersion
from app.services.assets import content_disposition_attachment
from app.services.export_yolo import export_storage_key
from app.services.member_sources import build_member_sources
from app.services.versions import apply_version_to_workspace, publish_version
from app.storage.factory import get_blob_store, get_default_write_backend

router = APIRouter(tags=["versions"])
logger = get_logger("labeltrace.api.versions")


class PublishIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    note: str | None = None
    parent_id: UUID | None = None
    split_train: float = Field(0.7, ge=0, le=1, alias="splitTrain")
    split_val: float = Field(0.2, ge=0, le=1, alias="splitVal")
    split_test: float = Field(0.1, ge=0, le=1, alias="splitTest")
    split_seed: int | None = Field(None, alias="splitSeed")

    model_config = {"populate_by_name": True}


class VersionClassOut(BaseModel):
    id: str
    name: str


class VersionOut(BaseModel):
    id: UUID
    dataset_id: UUID
    name: str
    parent_id: UUID | None
    classes: list[VersionClassOut]
    enabled_annotation_types: list[Any]
    member_sources: list[Any]
    change_summary: dict[str, Any] | None
    created_by: str
    note: str | None
    created_at: datetime
    entry_count: int = 0

    model_config = {"from_attributes": True}


def _normalize_version_classes(raw: Any) -> list[VersionClassOut]:
    """发版快照 [{id, name}]。"""
    out: list[VersionClassOut] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, dict) and item.get("id") and item.get("name") is not None:
            out.append(
                VersionClassOut(id=str(item["id"]), name=str(item["name"]))
            )
    return out


def _out(v: DatasetVersion) -> VersionOut:
    entries = (v.manifest or {}).get("entries") or []
    return VersionOut(
        id=v.id,
        dataset_id=v.dataset_id,
        name=v.name,
        parent_id=v.parent_id,
        classes=_normalize_version_classes(v.classes),
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
        split_train=body.split_train,
        split_val=body.split_val,
        split_test=body.split_test,
        split_seed=body.split_seed,
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


class ExportJobOut(BaseModel):
    job_id: UUID
    version_id: UUID
    status: str


def _version_for_member(
    db: Session, version_id: UUID, user_id: str
) -> tuple[DatasetVersion, Dataset]:
    v = db.get(DatasetVersion, version_id)
    if v is None:
        raise NotFoundError("版本不存在")
    ds = db.get(Dataset, v.dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user_id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return v, ds


@router.post(
    "/versions/{version_id}/export",
    response_model=ExportJobOut,
    status_code=202,
)
def start_yolo_export(
    version_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    jobs: Annotated[JobService, Depends(get_job_service)],
) -> ExportJobOut:
    """入队 YOLO zip 导出；立即返回 job_id，完成后 GET .../export/download。"""
    v, _ds = _version_for_member(db, version_id, user.id)
    job = jobs.enqueue(
        db,
        "yolo_export",
        {"version_id": str(v.id), "requested_by": user.id},
    )
    logger.info(
        "yolo_export_enqueued version_id=%s job_id=%s user_id=%s",
        v.id,
        job.id,
        user.id,
    )
    return ExportJobOut(job_id=job.id, version_id=v.id, status=job.status)


@router.get("/versions/{version_id}/export/download")
def download_yolo_export(
    version_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """下载已生成的 YOLO zip；尚未导出或产物缺失时 404。"""
    v, ds = _version_for_member(db, version_id, user.id)
    key = export_storage_key(ds.project_id, v.id)
    backend = get_default_write_backend()
    download_name = f"{ds.name}_{v.name}.zip"

    # 优先用本版本最近一次成功导出的 backend/key/文件名
    for j in db.scalars(
        select(Job)
        .where(Job.job_type == "yolo_export", Job.status == "succeeded")
        .order_by(Job.finished_at.desc().nullslast(), Job.created_at.desc())
        .limit(100)
    ).all():
        payload = j.payload or {}
        result = j.result if isinstance(j.result, dict) else {}
        if str(payload.get("version_id")) != str(v.id) and str(
            result.get("versionId")
        ) != str(v.id):
            continue
        backend = str(result.get("storageBackend") or backend)
        key = str(result.get("storageKey") or key)
        if result.get("downloadName"):
            download_name = str(result["downloadName"])
        break

    store = get_blob_store(backend)
    if not store.exists(key):
        raise NotFoundError("尚未导出或导出文件不存在，请先触发导出")

    body = b"".join(store.get(key))
    logger.info(
        "yolo_export_download version_id=%s bytes=%s key=%s",
        version_id,
        len(body),
        key,
    )
    return Response(
        content=body,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition_attachment(download_name),
        },
    )
