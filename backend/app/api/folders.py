"""目录树 CRUD。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import (
    ALL_ROLES,
    WRITE_ROLES,
    CurrentUser,
    get_current_user,
    require_project_role,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.asset import Asset
from app.models.folder import Folder
from app.models.project import Membership

router = APIRouter(tags=["folders"])
logger = get_logger("labeltrace.folders")


class FolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    parent_id: UUID | None = None


class FolderOut(BaseModel):
    id: UUID
    project_id: UUID
    parent_id: UUID | None
    name: str
    path: str
    # 该目录内直接存放的库可见视频 / 图片数（不含子孙目录、不含 frame）
    video_count: int = 0
    image_count: int = 0

    model_config = {"from_attributes": True}


def _direct_media_counts(
    db: Session, folder_ids: list[UUID]
) -> dict[UUID, tuple[int, int]]:
    counts = {fid: (0, 0) for fid in folder_ids}
    if not folder_ids:
        return counts
    rows = db.execute(
        select(Asset.folder_id, Asset.media_kind, func.count())
        .where(
            Asset.folder_id.in_(folder_ids),
            Asset.library_visible.is_(True),
            Asset.media_kind.in_(("image", "video")),
        )
        .group_by(Asset.folder_id, Asset.media_kind)
    ).all()
    video: dict[UUID, int] = {}
    image: dict[UUID, int] = {}
    for folder_id, kind, n in rows:
        if folder_id is None:
            continue
        if kind == "video":
            video[folder_id] = int(n)
        elif kind == "image":
            image[folder_id] = int(n)
    return {fid: (video.get(fid, 0), image.get(fid, 0)) for fid in folder_ids}


def _build_path(parent: Folder | None, name: str) -> str:
    if parent is None:
        return name
    return f"{parent.path}/{name}"


@router.post(
    "/projects/{project_id}/folders",
    response_model=FolderOut,
    status_code=201,
)
def create_folder(
    project_id: UUID,
    body: FolderCreate,
    _: Annotated[Membership, Depends(require_project_role(*WRITE_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> Folder:
    name = body.name.strip()
    if not name:
        raise ConflictError("目录名无效", code="invalid_folder_name")

    parent: Folder | None = None
    if body.parent_id is not None:
        parent = db.get(Folder, body.parent_id)
        if parent is None or parent.project_id != project_id:
            raise NotFoundError("父目录不存在")

    folder = Folder(
        project_id=project_id,
        parent_id=body.parent_id,
        name=name,
        path=_build_path(parent, name),
    )
    db.add(folder)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning(
            "folder_name_conflict project_id=%s parent_id=%s name=%s",
            project_id,
            body.parent_id,
            name,
        )
        raise ConflictError("同级目录名称已存在") from None
    db.refresh(folder)
    logger.info(
        "folder_created folder_id=%s path=%s",
        folder.id,
        folder.path,
    )
    return folder


@router.get("/projects/{project_id}/folders", response_model=list[FolderOut])
def list_folders(
    project_id: UUID,
    _: Annotated[Membership, Depends(require_project_role(*ALL_ROLES))],
    db: Annotated[Session, Depends(get_db)],
    parent_id: UUID | None = Query(default=None),
) -> list[FolderOut]:
    stmt = select(Folder).where(Folder.project_id == project_id)
    if parent_id is None:
        stmt = stmt.where(Folder.parent_id.is_(None))
    else:
        stmt = stmt.where(Folder.parent_id == parent_id)
    stmt = stmt.order_by(Folder.name)
    folders = list(db.scalars(stmt).all())
    counts = _direct_media_counts(db, [f.id for f in folders])
    return [
        FolderOut(
            id=f.id,
            project_id=f.project_id,
            parent_id=f.parent_id,
            name=f.name,
            path=f.path,
            video_count=counts[f.id][0],
            image_count=counts[f.id][1],
        )
        for f in folders
    ]


@router.get("/folders/{folder_id}", response_model=FolderOut)
def get_folder(
    folder_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise NotFoundError("目录不存在")
    from app.auth.deps import get_membership

    m = get_membership(db, folder.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return folder


class FolderRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


@router.patch("/folders/{folder_id}", response_model=FolderOut)
def rename_folder(
    folder_id: UUID,
    body: FolderRename,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Folder:
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role

    folder = db.get(Folder, folder_id)
    if folder is None:
        raise NotFoundError("目录不存在")
    m = get_membership(db, folder.project_id, user.id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")

    name = body.name.strip()
    if not name:
        raise ConflictError("目录名无效", code="invalid_folder_name")

    parent: Folder | None = None
    if folder.parent_id is not None:
        parent = db.get(Folder, folder.parent_id)

    old_path = folder.path
    new_path = _build_path(parent, name)
    folder.name = name
    folder.path = new_path

    descendants = list(
        db.scalars(
            select(Folder).where(
                Folder.project_id == folder.project_id,
                Folder.path.like(f"{old_path}/%"),
            )
        ).all()
    )
    for child in descendants:
        child.path = new_path + child.path[len(old_path) :]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("同级目录名称已存在") from None
    db.refresh(folder)
    logger.info(
        "folder_renamed folder_id=%s old_path=%s new_path=%s",
        folder_id,
        old_path,
        new_path,
    )
    return folder
