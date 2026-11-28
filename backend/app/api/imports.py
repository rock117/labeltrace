"""YOLO 数据集导入 API。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user, get_membership
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import get_db
from app.jobs.service import JobService, get_job_service
from app.models.dataset import Dataset
from app.models.dataset_import import DatasetImport
from app.services.import_yolo import create_dataset_import

router = APIRouter(tags=["imports"])
logger = get_logger("labeltrace.api.imports")


class ImportOut(BaseModel):
    id: UUID
    project_id: UUID
    dataset_id: UUID | None
    job_id: UUID | None
    package_name: str
    status: str
    stats: dict[str, Any]
    error_message: str | None
    created_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


def _out(row: DatasetImport) -> ImportOut:
    return ImportOut(
        id=row.id,
        project_id=row.project_id,
        dataset_id=row.dataset_id,
        job_id=row.job_id,
        package_name=row.package_name,
        status=row.status,
        stats=dict(row.stats or {}),
        error_message=row.error_message,
        created_by=row.created_by,
        created_at=row.created_at,
    )


@router.post(
    "/projects/{project_id}/dataset-imports",
    response_model=ImportOut,
    status_code=202,
)
async def start_dataset_import(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    jobs: Annotated[JobService, Depends(get_job_service)],
    file: UploadFile = File(...),
    datasetName: str | None = Form(None),
    datasetId: UUID | None = Form(None),
    profile: str | None = Form(None),
) -> ImportOut:
    """multipart：YOLO zip + datasetName（新建）或 datasetId（空集）+ 可选 profile。仅 owner。"""
    raw = await file.read()
    name = file.filename or "package.zip"
    if not name.lower().endswith(".zip"):
        raise ValidationAppError("请上传 .zip 格式的 YOLO 数据包")

    def enqueue(session: Session, job_type: str, payload: dict) -> Any:
        return jobs.enqueue(session, job_type, payload)

    imp = create_dataset_import(
        db,
        project_id=project_id,
        package_name=name,
        zip_bytes=raw,
        user_id=user.id,
        dataset_name=datasetName,
        dataset_id=datasetId,
        enqueue_job=enqueue,
        profile=profile,
    )
    return _out(imp)


@router.get("/dataset-imports/{import_id}", response_model=ImportOut)
def get_dataset_import(
    import_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ImportOut:
    imp = db.get(DatasetImport, import_id)
    if imp is None:
        raise NotFoundError("导入记录不存在")
    m = get_membership(db, imp.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return _out(imp)


@router.get(
    "/datasets/{dataset_id}/imports",
    response_model=list[ImportOut],
)
def list_dataset_imports(
    dataset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ImportOut]:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    rows = db.scalars(
        select(DatasetImport)
        .where(DatasetImport.dataset_id == dataset_id)
        .order_by(DatasetImport.created_at.desc())
    ).all()
    return [_out(r) for r in rows]
