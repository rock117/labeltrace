"""数据集 API（创建、成员、入集抽帧）。"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import (
    ALL_ROLES,
    OWNER_ROLES,
    WRITE_ROLES,
    CurrentUser,
    get_current_user,
    get_membership,
    has_any_role,
    require_project_role,
)
from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.models.dataset import Dataset, DatasetAsset
from app.models.frame_extract_job import FrameExtractJob
from app.models.project import Membership
from app.services.assignment import (
    must_list_mine_only,
    resolve_assignee_user_id,
    usernames_for_ids,
)
from app.services.project_classes import (
    classes_as_dicts,
    enable_all_project_classes,
    set_dataset_class_ids,
)

router = APIRouter(tags=["datasets"])
logger = get_logger("labeltrace.api.datasets")

Split = Literal["train", "val", "test", "unassigned"]


class DatasetClassOut(BaseModel):
    id: UUID
    name: str
    idx: int
    color: str | None = None


class DatasetCreate(BaseModel):
    """只建工作区。类别在项目词表创建，再经 PUT /classes 按 classIds 启用。"""

    name: str = Field(..., min_length=1, max_length=256)
    enabled_annotation_types: list[str] = Field(
        default_factory=lambda: ["rect"],
        alias="enabledAnnotationTypes",
    )

    model_config = {"populate_by_name": True}


class DatasetOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    classes: list[DatasetClassOut]
    enabled_annotation_types: list[str]

    model_config = {"from_attributes": True}


class DatasetClassesIn(BaseModel):
    class_ids: list[UUID] = Field(default_factory=list, alias="classIds")

    model_config = {"populate_by_name": True}


class AddAssetsIn(BaseModel):
    asset_ids: list[UUID] = Field(..., min_length=1)
    split: Split = "unassigned"


class DatasetAssetOut(BaseModel):
    asset_id: UUID
    split: str
    media_kind: str
    filename: str
    annotation_status: Literal["draft", "submitted"] | None = None
    assignee_user_id: str | None = None
    assignee_username: str | None = None


class AddExtractFramesIn(BaseModel):
    extract_job_id: UUID
    split: Split = "unassigned"


class MemberPatch(BaseModel):
    """split 与 assignee 均可选；显式传 assigneeUserId: null 表示清空分配。"""

    split: Split | None = None
    assignee_user_id: str | None = Field(
        default=None, alias="assigneeUserId"
    )

    model_config = {"populate_by_name": True}


class AssignmentsIn(BaseModel):
    asset_ids: list[UUID] = Field(..., min_length=1, alias="assetIds")
    assignee_user_id: str | None = Field(
        default=None, alias="assigneeUserId"
    )

    model_config = {"populate_by_name": True}


def _asset_out(
    asset_id: UUID,
    split: str,
    media_kind: str,
    filename: str,
    *,
    annotation_status: Literal["draft", "submitted"] | None = None,
    assignee_user_id: str | None = None,
    assignee_username: str | None = None,
) -> DatasetAssetOut:
    return DatasetAssetOut(
        asset_id=asset_id,
        split=split,
        media_kind=media_kind,
        filename=filename,
        annotation_status=annotation_status,
        assignee_user_id=assignee_user_id,
        assignee_username=assignee_username,
    )


def _dataset_out(db: Session, ds: Dataset) -> DatasetOut:
    rows = classes_as_dicts(db, ds.id)
    return DatasetOut(
        id=ds.id,
        project_id=ds.project_id,
        name=ds.name,
        classes=[
            DatasetClassOut(
                id=UUID(r["id"]),
                name=r["name"],
                idx=r["idx"],
                color=r.get("color"),
            )
            for r in rows
        ],
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
    enable_all_project_classes(db, ds.id, project_id)
    db.commit()
    db.refresh(ds)
    logger.info("dataset_created dataset_id=%s", ds.id)
    return _dataset_out(db, ds)


@router.get(
    "/projects/{project_id}/datasets",
    response_model=list[DatasetOut],
)
def list_datasets(
    project_id: UUID,
    _: Annotated[Membership, Depends(require_project_role(*ALL_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> list[DatasetOut]:
    rows = list(
        db.scalars(
            select(Dataset)
            .where(Dataset.project_id == project_id)
            .order_by(Dataset.created_at.desc())
        ).all()
    )
    return [_dataset_out(db, ds) for ds in rows]


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


class DatasetRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


@router.patch("/datasets/{dataset_id}", response_model=DatasetOut)
def rename_dataset(
    dataset_id: UUID,
    body: DatasetRename,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DatasetOut:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    name = body.name.strip()
    if not name:
        raise ValidationAppError("数据集名称无效")
    ds.name = name
    db.commit()
    db.refresh(ds)
    logger.info("dataset_renamed dataset_id=%s name=%s", dataset_id, name)
    return _dataset_out(db, ds)


@router.put("/datasets/{dataset_id}/classes", response_model=DatasetOut)
def put_dataset_classes(
    dataset_id: UUID,
    body: DatasetClassesIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DatasetOut:
    """按顺序启用项目词表中的类别。停用仍被本集标注引用的类别返回 409。"""
    set_dataset_class_ids(
        db,
        dataset_id=dataset_id,
        class_ids=list(body.class_ids),
        user_id=user.id,
    )
    ds = db.get(Dataset, dataset_id)
    assert ds is not None
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
    if m is None or not has_any_role(m, WRITE_ROLES):
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
            row = DatasetAsset(
                dataset_id=dataset_id, asset_id=aid, split=body.split
            )
            db.add(row)
            assignee_uid = None
            split = body.split
        else:
            assignee_uid = existing.assignee_user_id
            split = existing.split
        out.append(
            _asset_out(
                aid,
                split,
                asset.media_kind,
                asset.filename,
                assignee_user_id=assignee_uid,
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
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    row = db.get(DatasetAsset, (dataset_id, asset_id))
    if row is None:
        raise NotFoundError("成员不存在")
    db.delete(row)
    db.commit()


@router.patch(
    "/datasets/{dataset_id}/assets/{asset_id}",
    response_model=DatasetAssetOut,
)
def patch_member(
    dataset_id: UUID,
    asset_id: UUID,
    body: MemberPatch,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DatasetAssetOut:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    row = db.get(DatasetAsset, (dataset_id, asset_id))
    if row is None:
        raise NotFoundError("成员不存在")
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError("素材不存在")
    if body.split is not None:
        row.split = body.split
    if "assignee_user_id" in body.model_fields_set:
        if not has_any_role(m, OWNER_ROLES):
            raise ForbiddenError("仅负责人可改任务分配")
        row.assignee_user_id = resolve_assignee_user_id(
            db, ds.project_id, body.assignee_user_id
        )
    db.commit()
    names = usernames_for_ids(
        db, [row.assignee_user_id] if row.assignee_user_id else []
    )
    return _asset_out(
        asset_id,
        row.split,
        asset.media_kind,
        asset.filename,
        assignee_user_id=row.assignee_user_id,
        assignee_username=names.get(row.assignee_user_id)
        if row.assignee_user_id
        else None,
    )


@router.post(
    "/datasets/{dataset_id}/assignments",
    response_model=list[DatasetAssetOut],
)
def assign_members(
    dataset_id: UUID,
    body: AssignmentsIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[DatasetAssetOut]:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None or not has_any_role(m, OWNER_ROLES):
        raise ForbiddenError("仅负责人可分配任务")
    target = resolve_assignee_user_id(db, ds.project_id, body.assignee_user_id)
    names = usernames_for_ids(db, [target] if target else [])
    out: list[DatasetAssetOut] = []
    for aid in body.asset_ids:
        row = db.get(DatasetAsset, (dataset_id, aid))
        if row is None:
            raise NotFoundError(f"成员不存在: {aid}")
        asset = db.get(Asset, aid)
        if asset is None:
            raise NotFoundError(f"素材不存在: {aid}")
        row.assignee_user_id = target
        out.append(
            _asset_out(
                aid,
                row.split,
                asset.media_kind,
                asset.filename,
                assignee_user_id=target,
                assignee_username=names.get(target) if target else None,
            )
        )
    db.commit()
    logger.info(
        "dataset_assignments dataset_id=%s count=%s assignee=%s",
        dataset_id,
        len(body.asset_ids),
        target,
    )
    return out


@router.get("/datasets/{dataset_id}/assets", response_model=list[DatasetAssetOut])
def list_members(
    dataset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    mine: Annotated[bool, Query()] = False,
) -> list[DatasetAssetOut]:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")
    force_mine = must_list_mine_only(m)
    filter_mine = force_mine or mine
    q = select(DatasetAsset).where(DatasetAsset.dataset_id == dataset_id)
    if filter_mine:
        q = q.where(DatasetAsset.assignee_user_id == user.id)
    rows = list(db.scalars(q).all())
    asset_ids = [r.asset_id for r in rows]
    status_map: dict[UUID, tuple[str, bool]] = {}
    if asset_ids:
        for ann in db.scalars(
            select(Annotation).where(
                Annotation.dataset_id == dataset_id,
                Annotation.asset_id.in_(asset_ids),
            )
        ).all():
            items = (ann.shapes or {}).get("items") or []
            status_map[ann.asset_id] = (ann.status or "", bool(items))
    name_map = usernames_for_ids(
        db, [r.assignee_user_id for r in rows if r.assignee_user_id]
    )
    out: list[DatasetAssetOut] = []
    for r in rows:
        asset = db.get(Asset, r.asset_id)
        if asset is None:
            continue
        raw = status_map.get(r.asset_id)
        ann_status: Literal["draft", "submitted"] | None = None
        if raw is not None:
            st, has_shapes = raw
            if st == "submitted":
                ann_status = "submitted"
            elif st == "draft" or has_shapes:
                ann_status = "draft"
        out.append(
            _asset_out(
                r.asset_id,
                r.split,
                asset.media_kind,
                asset.filename,
                annotation_status=ann_status,
                assignee_user_id=r.assignee_user_id,
                assignee_username=name_map.get(r.assignee_user_id)
                if r.assignee_user_id
                else None,
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
    if m is None or not has_any_role(m, WRITE_ROLES):
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
