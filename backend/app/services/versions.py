"""发版与变更摘要。"""

from __future__ import annotations

import json
import random
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


def _normalize_ratios(train: float, val: float, test: float) -> tuple[float, float, float]:
    total = train + val + test
    if total <= 0:
        raise ValidationAppError("划分比例之和须大于 0")
    if abs(total - 1.0) > 0.02:
        raise ValidationAppError("train/val/test 比例之和须为 1")
    return train / total, val / total, test / total


def _allocate_counts(n: int, train: float, val: float, test: float) -> dict[str, int]:
    """按比例分配整数人数，保证合计为 n。"""
    if n <= 0:
        return {"train": 0, "val": 0, "test": 0}
    raw = {
        "train": train * n,
        "val": val * n,
        "test": test * n,
    }
    counts = {k: int(v) for k, v in raw.items()}
    rem = n - sum(counts.values())
    # 按小数部分从大到小补余数
    order = sorted(raw.keys(), key=lambda k: (raw[k] - counts[k]), reverse=True)
    i = 0
    while rem > 0:
        counts[order[i % 3]] += 1
        rem -= 1
        i += 1
    return counts


def assign_random_splits(
    db: Session,
    dataset_id: UUID,
    *,
    train: float,
    val: float,
    test: float,
    seed: int | None,
) -> dict[str, Any]:
    train, val, test = _normalize_ratios(train, val, test)
    members = list(
        db.scalars(
            select(DatasetAsset).where(DatasetAsset.dataset_id == dataset_id)
        ).all()
    )
    n = len(members)
    counts = _allocate_counts(n, train, val, test)
    rng = random.Random(seed)
    shuffled = list(members)
    rng.shuffle(shuffled)

    labels: list[str] = (
        ["train"] * counts["train"]
        + ["val"] * counts["val"]
        + ["test"] * counts["test"]
    )
    for member, split in zip(shuffled, labels, strict=True):
        member.split = split
    db.flush()
    return {
        "seed": seed,
        "ratios": {"train": train, "val": val, "test": test},
        "counts": counts,
    }


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


def _assert_ready_to_publish(db: Session, dataset_id: UUID) -> None:
    """全部成员须有 status=submitted 的工作标注；空集不可发版。"""
    members = list(
        db.scalars(
            select(DatasetAsset).where(DatasetAsset.dataset_id == dataset_id)
        ).all()
    )
    if not members:
        raise ValidationAppError("数据集无成员，无法发版")

    anns = {
        a.asset_id: a
        for a in db.scalars(
            select(Annotation).where(Annotation.dataset_id == dataset_id)
        ).all()
    }
    incomplete = 0
    for m in members:
        ann = anns.get(m.asset_id)
        if ann is None or ann.status != "submitted":
            incomplete += 1
    if incomplete:
        raise ValidationAppError(
            f"尚有 {incomplete} 个成员未提交标注，无法发版"
        )


def publish_version(
    db: Session,
    *,
    dataset_id: UUID,
    name: str,
    user_id: str,
    note: str | None = None,
    parent_id: UUID | None = None,
    split_train: float = 0.7,
    split_val: float = 0.2,
    split_test: float = 0.1,
    split_seed: int | None = None,
) -> DatasetVersion:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    from app.auth.deps import OWNER_ROLES, get_membership, has_any_role

    m = get_membership(db, ds.project_id, user_id)
    if m is None or not has_any_role(m, OWNER_ROLES):
        raise ForbiddenError("仅负责人可发版")

    _assert_ready_to_publish(db, dataset_id)

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

    split_meta = assign_random_splits(
        db,
        dataset_id,
        train=split_train,
        val=split_val,
        test=split_test,
        seed=split_seed,
    )

    manifest = _build_manifest(db, dataset_id)
    member_sources = build_member_sources(db, dataset_id)
    summary = _diff_manifests(parent.manifest if parent else None, manifest)
    summary["split"] = split_meta

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
        "version_published version_id=%s dataset_id=%s entries=%s split=%s",
        ver.id,
        dataset_id,
        len(manifest.get("entries") or []),
        split_meta,
    )
    return ver


def apply_version_to_workspace(
    db: Session,
    *,
    version_id: UUID,
    user_id: str,
) -> dict[str, int]:
    """将版本快照合并进所属数据集工作区；不修改版本本身。"""
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role
    from app.models.asset import Asset

    ver = db.get(DatasetVersion, version_id)
    if ver is None:
        raise NotFoundError("版本不存在")
    ds = db.get(Dataset, ver.dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user_id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")

    entries = list((ver.manifest or {}).get("entries") or [])
    added = 0
    overwritten = 0
    skipped = 0

    for entry in entries:
        raw_id = entry.get("assetId")
        if not raw_id:
            skipped += 1
            continue
        try:
            asset_id = UUID(str(raw_id))
        except ValueError:
            skipped += 1
            continue
        asset = db.get(Asset, asset_id)
        if asset is None or asset.project_id != ds.project_id:
            skipped += 1
            continue
        if asset.media_kind == "video":
            skipped += 1
            continue

        split = str(entry.get("split") or "unassigned")
        if split not in {"train", "val", "test", "unassigned"}:
            split = "unassigned"
        shapes = entry.get("shapes") or {"format": "xyxy_abs", "items": []}
        if not isinstance(shapes, dict):
            shapes = {"format": "xyxy_abs", "items": []}

        member = db.get(DatasetAsset, (ver.dataset_id, asset_id))
        if member is None:
            db.add(
                DatasetAsset(
                    dataset_id=ver.dataset_id,
                    asset_id=asset_id,
                    split=split,
                )
            )
            added += 1
        else:
            overwritten += 1

        ann = db.scalar(
            select(Annotation).where(
                Annotation.dataset_id == ver.dataset_id,
                Annotation.asset_id == asset_id,
            )
        )
        if ann is None:
            db.add(
                Annotation(
                    dataset_id=ver.dataset_id,
                    asset_id=asset_id,
                    shapes=shapes,
                    status="draft",
                    updated_by=user_id,
                )
            )
        else:
            ann.shapes = shapes
            ann.status = "draft"
            ann.updated_by = user_id

    db.commit()
    logger.info(
        "version_applied_to_workspace version_id=%s dataset_id=%s "
        "added=%s overwritten=%s skipped=%s",
        version_id,
        ver.dataset_id,
        added,
        overwritten,
        skipped,
    )
    return {
        "added": added,
        "overwritten": overwritten,
        "skipped": skipped,
        "entryCount": len(entries),
    }
