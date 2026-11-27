"""鉴权依赖：JWT / 可选开发头 + 项目角色校验。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import unusable_password_hash
from app.auth.tokens import decode_access_token
from app.core.config import get_settings
from app.db.session import get_db
from app.models.project import Membership
from app.models.user import User

# 可写素材库 / 上传：owner、annotator
WRITE_ROLES = frozenset({"owner", "annotator"})
OWNER_ROLES = frozenset({"owner"})
ALL_ROLES = frozenset({"owner", "annotator", "viewer"})
ADMIN_ROLES = OWNER_ROLES
VALID_ROLE_SET = ALL_ROLES


@dataclass(frozen=True)
class CurrentUser:
    id: str  # users.id UUID 字符串；memberships.user_id 同此
    username: str


def membership_roles(m: Membership) -> frozenset[str]:
    raw = m.roles if isinstance(m.roles, list) else []
    return frozenset(str(r) for r in raw if r)


def has_any_role(m: Membership, allowed: Iterable[str]) -> bool:
    return bool(membership_roles(m) & frozenset(allowed))


def normalize_roles(roles: Iterable[str]) -> list[str]:
    order = ("owner", "annotator", "viewer")
    got = {str(r).strip() for r in roles if str(r).strip()}
    unknown = got - VALID_ROLE_SET
    if unknown:
        raise ValueError(f"非法角色: {', '.join(sorted(unknown))}")
    if not got:
        raise ValueError("至少指定一个角色")
    return [r for r in order if r in got]


def get_membership(
    db: Session, project_id: UUID, user_id: str
) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.project_id == project_id,
            Membership.user_id == user_id,
        )
    )


def _ensure_dev_user(db: Session, username: str) -> User:
    username = username.strip()
    if not username:
        raise HTTPException(status_code=401, detail="缺少用户标识")
    user = db.scalar(select(User).where(User.username == username))
    if user is not None:
        return user
    user = User(
        username=username,
        password_hash=unusable_password_hash(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> CurrentUser:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=401, detail="登录已失效，请重新登录") from exc
        sub = str(payload.get("sub") or "")
        username = str(payload.get("username") or "")
        try:
            uid = UUID(sub)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="无效令牌") from exc
        user = db.get(User, uid)
        if user is None:
            raise HTTPException(status_code=401, detail="用户不存在")
        return CurrentUser(id=str(user.id), username=user.username or username)

    settings = get_settings()
    if settings.auth_allow_dev_header and x_user_id and x_user_id.strip():
        user = _ensure_dev_user(db, x_user_id.strip())
        return CurrentUser(id=str(user.id), username=user.username)

    raise HTTPException(status_code=401, detail="未登录")


def require_project_role(*allowed: str) -> Callable[..., Membership]:
    """工厂：校验当前用户在项目中具备给定角色之一（多角色取并集）。"""

    allowed_set = frozenset(allowed) or ALL_ROLES

    def _dep(
        project_id: Annotated[UUID, Path(alias="project_id")],
        user: Annotated[CurrentUser, Depends(get_current_user)],
        db: Annotated[Session, Depends(get_db)],
    ) -> Membership:
        m = get_membership(db, project_id, user.id)
        if m is None:
            raise HTTPException(status_code=403, detail="不是项目成员")
        if not has_any_role(m, allowed_set):
            raise HTTPException(status_code=403, detail="权限不足")
        return m

    return _dep
