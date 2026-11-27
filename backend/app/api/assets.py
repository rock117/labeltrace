"""素材上传与内容 API。"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
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
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.asset import Asset
from app.models.folder import Folder
from app.services.assets import (
    content_disposition_attachment,
    delete_asset,
    get_asset_for_member,
    move_asset,
    read_asset_bytes,
    upload_image_to_folder,
)
from app.services.video import VIDEO_EXTS, upload_video_to_folder
from pathlib import PurePosixPath

router = APIRouter(tags=["assets"])
logger = get_logger("labeltrace.api.assets")


class AssetOut(BaseModel):
    id: UUID
    project_id: UUID
    media_kind: Literal["image", "video", "frame"]
    folder_id: UUID | None
    library_visible: bool
    origin: str
    content_hash: str
    storage_backend: str
    storage_key: str
    filename: str
    mime: str | None
    width: int | None = None
    height: int | None = None
    duration_ms: int | None = None
    fps: float | None = None
    parent_video_id: UUID | None = None
    frame_index: int | None = None
    extract_job_id: UUID | None = None

    model_config = {"from_attributes": True}


class FolderAssetsPage(BaseModel):
    items: list[AssetOut]
    total: int
    limit: int
    offset: int


def _ensure_folder_write(
    db: Session, folder_id: UUID, user_id: str
) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise NotFoundError("目录不存在")
    m = get_membership(db, folder.project_id, user_id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    if not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    return folder


@router.post(
    "/folders/{folder_id}/assets",
    response_model=AssetOut,
    status_code=201,
)
async def upload_folder_asset(
    folder_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
) -> Asset:
    _ensure_folder_write(db, folder_id, user.id)
    data = await file.read()
    if not data:
        from app.core.errors import ValidationAppError

        raise ValidationAppError("空文件")
    name = file.filename or "upload.bin"
    ext = PurePosixPath(name.replace("\\", "/")).suffix.lower()
    ctype = file.content_type or ""
    if ext in VIDEO_EXTS or ctype.startswith("video/"):
        asset = upload_video_to_folder(
            db,
            folder_id=folder_id,
            filename=name,
            data=data,
            content_type=file.content_type,
            user_id=user.id,
        )
    else:
        asset = upload_image_to_folder(
            db,
            folder_id=folder_id,
            filename=name,
            data=data,
            content_type=file.content_type,
            user_id=user.id,
        )
    return asset


@router.get("/folders/{folder_id}/assets", response_model=FolderAssetsPage)
def list_folder_assets(
    folder_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    media_kind: Annotated[
        Literal["image", "video"] | None,
        Query(description="仅返回该类型；默认 image+video"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FolderAssetsPage:
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise NotFoundError("目录不存在")
    m = get_membership(db, folder.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    kinds: tuple[str, ...] = (media_kind,) if media_kind else ("image", "video")
    base = (
        Asset.folder_id == folder_id,
        Asset.library_visible.is_(True),
        Asset.media_kind.in_(kinds),
    )
    total = db.scalar(select(func.count()).select_from(Asset).where(*base)) or 0
    items = list(
        db.scalars(
            select(Asset)
            .where(*base)
            .order_by(Asset.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
    return FolderAssetsPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(
    asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Asset:
    return get_asset_for_member(db, asset_id, user.id)


class AssetRename(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def rename_asset(
    asset_id: UUID,
    body: AssetRename,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Asset:
    asset = get_asset_for_member(db, asset_id, user.id)
    m = get_membership(db, asset.project_id, user.id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    filename = body.filename.strip()
    if not filename:
        raise ValidationAppError("文件名无效")
    # 仅改展示名；storage_key / 二进制不变
    asset.filename = filename
    db.commit()
    db.refresh(asset)
    logger.info(
        "asset_renamed asset_id=%s filename=%s storage_key=%s",
        asset_id,
        filename,
        asset.storage_key,
    )
    return asset


@router.get("/assets/{asset_id}/content")
def get_asset_content(
    asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    asset = get_asset_for_member(db, asset_id, user.id)
    body = read_asset_bytes(asset)
    headers = {
        "Content-Disposition": content_disposition_attachment(asset.filename),
        "X-Content-Hash": asset.content_hash,
        "X-Storage-Key": asset.storage_key,
    }
    return Response(
        content=body,
        media_type=asset.mime or "application/octet-stream",
        headers=headers,
    )


@router.get("/assets/{asset_id}/poster")
def get_asset_poster(
    asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """视频列表封面：小 JPEG；缺失时服务端用 ffmpeg 生成并缓存。"""
    from app.services.poster import get_poster_for_member

    _, body = get_poster_for_member(db, asset_id, user.id)
    return Response(
        content=body,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


class AssetMove(BaseModel):
    folder_id: UUID = Field(..., description="目标目录")


@router.post("/assets/{asset_id}/move", response_model=AssetOut)
def move_asset_api(
    asset_id: UUID,
    body: AssetMove,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Asset:
    return move_asset(
        db, asset_id=asset_id, target_folder_id=body.folder_id, user_id=user.id
    )


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset_api(
    asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    delete_asset(db, asset_id=asset_id, user_id=user.id)
    return Response(status_code=204)
