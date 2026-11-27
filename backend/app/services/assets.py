"""素材上传与内容读取用例。"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.asset import Asset
from app.models.folder import Folder
from app.storage.factory import get_blob_store, get_default_write_backend

logger = get_logger("labeltrace.assets")

IMAGE_MIME_PREFIXES = ("image/",)
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def content_disposition_attachment(filename: str) -> str:
    """RFC 5987：ASCII fallback + UTF-8'' 编码文件名。"""
    from urllib.parse import quote

    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in filename)
    if not ascii_name:
        ascii_name = "download"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded}"


def _ext_from_filename(filename: str) -> str:
    ext = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    return ext if ext else ".bin"


def _storage_key(project_id: UUID, content_hash: str, ext: str) -> str:
    safe_ext = ext if ext.startswith(".") else f".{ext}"
    # 仅 ASCII 扩展名
    safe_ext = "".join(c for c in safe_ext if c.isalnum() or c == ".")[:16] or ".bin"
    return f"proj/{project_id}/assets/{content_hash}{safe_ext}"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def upload_image_to_folder(
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

    name = (filename or "image.bin").strip() or "image.bin"
    ext = _ext_from_filename(name)
    mime = content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"

    if ext not in ALLOWED_IMAGE_EXTS and not mime.startswith("image/"):
        raise ValidationAppError("仅支持图片上传（image）")

    digest = _sha256(data)
    existing = db.scalar(
        select(Asset).where(
            Asset.project_id == folder.project_id,
            Asset.content_hash == digest,
        )
    )
    if existing is not None:
        logger.info(
            "asset_dedup_hit asset_id=%s content_hash=%s user_id=%s",
            existing.id,
            digest,
            user_id,
        )
        return existing

    backend = get_default_write_backend()
    key = _storage_key(folder.project_id, digest, ext)
    store = get_blob_store(backend)
    store.put(key, data, content_type=mime)

    asset = Asset(
        project_id=folder.project_id,
        media_kind="image",
        folder_id=folder.id,
        library_visible=True,
        origin="upload",
        content_hash=digest,
        storage_backend=backend,
        storage_key=key,
        filename=name,
        mime=mime,
    )
    db.add(asset)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "asset_create_failed folder_id=%s content_hash=%s",
            folder_id,
            digest,
        )
        # 竞态去重
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
        "asset_uploaded asset_id=%s media_kind=image storage_key=%s filename=%s",
        asset.id,
        asset.storage_key,
        asset.filename,
    )
    return asset


def get_asset_for_member(db: Session, asset_id: UUID, user_id: str) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError("素材不存在")
    from app.auth.deps import get_membership

    m = get_membership(db, asset.project_id, user_id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return asset


def read_asset_bytes(asset: Asset) -> bytes:
    store = get_blob_store(asset.storage_backend)
    if not store.exists(asset.storage_key):
        logger.error(
            "blob_missing asset_id=%s backend=%s key=%s",
            asset.id,
            asset.storage_backend,
            asset.storage_key,
        )
        raise NotFoundError("素材文件缺失")
    return b"".join(store.get(asset.storage_key))


def move_asset(
    db: Session,
    *,
    asset_id: UUID,
    target_folder_id: UUID,
    user_id: str,
) -> Asset:
    asset = get_asset_for_member(db, asset_id, user_id)
    if not asset.library_visible:
        raise ValidationAppError("非库可见素材不能移动到目录")
    target = db.get(Folder, target_folder_id)
    if target is None or target.project_id != asset.project_id:
        raise NotFoundError("目标目录不存在")
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role
    from app.core.errors import ForbiddenError as _Forbidden

    m = get_membership(db, asset.project_id, user_id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise _Forbidden("权限不足")

    old_key = asset.storage_key
    asset.folder_id = target.id
    db.commit()
    db.refresh(asset)
    logger.info(
        "asset_moved asset_id=%s folder_id=%s storage_key=%s unchanged_key=%s",
        asset.id,
        target.id,
        asset.storage_key,
        old_key == asset.storage_key,
    )
    return asset


def delete_asset(db: Session, *, asset_id: UUID, user_id: str) -> None:
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role
    from app.core.errors import ConflictError, ForbiddenError as _Forbidden
    from app.services.asset_refs import asset_has_references

    asset = get_asset_for_member(db, asset_id, user_id)
    m = get_membership(db, asset.project_id, user_id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise _Forbidden("权限不足")
    if asset_has_references(db, asset.id):
        raise ConflictError("素材仍被数据集或版本引用，禁止硬删")

    store = get_blob_store(asset.storage_backend)
    key = asset.storage_key
    backend = asset.storage_backend
    db.delete(asset)
    db.commit()
    try:
        store.delete(key)
    except Exception:
        logger.exception(
            "blob_delete_failed asset_id=%s backend=%s key=%s",
            asset_id,
            backend,
            key,
        )
        # 元数据已删；二进制残留可运维 GC，不向客户端伪装成功后的静默
        raise
    logger.info("asset_deleted asset_id=%s key=%s", asset_id, key)
