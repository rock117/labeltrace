"""数据集 API（创建、成员、入集抽帧）。"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import (
    WRITE_ROLES,
    CurrentUser,
    get_current_user,
    get_membership,
    require_project_role,
)
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.asset import Asset
from app.models.dataset import Dataset, DatasetAsset, DatasetClass
from app.models.frame_extract_job import FrameExtractJob
from app.models.project import Membership

router = APIRouter(tags=["datasets"])
logger = get_logger("labeltrace.api.datasets")

Split = Literal["train", "val", "test", "unassigned"]


class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    classes: list[str] = Field(default_factory=list)
    enabled_annotation_types: list[str] = Field(
        default_factory=lambda: ["rect"],
        alias="enabledAnnotationTypes",
    )

    model_config = {"populate_by_name": True}


class DatasetOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    classes: list[str]
    enabled_annotation_types: list[str]

    model_config = {"from_attributes": True}


class AddAssetsIn(BaseModel):
    asset_ids: list[UUID] = Field(..., min_length=1)
    split: Split = "unassigned"


class DatasetAssetOut(BaseModel):
    asset_id: UUID
    split: str
    media_kind: str
    filename: str


class AddExtractFramesIn(BaseModel):
    extract_job_id: UUID
    split: Split = "unassigned"


def _dataset_out(db: Session, ds: Dataset) -> DatasetOut:
    classes = list(
        db.scalars(
            select(DatasetClass)
            .where(DatasetClass.dataset_id == ds.id)
            .order_by(DatasetClass.idx)
        ).all()
    )
    return DatasetOut(
        id=ds.id,
        project_id=ds.project_id,
        name=ds.name,
        classes=[c.name for c in classes],
        enabled_annotation_types=list(ds.enabled_annotation_types or ["rect"]),
    )


@router.post(
    "/projects/{project_id}/datasets",
    response_model=DatasetOut,
    status_code=201,
)
def create_dataset(
    project_id: UUID,
    body: DatasetCreate,
    _: Annotated[Membership, Depends(require_project_role(*WRITE_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> DatasetOut:
    types = body.enabled_annotation_types or ["rect"]
    ds = Dataset(
        project_id=project_id,
        name=body.name.strip(),
        enabled_annotation_types=types,
    )
    db.add(ds)
    db.flush()
    for i, name in enumerate(body.classes):
        db.add(DatasetClass(dataset_id=ds.id, idx=i, name=name.strip()))
    db.commit()
    db.refresh(ds)
    logger.info("dataset_created dataset_id=%s", ds.id)
    return _dataset_out(db, ds)


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DatasetOut:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    return _dataset_out(db, ds)


@router.post("/datasets/{dataset_id}/assets", response_model=list[DatasetAssetOut])
def add_assets(
    dataset_id: UUID,
    body: AddAssetsIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DatasetAssetOut]:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or m.role not in WRITE_ROLES:
        raise ForbiddenError("权限不足")

    out: list[DatasetAssetOut] = []
    for aid in body.asset_ids:
        asset = db.get(Asset, aid)
        if asset is None or asset.project_id != ds.project_id:
            raise ValidationAppError(f"跨项目或无效素材: {aid}")
        if asset.media_kind == "video":
            raise ValidationAppError("不能将 video 直接加入数据集，请使用 frame/image")
        existing = db.get(DatasetAsset, (dataset_id, aid))
        if existing is None:
            db.add(
                DatasetAsset(
                    dataset_id=dataset_id, asset_id=aid, split=body.split
                )
            )
            split = body.split
        else:
            split = existing.split
        out.append(
            DatasetAssetOut(
                asset_id=aid,
                split=split,
                media_kind=asset.media_kind,
                filename=asset.filename,
            )
        )
    db.commit()
    logger.info(
        "dataset_assets_added dataset_id=%s count=%s", dataset_id, len(body.asset_ids)
    )
    return out


@router.delete("/datasets/{dataset_id}/assets/{asset_id}", status_code=204)
def remove_asset(
    dataset_id: UUID,
    asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or m.role not in WRITE_ROLES:
        raise ForbiddenError("权限不足")
    row = db.get(DatasetAsset, (dataset_id, asset_id))
    if row is None:
        raise NotFoundError("成员不存在")
    db.delete(row)
    db.commit()


class SplitUpdate(BaseModel):
    split: Split


@router.patch(
    "/datasets/{dataset_id}/assets/{asset_id}",
    response_model=DatasetAssetOut,
)
def update_split(
    dataset_id: UUID,
    asset_id: UUID,
    body: SplitUpdate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DatasetAssetOut:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or m.role not in WRITE_ROLES:
        raise ForbiddenError("权限不足")
    row = db.get(DatasetAsset, (dataset_id, asset_id))
    if row is None:
        raise NotFoundError("成员不存在")
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError("素材不存在")
    row.split = body.split
    db.commit()
    return DatasetAssetOut(
        asset_id=asset_id,
        split=row.split,
        media_kind=asset.media_kind,
        filename=asset.filename,
    )


@router.get("/datasets/{dataset_id}/assets", response_model=list[DatasetAssetOut])
def list_members(
    dataset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DatasetAssetOut]:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    rows = db.scalars(
        select(DatasetAsset).where(DatasetAsset.dataset_id == dataset_id)
    ).all()
    out: list[DatasetAssetOut] = []
    for r in rows:
        asset = db.get(Asset, r.asset_id)
        if asset is None:
            continue
        out.append(
            DatasetAssetOut(
                asset_id=r.asset_id,
                split=r.split,
                media_kind=asset.media_kind,
                filename=asset.filename,
            )
        )
    return out


@router.post(
    "/datasets/{dataset_id}/assets/from-extract",
    response_model=list[DatasetAssetOut],
)
def add_remaining_extract_frames(
    dataset_id: UUID,
    body: AddExtractFramesIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DatasetAssetOut]:
    """将某次抽帧审查后剩余 frame 全部加入数据集。"""
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or m.role not in WRITE_ROLES:
        raise ForbiddenError("权限不足")
    extract = db.get(FrameExtractJob, body.extract_job_id)
    if extract is None or extract.project_id != ds.project_id:
        raise NotFoundError("抽帧任务不存在")
    frames = list(
        db.scalars(
            select(Asset).where(
                Asset.extract_job_id == body.extract_job_id,
                Asset.media_kind == "frame",
            )
        ).all()
    )
    if not frames:
        return []
    return add_assets(
        dataset_id=dataset_id,
        body=AddAssetsIn(asset_ids=[f.id for f in frames], split=body.split),
        user=user,
        db=db,
    )
