"""视频封面（列表缩略图）：旁路存 {storage_key}.poster.jpg。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.media.ffmpeg import extract_poster_frame, write_bytes_to_temp
from app.models.asset import Asset
from app.services.assets import get_asset_for_member, read_asset_bytes
from app.storage.factory import get_blob_store

logger = get_logger("labeltrace.poster")


def poster_key_for(storage_key: str) -> str:
    return f"{storage_key}.poster.jpg"


def ensure_video_poster(asset: Asset, *, at_sec: float | None = None) -> bytes:
    """返回封面 JPEG；不存在则用 ffmpeg 生成并写入 BlobStore。"""
    if asset.media_kind != "video":
        raise ValidationAppError("仅视频支持封面")
    store = get_blob_store(asset.storage_backend)
    key = poster_key_for(asset.storage_key)
    if store.exists(key):
        return b"".join(store.get(key))

    if not store.exists(asset.storage_key):
        raise NotFoundError("素材文件缺失")

    video_bytes = read_asset_bytes(asset)
    ext = Path(asset.filename or "video.mp4").suffix or ".mp4"
    tmp_v: Path | None = None
    tmp_p: Path | None = None
    try:
        tmp_v = write_bytes_to_temp(video_bytes, ext)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            tmp_p = Path(f.name)
        seek = at_sec
        if seek is None:
            if asset.duration_ms and asset.duration_ms > 2000:
                seek = min(1.0, asset.duration_ms / 1000.0 * 0.05)
            else:
                seek = 0.1
        extract_poster_frame(tmp_v, tmp_p, at_sec=seek)
        data = tmp_p.read_bytes()
    finally:
        for p in (tmp_v, tmp_p):
            if p is not None:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass

    store.put(key, data, content_type="image/jpeg")
    logger.info(
        "poster_created asset_id=%s key=%s bytes=%s",
        asset.id,
        key,
        len(data),
    )
    return data


def get_poster_for_member(
    db: Session, asset_id: UUID, user_id: str
) -> tuple[Asset, bytes]:
    asset = get_asset_for_member(db, asset_id, user_id)
    if asset.media_kind != "video":
        raise ValidationAppError("仅视频有封面")
    data = ensure_video_poster(asset)
    return asset, data
