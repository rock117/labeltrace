"""项目类别词表，以及数据集对词表的有序启用。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.annotation import Annotation
from app.models.dataset import Dataset, DatasetClassRef
from app.models.project import ProjectClass
from app.models.version import DatasetVersion

logger = get_logger("labeltrace.project_classes")

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass
class EnabledClass:
    id: UUID
    name: str
    idx: int
    color: str | None


def _normalize_color(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    s = str(raw).strip()
    if not _COLOR_RE.match(s):
        raise ValidationAppError("类别颜色须为 #RRGGBB")
    return s.upper()


def _normalize_name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise ValidationAppError("类别名称不能为空")
    if len(name) > 128:
        raise ValidationAppError("类别名称过长")
    return name


def list_project_classes(db: Session, project_id: UUID) -> list[ProjectClass]:
    return list(
        db.scalars(
            select(ProjectClass)
            .where(ProjectClass.project_id == project_id)
            .order_by(ProjectClass.created_at, ProjectClass.name)
        ).all()
    )


def list_classes(db: Session, dataset_id: UUID) -> list[EnabledClass]:
    rows = db.execute(
        select(DatasetClassRef, ProjectClass)
        .join(ProjectClass, ProjectClass.id == DatasetClassRef.class_id)
        .where(DatasetClassRef.dataset_id == dataset_id)
        .order_by(DatasetClassRef.idx)
    ).all()
    return [
        EnabledClass(
            id=pc.id,
            name=pc.name,
            idx=ref.idx,
            color=pc.color,
        )
        for ref, pc in rows
    ]


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
    """发版冻结当时的有序 [{id, name}]。之后改项目词表名称不影响该快照。"""
    return [{"id": str(c.id), "name": c.name} for c in list_classes(db, dataset_id)]


def class_id_set(db: Session, dataset_id: UUID) -> set[str]:
    return {str(c.id) for c in list_classes(db, dataset_id)}


def referenced_class_ids(db: Session, dataset_id: UUID) -> set[str]:
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


def _replace_refs(db: Session, dataset_id: UUID, class_ids: list[UUID]) -> None:
    existing = list(
        db.scalars(
            select(DatasetClassRef).where(DatasetClassRef.dataset_id == dataset_id)
        ).all()
    )
    for row in existing:
        db.delete(row)
    db.flush()
    for idx, cid in enumerate(class_ids):
        db.add(
            DatasetClassRef(dataset_id=dataset_id, class_id=cid, idx=idx)
        )
    db.flush()


def set_dataset_class_ids(
    db: Session,
    *,
    dataset_id: UUID,
    class_ids: list[UUID],
    user_id: str,
) -> list[EnabledClass]:
    """替换数据集启用顺序。id 必须属于该项目词表。停用仍被本集标注引用的类别 → 409。"""
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role
    from app.core.errors import ForbiddenError

    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    m = get_membership(db, ds.project_id, user_id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")

    seen: set[UUID] = set()
    for cid in class_ids:
        if cid in seen:
            raise ValidationAppError("类别重复启用")
        seen.add(cid)
    if class_ids:
        found = {
            row.id
            for row in db.scalars(
                select(ProjectClass).where(
                    ProjectClass.project_id == ds.project_id,
                    ProjectClass.id.in_(class_ids),
                )
            ).all()
        }
        missing = [cid for cid in class_ids if cid not in found]
        if missing:
            raise ValidationAppError("类别不属于当前项目")

    current = {c.id for c in list_classes(db, dataset_id)}
    removed = current - set(class_ids)
    if removed:
        used = referenced_class_ids(db, dataset_id)
        blocked = [cid for cid in removed if str(cid) in used]
        if blocked:
            raise ConflictError("类别仍被本数据集标注引用，无法停用")

    _replace_refs(db, dataset_id, class_ids)
    db.commit()
    logger.info(
        "dataset_classes_set dataset_id=%s count=%s user_id=%s",
        dataset_id,
        len(class_ids),
        user_id,
    )
    return list_classes(db, dataset_id)


def ensure_classes_from_names(
    db: Session,
    dataset_id: UUID,
    names: list[str],
) -> list[str]:
    """按名字复用或新建项目类别，并按该顺序启用到数据集。不删除词表里的其它类别。"""
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError("数据集不存在")
    ordered: list[UUID] = []
    seen: set[str] = set()
    for raw in names:
        name = _normalize_name(raw)
        if name in seen:
            raise ValidationAppError(f"导入类别重名：{name}")
        seen.add(name)
        row = db.scalar(
            select(ProjectClass).where(
                ProjectClass.project_id == ds.project_id,
                ProjectClass.name == name,
            )
        )
        if row is None:
            row = ProjectClass(project_id=ds.project_id, name=name, color=None)
            db.add(row)
            db.flush()
        ordered.append(row.id)
    _replace_refs(db, dataset_id, ordered)
    return [str(cid) for cid in ordered]


def _version_uses_class(db: Session, project_id: UUID, class_id: UUID) -> bool:
    needle = str(class_id)
    versions = db.scalars(
        select(DatasetVersion)
        .join(Dataset, Dataset.id == DatasetVersion.dataset_id)
        .where(Dataset.project_id == project_id)
    ).all()
    for version in versions:
        for item in version.classes or []:
            if isinstance(item, dict) and str(item.get("id")) == needle:
                return True
    return False


def _annotation_uses_class(db: Session, project_id: UUID, class_id: UUID) -> bool:
    needle = str(class_id)
    anns = db.scalars(
        select(Annotation)
        .join(Dataset, Dataset.id == Annotation.dataset_id)
        .where(Dataset.project_id == project_id)
    ).all()
    for ann in anns:
        items = (ann.shapes or {}).get("items") or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and str(item.get("classId") or "") == needle:
                return True
    return False


def create_project_class(
    db: Session,
    *,
    project_id: UUID,
    name: str,
    color: str | None,
    user_id: str,
) -> ProjectClass:
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role
    from app.core.errors import ForbiddenError

    m = get_membership(db, project_id, user_id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    row = ProjectClass(
        project_id=project_id,
        name=_normalize_name(name),
        color=_normalize_color(color),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("项目中已有同名类别") from None
    db.refresh(row)
    logger.info(
        "project_class_created project_id=%s class_id=%s user_id=%s",
        project_id,
        row.id,
        user_id,
    )
    return row


def update_project_class(
    db: Session,
    *,
    project_id: UUID,
    class_id: UUID,
    name: str | None,
    color: Any,
    color_set: bool,
    user_id: str,
) -> ProjectClass:
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role
    from app.core.errors import ForbiddenError

    m = get_membership(db, project_id, user_id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    row = db.get(ProjectClass, class_id)
    if row is None or row.project_id != project_id:
        raise NotFoundError("类别不存在")
    if name is not None:
        row.name = _normalize_name(name)
    if color_set:
        row.color = _normalize_color(color)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("项目中已有同名类别") from None
    db.refresh(row)
    logger.info(
        "project_class_updated project_id=%s class_id=%s user_id=%s",
        project_id,
        class_id,
        user_id,
    )
    return row


def delete_project_class(
    db: Session,
    *,
    project_id: UUID,
    class_id: UUID,
    user_id: str,
) -> None:
    from app.auth.deps import WRITE_ROLES, get_membership, has_any_role
    from app.core.errors import ForbiddenError

    m = get_membership(db, project_id, user_id)
    if m is None or not has_any_role(m, WRITE_ROLES):
        raise ForbiddenError("权限不足")
    row = db.get(ProjectClass, class_id)
    if row is None or row.project_id != project_id:
        raise NotFoundError("类别不存在")
    linked = db.scalar(
        select(DatasetClassRef.class_id).where(DatasetClassRef.class_id == class_id)
    )
    if linked is not None:
        raise ConflictError("类别仍被数据集选用，无法删除")
    if _annotation_uses_class(db, project_id, class_id):
        raise ConflictError("类别仍被标注引用，无法删除")
    if _version_uses_class(db, project_id, class_id):
        raise ConflictError("类别已写入已发版本，无法删除")
    db.delete(row)
    db.commit()
    logger.info(
        "project_class_deleted project_id=%s class_id=%s user_id=%s",
        project_id,
        class_id,
        user_id,
    )
