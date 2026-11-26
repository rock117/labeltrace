"""抽帧任务：创建、执行、审查列表与批量删除。"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.logging import bind_context, get_logger, reset_context
from app.db.session import SessionLocal
from app.media.ffmpeg import (
    extract_frames_interval_ms,
    extract_frames_stride,
    write_bytes_to_temp,
)
from app.models.asset import Asset
from app.models.frame_extract_job import FrameExtractJob
from app.services.asset_refs import asset_has_references
from app.services.assets import _sha256, _storage_key, read_asset_bytes
from app.storage.factory import get_blob_store, get_default_write_backend

logger = get_logger("labeltrace.extract")


def create_extract_job(
    db: Session,
    *,
    video_asset_id: UUID,
    mode: str,
    stride: int | None,
    interval_ms: int | None,
    options: dict[str, Any] | None,
    user_id: str,
    enqueue_job,
) -> FrameExtractJob:
    video = db.get(Asset, video_asset_id)
    if video is None or video.media_kind != "video":
        raise NotFoundError("视频素材不存在")
    if mode == "stride_frames":
        if stride is None or stride < 1:
            raise ValidationAppError("stride_frames 模式需要 stride >= 1")
    elif mode == "interval_ms":
        if interval_ms is None or interval_ms < 1:
            raise ValidationAppError("interval_ms 模式需要 interval_ms >= 1")
    else:
        raise ValidationAppError("mode 须为 stride_frames 或 interval_ms")

    extract = FrameExtractJob(
        project_id=video.project_id,
        video_asset_id=video.id,
        mode=mode,
        stride=stride,
        interval_ms=interval_ms,
        options=options or {},
        status="pending",
        stats={},
        created_by=user_id,
    )
    db.add(extract)
    db.flush()

    job = enqueue_job(
        db,
        "frame_extract",
        {"extract_job_id": str(extract.id)},
    )
    extract.job_id = job.id
    db.commit()
    db.refresh(extract)
    logger.info(
        "extract_job_created extract_job_id=%s video_id=%s mode=%s",
        extract.id,
        video.id,
        mode,
    )
    return extract


def run_frame_extract(extract_job_id: UUID) -> dict[str, Any]:
    """Job handler：物化帧并写入 Asset(frame)。"""
    tokens = bind_context(job_id=str(extract_job_id))
    db = SessionLocal()
    tmp_video: Path | None = None
    work_dir: Path | None = None
    try:
        extract = db.get(FrameExtractJob, extract_job_id)
        if extract is None:
            raise RuntimeError(f"抽帧任务不存在: {extract_job_id}")
        extract.status = "running"
        db.commit()

        video = db.get(Asset, extract.video_asset_id)
        if video is None:
            raise RuntimeError("源视频已删除")

        data = read_asset_bytes(video)
        ext = Path(video.filename).suffix or ".mp4"
        tmp_video = write_bytes_to_temp(data, ext)
        work_dir = Path(tempfile.mkdtemp(prefix="lt-frames-"))

        max_frames = (extract.options or {}).get("max_frames")
        if extract.mode == "stride_frames":
            frames = extract_frames_stride(
                tmp_video,
                stride=int(extract.stride or 1),
                out_dir=work_dir,
                max_frames=max_frames,
            )
        else:
            frames = extract_frames_interval_ms(
                tmp_video,
                interval_ms=int(extract.interval_ms or 1000),
                out_dir=work_dir,
                max_frames=max_frames,
            )

        backend = get_default_write_backend()
        store = get_blob_store(backend)
        created = 0
        for fr in frames:
            jpg = fr.path.read_bytes()
            digest = _sha256(jpg)
            key = _storage_key(extract.project_id, digest, ".jpg")
            if not store.exists(key):
                store.put(key, jpg, content_type="image/jpeg")
            asset = Asset(
                project_id=extract.project_id,
                media_kind="frame",
                parent_video_id=video.id,
                frame_index=fr.frame_index,
                extract_job_id=extract.id,
                folder_id=None,
                library_visible=False,
                origin="extract",
                content_hash=digest,
                storage_backend=backend,
                storage_key=key,
                filename=f"frame_{fr.frame_index:06d}.jpg",
                mime="image/jpeg",
                width=video.width,
                height=video.height,
            )
            db.add(asset)
            created += 1
            db.flush()  # 尽早暴露唯一约束冲突

        extract.status = "succeeded"
        extract.stats = {
            "extracted_count": len(frames),
            "created_count": created,
            "kept_count": len(frames),
            "discarded_count": 0,
        }
        extract.error_message = None
        db.commit()
        logger.info(
            "extract_done extract_job_id=%s extracted=%s created=%s",
            extract.id,
            len(frames),
            created,
        )
        return {"extract_job_id": str(extract.id), "stats": extract.stats}
    except Exception as exc:
        logger.exception("extract_failed extract_job_id=%s", extract_job_id)
        db.rollback()
        extract = db.get(FrameExtractJob, extract_job_id)
        if extract is not None:
            extract.status = "failed"
            extract.error_message = str(exc)[:2000]
            db.commit()
        raise
    finally:
        reset_context(tokens)
        if tmp_video is not None:
            try:
                tmp_video.unlink(missing_ok=True)
            except OSError:
                logger.warning("temp_cleanup_failed path=%s", tmp_video)
        if work_dir is not None and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)
        db.close()


def list_extract_frames(db: Session, extract_job_id: UUID) -> list[Asset]:
    """候选帧：按 frame_index 升序。"""
    stmt = (
        select(Asset)
        .where(
            Asset.extract_job_id == extract_job_id,
            Asset.media_kind == "frame",
        )
        .order_by(Asset.frame_index.asc())
    )
    return list(db.scalars(stmt).all())


def batch_delete_frames(
    db: Session,
    *,
    extract_job_id: UUID,
    asset_ids: list[UUID],
    user_id: str,
) -> dict[str, int]:
    extract = db.get(FrameExtractJob, extract_job_id)
    if extract is None:
        raise NotFoundError("抽帧任务不存在")

    deleted = 0
    for aid in asset_ids:
        asset = db.get(Asset, aid)
        if asset is None:
            continue
        if asset.extract_job_id != extract_job_id or asset.media_kind != "frame":
            raise ValidationAppError(f"素材不属于该抽帧任务: {aid}")
        if asset_has_references(db, asset.id):
            raise ConflictError(f"帧仍被引用，禁止删除: {aid}")
        store = get_blob_store(asset.storage_backend)
        key = asset.storage_key
        db.delete(asset)
        db.flush()
        try:
            store.delete(key)
        except Exception:
            logger.exception("frame_blob_delete_failed asset_id=%s", aid)
            raise
        deleted += 1

    remaining = db.scalar(
        select(func.count())
        .select_from(Asset)
        .where(
            Asset.extract_job_id == extract_job_id,
            Asset.media_kind == "frame",
        )
    ) or 0
    stats = dict(extract.stats or {})
    extracted = int(stats.get("extracted_count") or (remaining + deleted))
    discarded = int(stats.get("discarded_count") or 0) + deleted
    stats.update(
        {
            "extracted_count": extracted,
            "kept_count": remaining,
            "discarded_count": discarded,
        }
    )
    extract.stats = stats
    db.commit()
    logger.info(
        "frames_batch_deleted extract_job_id=%s deleted=%s kept=%s user_id=%s",
        extract_job_id,
        deleted,
        remaining,
        user_id,
    )
    return {"deleted": deleted, "kept_count": remaining, "discarded_count": discarded}


def frame_time_ms(asset: Asset, video: Asset | None) -> int:
    if asset.frame_index is None:
        return 0
    fps = (video.fps if video else None) or 0.0
    if fps <= 0:
        return 0
    return int(asset.frame_index / fps * 1000)
