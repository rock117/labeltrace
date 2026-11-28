"""数据集成员任务分配：可见性与标注写权限。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import OWNER_ROLES, WRITE_ROLES, has_any_role, membership_roles
from app.core.errors import ForbiddenError, ValidationAppError
from app.models.dataset import DatasetAsset
from app.models.project import Membership
from app.models.user import User


def is_project_owner(m: Membership) -> bool:
    return has_any_role(m, OWNER_ROLES)


def must_list_mine_only(m: Membership) -> bool:
    """仅有 annotator、无 owner 时列表强制只看自己的。viewer 可见全部。"""
    roles = membership_roles(m)
    return "annotator" in roles and "owner" not in roles


def can_annotate_member(m: Membership, row: DatasetAsset, user_id: str) -> bool:
    if is_project_owner(m):
        return True
    if not has_any_role(m, WRITE_ROLES):
        return False
    return row.assignee_user_id is not None and row.assignee_user_id == user_id


def require_can_annotate(
    m: Membership, row: DatasetAsset, user_id: str
) -> None:
    if can_annotate_member(m, row, user_id):
        return
    if row.assignee_user_id is None:
        raise ForbiddenError("该成员尚未分配，仅负责人可标注")
    raise ForbiddenError("该成员已分配给其他用户")


def default_owner_assignee_id(
    db: Session,
    project_id: UUID,
    preferred_user_id: str | None = None,
) -> str | None:
    """入集默认执行人：优先当前操作者（若为 owner），否则取项目最早的一名 owner。"""
    if preferred_user_id:
        m = db.scalar(
            select(Membership).where(
                Membership.project_id == project_id,
                Membership.user_id == preferred_user_id,
            )
        )
        if m is not None and is_project_owner(m):
            return preferred_user_id
    owners = list(
        db.scalars(
            select(Membership)
            .where(Membership.project_id == project_id)
            .order_by(Membership.created_at.asc())
        ).all()
    )
    for m in owners:
        if is_project_owner(m):
            return m.user_id
    return preferred_user_id


def resolve_assignee_user_id(
    db: Session, project_id: UUID, assignee_user_id: str | None
) -> str | None:
    """校验可写项目成员；None 表示清空。接受 user UUID 或 username。"""
    if assignee_user_id is None:
        return None
    raw = assignee_user_id.strip()
    if not raw:
        return None
    target_uid: str | None = None
    try:
        u = db.get(User, UUID(raw))
        if u is not None:
            target_uid = str(u.id)
    except ValueError:
        pass
    if target_uid is None:
        u = db.scalar(select(User).where(User.username == raw))
        if u is not None:
            target_uid = str(u.id)
    if target_uid is None:
        raise ValidationAppError("分配对象用户不存在")
    mem = db.scalar(
        select(Membership).where(
            Membership.project_id == project_id,
            Membership.user_id == target_uid,
        )
    )
    if mem is None or not has_any_role(mem, WRITE_ROLES):
        raise ValidationAppError("只能分配给项目内的负责人或标注员")
    return target_uid


def usernames_for_ids(db: Session, user_ids: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    uuids: list[UUID] = []
    for uid in user_ids:
        if not uid:
            continue
        try:
            uuids.append(UUID(uid))
        except ValueError:
            out[uid] = uid
    if not uuids:
        return out
    for u in db.scalars(select(User).where(User.id.in_(uuids))).all():
        out[str(u.id)] = u.username
    return out
