"""发版与变更摘要。"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.models.dataset import Dataset, DatasetAsset, DatasetClass
from app.models.version import DatasetVersion
from app.services.member_sources import build_member_sources

logger = get_logger("labeltrace.versions")


def _classes(db: Session, dataset_id: UUID) -> list[str]:
    return [
        c.name
        for c in db.scalars(
            select(DatasetClass)
            .where(DatasetClass.dataset_id == dataset_id)
            .order_by(DatasetClass.idx)
        ).all()
    ]


def _build_manifest(db: Session, dataset_id: UUID) -> dict[str, Any]:
    members = list(
        db.scalars(
            select(DatasetAsset).where(DatasetAsset.dataset_id == dataset_id)
        ).all()
    )
    anns = {
        a.asset_id: a
        for a in db.scalars(
            select(Annotation).where(Annotation.dataset_id == dataset_id)
        ).all()
    }
    entries: list[dict[str, Any]] = []
    for m in members:
        asset = db.get(Asset, m.asset_id)
        if asset is None:
            continue
        ann = anns.get(m.asset_id)
        entry: dict[str, Any] = {
            "assetId": str(asset.id),
            "contentHash": asset.content_hash,
            "split": m.split,
            "mediaKind": asset.media_kind,
            "filename": asset.filename,
            "shapes": (ann.shapes if ann else {"format": "xyxy_abs", "items": []}),
            "annotationStatus": ann.status if ann else "draft",
        }
        if asset.media_kind == "frame":
            entry["parentVideoId"] = (
                str(asset.parent_video_id) if asset.parent_video_id else None
            )
            entry["frameIndex"] = asset.frame_index
            entry["extractJobId"] = (
                str(asset.extract_job_id) if asset.extract_job_id else None
            )
        entries.append(entry)
    return {"entries": entries}


def _diff_manifests(
    parent: dict[str, Any] | None, current: dict[str, Any]
) -> dict[str, Any]:
    if not parent:
        return {
            "added": len(current.get("entries") or []),
            "removed": 0,
            "changedAnnotations": 0,
        }
    p_map = {
        e["assetId"]: e for e in (parent.get("entries") or []) if "assetId" in e
    }
    c_map = {
        e["assetId"]: e for e in (current.get("entries") or []) if "assetId" in e
    }
    added = len(set(c_map) - set(p_map))
    removed = len(set(p_map) - set(c_map))
    changed = 0
    for aid in set(p_map) & set(c_map):
        if json.dumps(p_map[aid].get("shapes"), sort_keys=True) != json.dumps(
            c_map[aid].get("shapes"), sort_keys=True
        ):
            changed += 1
    return {
        "added": added,
        "removed": removed,
        "changedAnnotations": changed,
    }


def publish_version(
    db: Session,
    *,
    dataset_id: UUID,
    name: str,
    user_id: str,
    note: str | None = None,
    parent_id: UUID | None = None,
) -> DatasetVersion:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    from app.auth.deps import get_membership

    m = get_membership(db, ds.project_id, user_id)
    if m is None or m.role != "admin":
        raise ForbiddenError("仅管理员可发版")

    parent: DatasetVersion | None = None
    if parent_id:
        parent = db.get(DatasetVersion, parent_id)
        if parent is None or parent.dataset_id != dataset_id:
            raise ValidationAppError("父版本无效")
    else:
        # 默认挂到最新版本
        parent = db.scalar(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.created_at.desc())
            .limit(1)
        )

    manifest = _build_manifest(db, dataset_id)
    member_sources = build_member_sources(db, dataset_id)
    summary = _diff_manifests(parent.manifest if parent else None, manifest)

    ver = DatasetVersion(
        dataset_id=dataset_id,
        name=name.strip(),
        parent_id=parent.id if parent else None,
        classes=_classes(db, dataset_id),
        enabled_annotation_types=list(ds.enabled_annotation_types or ["rect"]),
        manifest=manifest,
        member_sources=member_sources,
        change_summary=summary,
        created_by=user_id,
        note=note,
    )
    db.add(ver)
    db.commit()
    db.refresh(ver)
    logger.info(
        "version_published version_id=%s dataset_id=%s entries=%s",
        ver.id,
        dataset_id,
        len(manifest.get("entries") or []),
    )
    return ver
