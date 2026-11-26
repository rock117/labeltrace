"""鉴权依赖：X-User-Id + 项目角色校验。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.project import Membership

# 可写素材库 / 上传：admin、annotator
WRITE_ROLES = frozenset({"admin", "annotator"})
ADMIN_ROLES = frozenset({"admin"})
ALL_ROLES = frozenset({"admin", "annotator", "viewer"})


@dataclass(frozen=True)
class CurrentUser:
    id: str


def get_current_user(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> CurrentUser:
    if not x_user_id or not x_user_id.strip():
        raise HTTPException(status_code=401, detail="缺少 X-User-Id")
    return CurrentUser(id=x_user_id.strip())


def get_membership(
    db: Session, project_id: UUID, user_id: str
) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.project_id == project_id,
            Membership.user_id == user_id,
        )
    )


def require_project_role(*allowed: str) -> Callable[..., Membership]:
    """工厂：校验当前用户在项目中具备给定角色之一。"""

    allowed_set = frozenset(allowed) or ALL_ROLES

    def _dep(
        project_id: Annotated[UUID, Path(alias="project_id")],
        user: Annotated[CurrentUser, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> Membership:
        m = get_membership(db, project_id, user.id)
        if m is None:
            raise HTTPException(status_code=403, detail="不是项目成员")
        if m.role not in allowed_set:
            raise HTTPException(status_code=403, detail="权限不足")
        return m

    return _dep
