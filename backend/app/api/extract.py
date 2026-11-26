"""抽帧任务与候选帧审查 API。"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import (
    WRITE_ROLES,
    CurrentUser,
    get_current_user,
    get_membership,
)
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.jobs.service import JobService, get_job_service
from app.models.asset import Asset
from app.models.frame_extract_job import FrameExtractJob
from app.services.extract import (
    batch_delete_frames,
    create_extract_job,
    frame_time_ms,
    list_extract_frames,
)

router = APIRouter(tags=["extract"])
logger = get_logger("labeltrace.api.extract")


class ExtractCreate(BaseModel):
    mode: Literal["stride_frames", "interval_ms"]
    stride: int | None = None
    interval_ms: int | None = None
    max_frames: int | None = Field(default=None, ge=1)


class ExtractJobOut(BaseModel):
    id: UUID
    project_id: UUID
    video_asset_id: UUID
    job_id: UUID | None
    mode: str
    stride: int | None
    interval_ms: int | None
    options: dict
    status: str
    stats: dict
    error_message: str | None
    created_by: str

    model_config = {"from_attributes": True}


class FrameCandidateOut(BaseModel):
    id: UUID
    frame_index: int | None
    time_ms: int
    time_label: str
    filename: str
    extract_job_id: UUID | None
    parent_video_id: UUID | None


class BatchDeleteIn(BaseModel):
    asset_ids: list[UUID] = Field(..., min_length=1)


def _fmt_time(ms: int) -> str:
    total_s = ms / 1000.0
    m = int(total_s // 60)
    s = total_s - m * 60
    return f"{m:02d}:{s:06.3f}"


@router.post(
    "/assets/{video_asset_id}/extract-jobs",
    response_model=ExtractJobOut,
    status_code=201,
)
def start_extract(
    video_asset_id: UUID,
    body: ExtractCreate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    jobs: Annotated[JobService, Depends(get_job_service)],
) -> FrameExtractJob:
    video = db.get(Asset, video_asset_id)
    if video is None:
        raise NotFoundError("视频不存在")
    m = get_membership(db, video.project_id, user.id)
    if m is None or m.role not in WRITE_ROLES:
        raise ForbiddenError("权限不足")

    options = {}
    if body.max_frames is not None:
        options["max_frames"] = body.max_frames

    return create_extract_job(
        db,
        video_asset_id=video_asset_id,
        mode=body.mode,
        stride=body.stride,
        interval_ms=body.interval_ms,
        options=options,
        user_id=user.id,
        enqueue_job=jobs.enqueue,
    )


@router.get("/extract-jobs/{extract_job_id}", response_model=ExtractJobOut)
def get_extract_job(
    extract_job_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FrameExtractJob:
    job = db.get(FrameExtractJob, extract_job_id)
    if job is None:
        raise NotFoundError("抽帧任务不存在")
    m = get_membership(db, job.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return job


@router.get(
    "/extract-jobs/{extract_job_id}/frames",
    response_model=list[FrameCandidateOut],
)
def list_frames(
    extract_job_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[FrameCandidateOut]:
    job = db.get(FrameExtractJob, extract_job_id)
    if job is None:
        raise NotFoundError("抽帧任务不存在")
    m = get_membership(db, job.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    video = db.get(Asset, job.video_asset_id)
    frames = list_extract_frames(db, extract_job_id)
    out: list[FrameCandidateOut] = []
    for f in frames:
        tms = frame_time_ms(f, video)
        out.append(
            FrameCandidateOut(
                id=f.id,
                frame_index=f.frame_index,
                time_ms=tms,
                time_label=_fmt_time(tms),
                filename=f.filename,
                extract_job_id=f.extract_job_id,
                parent_video_id=f.parent_video_id,
            )
        )
    return out


@router.post("/extract-jobs/{extract_job_id}/frames/batch-delete")
def batch_delete(
    extract_job_id: UUID,
    body: BatchDeleteIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    job = db.get(FrameExtractJob, extract_job_id)
    if job is None:
        raise NotFoundError("抽帧任务不存在")
    m = get_membership(db, job.project_id, user.id)
    if m is None or m.role not in WRITE_ROLES:
        raise ForbiddenError("权限不足")
    return batch_delete_frames(
        db,
        extract_job_id=extract_job_id,
        asset_ids=body.asset_ids,
        user_id=user.id,
    )
