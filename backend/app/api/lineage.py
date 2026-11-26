"""素材血缘。"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user, get_membership
from app.core.errors import ForbiddenError, NotFoundError
from app.db.session import get_db
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.models.dataset import Dataset, DatasetAsset
from app.models.folder import Folder
from app.models.tag import AssetTag, Tag
from app.models.version import DatasetVersion

router = APIRouter(tags=["lineage"])


@router.get("/assets/{asset_id}/lineage")
def asset_lineage(
    asset_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError("素材不存在")
    m = get_membership(db, asset.project_id, user.id)
    if m is None:
        raise ForbiddenError("不是项目成员")

    folder = db.get(Folder, asset.folder_id) if asset.folder_id else None
    tags = list(
        db.scalars(
            select(Tag)
            .join(AssetTag, AssetTag.tag_id == Tag.id)
            .where(AssetTag.asset_id == asset_id)
        ).all()
    )
    members = list(
        db.scalars(
            select(DatasetAsset).where(DatasetAsset.asset_id == asset_id)
        ).all()
    )
    datasets = []
    for row in members:
        ds = db.get(Dataset, row.dataset_id)
        if not ds:
            continue
        ann = db.scalar(
            select(Annotation).where(
                Annotation.dataset_id == ds.id,
                Annotation.asset_id == asset_id,
            )
        )
        datasets.append(
            {
                "datasetId": str(ds.id),
                "name": ds.name,
                "split": row.split,
                "annotationUpdatedBy": ann.updated_by if ann else None,
                "annotationUpdatedAt": (
                    ann.updated_at.isoformat() if ann else None
                ),
            }
        )

    versions: list[dict[str, Any]] = []
    aid = str(asset_id)
    for ver in db.scalars(select(DatasetVersion)).all():
        ds = db.get(Dataset, ver.dataset_id)
        if ds is None or ds.project_id != asset.project_id:
            continue
        entries = (ver.manifest or {}).get("entries") or []
        if any(e.get("assetId") == aid for e in entries):
            versions.append(
                {
                    "versionId": str(ver.id),
                    "name": ver.name,
                    "datasetId": str(ver.dataset_id),
                }
            )

    out: dict[str, Any] = {
        "assetId": str(asset.id),
        "origin": asset.origin,
        "importId": str(asset.import_id) if asset.import_id else None,
        "path": folder.path if folder else None,
        "filename": asset.filename,
        "mediaKind": asset.media_kind,
        "libraryVisible": asset.library_visible,
        "tags": [{"id": str(t.id), "name": t.name} for t in tags],
        "datasets": datasets,
        "versions": versions,
    }
    if asset.media_kind == "frame":
        out["parentVideoId"] = (
            str(asset.parent_video_id) if asset.parent_video_id else None
        )
        out["frameIndex"] = asset.frame_index
        out["extractJobId"] = (
            str(asset.extract_job_id) if asset.extract_job_id else None
        )
    return out
