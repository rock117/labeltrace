"""扁平标签 API。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import ALL_ROLES, WRITE_ROLES, CurrentUser, get_current_user, get_membership, has_any_role, require_project_role
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.asset import Asset
from app.models.project import Membership
from app.models.tag import AssetTag, Tag

router = APIRouter(tags=["tags"])
logger = get_logger("labeltrace.api.tags")


class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)


class TagOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str

    model_config = {"from_attributes": True}


class TagIdsIn(BaseModel):
    tag_ids: list[UUID]


@router.post("/projects/{project_id}/tags", response_model=TagOut, status_code=201)
def create_tag(
    project_id: UUID,
    body: TagCreate,
    _: Annotated[Membership, Depends(require_project_role(*WRITE_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> Tag:
    name = body.name.strip()
    tag = Tag(project_id=project_id, name=name)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("标签名称已存在") from None
    db.refresh(tag)
    logger.info("tag_created tag_id=%s name=%s", tag.id, tag.name)
    return tag


@router.get("/projects/{project_id}/tags", response_model=list[TagOut])
def list_tags(
    project_id: UUID,
    _: Annotated[Membership, Depends(require_project_role(*ALL_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> list[Tag]:
    return list(
        db.scalars(
            select(Tag).where(Tag.project_id == project_id).order_by(Tag.name)
        ).all()
    )


@router.put("/assets/{asset_id}/tags", response_model=list[TagOut])
def set_asset_tags(
    asset_id: UUID,
    body: TagIdsIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Tag]:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError("素材不存在")
    m = get_membership(db, asset.project_id, user.id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    tags = list(
        db.scalars(
            select(Tag).where(
                Tag.project_id == asset.project_id, Tag.id.in_(body.tag_ids)
            )
        ).all()
    )
    if len(tags) != len(set(body.tag_ids)):
        raise ValidationAppError("含非法或不属于本项目的标签")
    existing = db.scalars(
        select(AssetTag).where(AssetTag.asset_id == asset_id)
    ).all()
    for row in existing:
        db.delete(row)
    for t in tags:
        db.add(AssetTag(asset_id=asset_id, tag_id=t.id))
    db.commit()
    return tags


@router.get("/assets/{asset_id}/tags", response_model=list[TagOut])
def get_asset_tags(
    asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Tag]:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError("素材不存在")
    m = get_membership(db, asset.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return list(
        db.scalars(
            select(Tag)
            .join(AssetTag, AssetTag.tag_id == Tag.id)
            .where(AssetTag.asset_id == asset_id)
            .order_by(Tag.name)
        ).all()
    )


@router.get("/projects/{project_id}/assets", response_model=list[dict])
def filter_assets_by_tags(
    project_id: UUID,
    _: Annotated[Membership, Depends(require_project_role(*ALL_ROLES))],
    db: Annotated[Session, Depends(get_db)],
    tag_ids: list[UUID] = Query(default=[]),
) -> list[dict]:
    """库可见素材；多 tag_ids 取交集。"""
    stmt = select(Asset).where(
        Asset.project_id == project_id,
        Asset.library_visible.is_(True),
        Asset.media_kind.in_(("image", "video")),
    )
    for tid in tag_ids:
        stmt = stmt.where(
            Asset.id.in_(
                select(AssetTag.asset_id).where(AssetTag.tag_id == tid)
            )
        )
    assets = db.scalars(stmt.order_by(Asset.created_at.desc())).all()
    return [
        {
            "id": a.id,
            "filename": a.filename,
            "media_kind": a.media_kind,
            "folder_id": a.folder_id,
        }
        for a in assets
    ]
