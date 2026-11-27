"""标注 PUT/GET。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.annotation.registry import INTERNAL_FORMAT, get_registry
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
from app.models.annotation import Annotation
from app.models.dataset import Dataset, DatasetAsset

router = APIRouter(tags=["annotations"])
logger = get_logger("labeltrace.api.annotations")


class AnnotationPut(BaseModel):
    shapes: dict[str, Any] = Field(
        ...,
        description='{"format":"xyxy_abs","items":[{"type":"rect","cls":0,"bbox":[x1,y1,x2,y2]}]}',
    )
    status: Literal["draft", "submitted"] = "draft"


class AnnotationOut(BaseModel):
    dataset_id: UUID
    asset_id: UUID
    shapes: dict[str, Any]
    status: str
    updated_by: str
    updated_at: datetime | None = None


class SubmitDraftsOut(BaseModel):
    updated: int
    already_submitted: int
    without_annotation: int


def _empty_shapes() -> dict[str, Any]:
    return {"format": INTERNAL_FORMAT, "items": []}


@router.put(
    "/datasets/{dataset_id}/assets/{asset_id}/annotation",
    response_model=AnnotationOut,
)
def put_annotation(
    dataset_id: UUID,
    asset_id: UUID,
    body: AnnotationPut,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AnnotationOut:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    member = db.get(DatasetAsset, (dataset_id, asset_id))
    if member is None:
        raise ValidationAppError("素材不是该数据集成员，无法标注")

    enabled = list(ds.enabled_annotation_types or ["rect"])
    shapes = get_registry().validate_shapes(body.shapes, enabled_types=enabled)

    ann = db.scalar(
        select(Annotation).where(
            Annotation.dataset_id == dataset_id,
            Annotation.asset_id == asset_id,
        )
    )
    if ann is None:
        ann = Annotation(
            dataset_id=dataset_id,
            asset_id=asset_id,
            shapes=shapes,
            status=body.status,
            updated_by=user.id,
        )
        db.add(ann)
    else:
        ann.shapes = shapes
        ann.status = body.status
        ann.updated_by = user.id
    db.commit()
    db.refresh(ann)
    logger.info(
        "annotation_saved dataset_id=%s asset_id=%s items=%s status=%s",
        dataset_id,
        asset_id,
        len(shapes["items"]),
        body.status,
    )
    return AnnotationOut(
        dataset_id=ann.dataset_id,
        asset_id=ann.asset_id,
        shapes=ann.shapes,
        status=ann.status,
        updated_by=ann.updated_by,
        updated_at=ann.updated_at,
    )


@router.get(
    "/datasets/{dataset_id}/assets/{asset_id}/annotation",
    response_model=AnnotationOut,
)
def get_annotation(
    dataset_id: UUID,
    asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> AnnotationOut:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    member = db.get(DatasetAsset, (dataset_id, asset_id))
    if member is None:
        raise NotFoundError("素材不是该数据集成员")

    ann = db.scalar(
        select(Annotation).where(
            Annotation.dataset_id == dataset_id,
            Annotation.asset_id == asset_id,
        )
    )
    if ann is None:
        return AnnotationOut(
            dataset_id=dataset_id,
            asset_id=asset_id,
            shapes=_empty_shapes(),
            status="draft",
            updated_by=user.id,
            updated_at=None,
        )
    return AnnotationOut(
        dataset_id=ann.dataset_id,
        asset_id=ann.asset_id,
        shapes=ann.shapes,
        status=ann.status,
        updated_by=ann.updated_by,
        updated_at=ann.updated_at,
    )


@router.post(
    "/datasets/{dataset_id}/annotations/submit-drafts",
    response_model=SubmitDraftsOut,
)
def submit_all_drafts(
    dataset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SubmitDraftsOut:
    """将本数据集成员中状态为 draft 的工作标注全部改为 submitted（不改 shapes）。"""
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")

    member_ids = list(
        db.scalars(
            select(DatasetAsset.asset_id).where(
                DatasetAsset.dataset_id == dataset_id
            )
        ).all()
    )
    if not member_ids:
        return SubmitDraftsOut(
            updated=0, already_submitted=0, without_annotation=0
        )

    anns = list(
        db.scalars(
            select(Annotation).where(
                Annotation.dataset_id == dataset_id,
                Annotation.asset_id.in_(member_ids),
            )
        ).all()
    )
    by_asset = {a.asset_id: a for a in anns}
    updated = 0
    already = 0
    for aid in member_ids:
        ann = by_asset.get(aid)
        if ann is None:
            continue
        if ann.status == "submitted":
            already += 1
            continue
        if ann.status == "draft":
            ann.status = "submitted"
            ann.updated_by = str(user.id)
            updated += 1
    without = len(member_ids) - len(by_asset)
    if updated:
        db.commit()
    logger.info(
        "annotations_submit_drafts dataset_id=%s updated=%s already=%s without=%s",
        dataset_id,
        updated,
        already,
        without,
    )
    return SubmitDraftsOut(
        updated=updated,
        already_submitted=already,
        without_annotation=without,
    )
