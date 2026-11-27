"""抽帧任务与候选帧审查 API。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import (
    WRITE_ROLES,
    CurrentUser,
    get_current_user,
    get_membership,
    has_any_role,
)
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.jobs.service import JobService, get_job_service
from app.models.asset import Asset
from app.models.dataset import DatasetAsset
from app.models.frame_extract_job import FrameExtractJob
from app.models.project import Project
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


class ProjectExtractJobOut(BaseModel):
    """项目级抽帧任务列表项：供数据集页多选入集。"""

    id: UUID
    project_id: UUID
    video_asset_id: UUID
    video_filename: str | None
    mode: str
    stride: int | None
    interval_ms: int | None
    status: str
    stats: dict
    remaining_frame_count: int
    in_dataset_count: int | None = None
    created_by: str
    created_at: datetime | None = None


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
    if m is None or not has_any_role(m, WRITE_ROLES):
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


@router.get(
    "/assets/{video_asset_id}/extract-jobs",
    response_model=list[ExtractJobOut],
)
def list_video_extract_jobs(
    video_asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[FrameExtractJob]:
    """某视频下的抽帧任务（新→旧）；候选帧只通过任务访问，不进目录主列表。"""
    video = db.get(Asset, video_asset_id)
    if video is None:
        raise NotFoundError("视频不存在")
    m = get_membership(db, video.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return list(
        db.scalars(
            select(FrameExtractJob)
            .where(FrameExtractJob.video_asset_id == video_asset_id)
            .order_by(FrameExtractJob.created_at.desc())
        ).all()
    )


@router.get(
    "/projects/{project_id}/extract-jobs",
    response_model=list[ProjectExtractJobOut],
)
def list_project_extract_jobs(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    status: Annotated[
        Literal["succeeded", "failed", "pending", "running"] | None,
        Query(description="按状态筛选；默认仅 succeeded"),
    ] = "succeeded",
    dataset_id: Annotated[
        UUID | None,
        Query(description="若提供，附带该数据集中已引用的帧数"),
    ] = None,
) -> list[ProjectExtractJobOut]:
    """项目内抽帧任务（新→旧），供数据集页按任务多选入集。"""
    if db.get(Project, project_id) is None:
        raise NotFoundError("项目不存在")
    m = get_membership(db, project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")

    stmt = select(FrameExtractJob).where(FrameExtractJob.project_id == project_id)
    if status is not None:
        stmt = stmt.where(FrameExtractJob.status == status)
    jobs = list(db.scalars(stmt.order_by(FrameExtractJob.created_at.desc())).all())
    if not jobs:
        return []

    video_ids = {j.video_asset_id for j in jobs}
    videos = {
        a.id: a
        for a in db.scalars(select(Asset).where(Asset.id.in_(video_ids))).all()
    }
    job_ids = [j.id for j in jobs]
    remaining_rows = db.execute(
        select(Asset.extract_job_id, func.count())
        .where(
            Asset.extract_job_id.in_(job_ids),
            Asset.media_kind == "frame",
        )
        .group_by(Asset.extract_job_id)
    ).all()
    remaining_map = {row[0]: int(row[1]) for row in remaining_rows}

    in_dataset_map: dict[UUID, int] = {}
    if dataset_id is not None:
        in_rows = db.execute(
            select(Asset.extract_job_id, func.count())
            .join(
                DatasetAsset,
                DatasetAsset.asset_id == Asset.id,
            )
            .where(
                DatasetAsset.dataset_id == dataset_id,
                Asset.extract_job_id.in_(job_ids),
                Asset.media_kind == "frame",
            )
            .group_by(Asset.extract_job_id)
        ).all()
        in_dataset_map = {row[0]: int(row[1]) for row in in_rows}

    out: list[ProjectExtractJobOut] = []
    for j in jobs:
        video = videos.get(j.video_asset_id)
        out.append(
            ProjectExtractJobOut(
                id=j.id,
                project_id=j.project_id,
                video_asset_id=j.video_asset_id,
                video_filename=video.filename if video else None,
                mode=j.mode,
                stride=j.stride,
                interval_ms=j.interval_ms,
                status=j.status,
                stats=j.stats or {},
                remaining_frame_count=remaining_map.get(j.id, 0),
                in_dataset_count=(
                    in_dataset_map.get(j.id, 0) if dataset_id is not None else None
                ),
                created_by=j.created_by,
                created_at=j.created_at,
            )
        )
    return out


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
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    return batch_delete_frames(
        db,
        extract_job_id=extract_job_id,
        asset_ids=body.asset_ids,
        user_id=user.id,
    )
