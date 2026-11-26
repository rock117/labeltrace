"""视频上传与元数据。"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.media.ffmpeg import probe_video, write_bytes_to_temp
from app.models.asset import Asset
from app.models.folder import Folder
from app.services.assets import _ext_from_filename, _sha256, _storage_key
from app.storage.factory import get_blob_store, get_default_write_backend

logger = get_logger("labeltrace.video")

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


def upload_video_to_folder(
    db: Session,
    *,
    folder_id: UUID,
    filename: str,
    data: bytes,
    content_type: str | None,
    user_id: str,
) -> Asset:
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise NotFoundError("目录不存在")

    name = (filename or "video.mp4").strip() or "video.mp4"
    ext = _ext_from_filename(name)
    mime = content_type or mimetypes.guess_type(name)[0] or "video/mp4"
    if ext not in VIDEO_EXTS and not (mime or "").startswith("video/"):
        raise ValidationAppError("仅支持视频上传")

    digest = _sha256(data)
    existing = db.scalar(
        select(Asset).where(
            Asset.project_id == folder.project_id,
            Asset.content_hash == digest,
        )
    )
    if existing is not None:
        logger.info(
            "video_dedup_hit asset_id=%s content_hash=%s",
            existing.id,
            digest,
        )
        return existing

    tmp: Path | None = None
    try:
        tmp = write_bytes_to_temp(data, ext or ".mp4")
        meta = probe_video(tmp)
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                logger.warning("temp_video_cleanup_failed path=%s", tmp)

    backend = get_default_write_backend()
    key = _storage_key(folder.project_id, digest, ext or ".mp4")
    store = get_blob_store(backend)
    store.put(key, data, content_type=mime)

    asset = Asset(
        project_id=folder.project_id,
        media_kind="video",
        folder_id=folder.id,
        library_visible=True,
        origin="upload",
        content_hash=digest,
        storage_backend=backend,
        storage_key=key,
        filename=name,
        mime=mime,
        width=meta.width,
        height=meta.height,
        duration_ms=meta.duration_ms,
        fps=meta.fps,
    )
    db.add(asset)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("video_create_failed content_hash=%s", digest)
        existing = db.scalar(
            select(Asset).where(
                Asset.project_id == folder.project_id,
                Asset.content_hash == digest,
            )
        )
        if existing is not None:
            return existing
        raise
    db.refresh(asset)
    logger.info(
        "video_uploaded asset_id=%s duration_ms=%s fps=%s %sx%s",
        asset.id,
        asset.duration_ms,
        asset.fps,
        asset.width,
        asset.height,
    )
    return asset
