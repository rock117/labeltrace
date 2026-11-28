"""数据集工作区类别：稳定 id + 有序维护。"""

from __future__ import annotations

import re
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.annotation import Annotation
from app.models.dataset import Dataset, DatasetClass

logger = get_logger("labeltrace.dataset_classes")

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def list_classes(db: Session, dataset_id: UUID) -> list[DatasetClass]:
    return list(
        db.scalars(
            select(DatasetClass)
            .where(DatasetClass.dataset_id == dataset_id)
            .order_by(DatasetClass.idx)
        ).all()
    )


def classes_as_dicts(db: Session, dataset_id: UUID) -> list[dict[str, Any]]:
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "idx": c.idx,
            "color": c.color,
        }
        for c in list_classes(db, dataset_id)
    ]


def classes_for_version_snapshot(db: Session, dataset_id: UUID) -> list[dict[str, str]]:
    """发版冻结：有序 [{id, name}]。"""
    return [{"id": str(c.id), "name": c.name} for c in list_classes(db, dataset_id)]


def class_id_set(db: Session, dataset_id: UUID) -> set[str]:
    return {str(c.id) for c in list_classes(db, dataset_id)}


def referenced_class_ids(db: Session, dataset_id: UUID) -> set[str]:
    """工作区标注中出现的 classId。"""
    found: set[str] = set()
    anns = db.scalars(
        select(Annotation).where(Annotation.dataset_id == dataset_id)
    ).all()
    for ann in anns:
        items = (ann.shapes or {}).get("items") or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("classId"):
                found.add(str(item["classId"]))
    return found


def _normalize_color(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if not _COLOR_RE.match(s):
        raise ValidationAppError("类别颜色须为 #RRGGBB")
    return s.upper()


def create_classes_from_names(
    db: Session,
    dataset_id: UUID,
    names: list[str],
) -> list[DatasetClass]:
    """创建数据集时批量写入；调用方负责 commit。"""
    rows: list[DatasetClass] = []
    for i, name in enumerate(names):
        n = str(name).strip()
        if not n:
            continue
        row = DatasetClass(dataset_id=dataset_id, idx=i, name=n, color=None)
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def replace_classes(
    db: Session,
    *,
    dataset_id: UUID,
    items: list[dict[str, Any]],
    user_id: str,
) -> list[DatasetClass]:
    """
    整表替换有序列表。
    - 带 id：改名/改色/调序
    - 无 id：新建
    - 原有但不在列表中：删除（若仍被标注引用则 409）
    """
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role
    from app.core.errors import ForbiddenError

    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user_id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")

    if not isinstance(items, list):
        raise ValidationAppError("classes 须为数组")

    existing = {str(c.id): c for c in list_classes(db, dataset_id)}
    keep_ids: set[str] = set()
    normalized: list[tuple[UUID | None, str, str | None]] = []

    for i, raw in enumerate(items):
        if isinstance(raw, str):
            name = raw.strip()
            cid = None
            color = None
        elif isinstance(raw, dict):
            name = str(raw.get("name") or "").strip()
            raw_id = raw.get("id")
            cid = UUID(str(raw_id)) if raw_id else None
            color = _normalize_color(raw.get("color"))
        else:
            raise ValidationAppError(f"classes[{i}] 格式无效")
        if not name:
            raise ValidationAppError(f"classes[{i}] 名称不能为空")
        if len(name) > 128:
            raise ValidationAppError(f"classes[{i}] 名称过长")
        if cid is not None:
            if str(cid) not in existing:
                raise ValidationAppError(f"未知类别 id: {cid}")
            keep_ids.add(str(cid))
        normalized.append((cid, name, color))

    # 重名检查（同表内）
    names_seen: set[str] = set()
    for _, name, _ in normalized:
        key = name.casefold()
        if key in names_seen:
            raise ValidationAppError(f"类别重名：{name}")
        names_seen.add(key)

    to_remove = [c for cid, c in existing.items() if cid not in keep_ids]
    if to_remove:
        used = referenced_class_ids(db, dataset_id)
        blocked = [c for c in to_remove if str(c.id) in used]
        if blocked:
            names = "、".join(c.name for c in blocked[:5])
            raise ConflictError(
                f"类别仍被工作区标注引用，无法删除：{names}"
            )
        for c in to_remove:
            db.delete(c)
        db.flush()

    # 先把保留行的 idx 挪到临时区，避免唯一约束冲突
    for c in existing.values():
        if str(c.id) in keep_ids:
            c.idx = c.idx + 100000
    db.flush()

    result: list[DatasetClass] = []
    for idx, (cid, name, color) in enumerate(normalized):
        if cid is None:
            row = DatasetClass(
                id=uuid.uuid4(),
                dataset_id=dataset_id,
                idx=idx,
                name=name,
                color=color,
            )
            db.add(row)
            result.append(row)
        else:
            row = existing[str(cid)]
            row.name = name
            row.color = color
            row.idx = idx
            result.append(row)
    db.commit()
    for row in result:
        db.refresh(row)
    logger.info(
        "dataset_classes_replaced dataset_id=%s count=%s user_id=%s",
        dataset_id,
        len(result),
        user_id,
    )
    return result
