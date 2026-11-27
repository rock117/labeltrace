"""项目与成员 API。"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import (
    OWNER_ROLES,
    WRITE_ROLES,
    CurrentUser,
    get_current_user,
    get_membership,
    has_any_role,
    membership_roles,
    normalize_roles,
    require_project_role,
)
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.project import Membership, Project
from app.models.user import User

logger = get_logger("labeltrace.api.projects")

router = APIRouter(tags=["projects"])

Role = Literal["owner", "annotator", "viewer"]
VALID_ROLES = frozenset({"owner", "annotator", "viewer"})


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class ProjectOut(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class MemberAdd(BaseModel):
    """按已注册用户名邀请进项目并赋予角色集合。"""

    username: str | None = Field(None, min_length=1, max_length=64)
    # 兼容旧字段：视为 username
    user_id: str | None = Field(None, min_length=1, max_length=128)
    roles: list[Role] = Field(default_factory=lambda: ["annotator"])
    role: Role | None = None


class MemberRolesPatch(BaseModel):
    roles: list[Role] = Field(..., min_length=1)


class MemberOut(BaseModel):
    user_id: str
    username: str
    roles: list[str]


_ROLE_ORDER = ("owner", "annotator", "viewer")


def _member_out(m: Membership, username: str) -> MemberOut:
    have = membership_roles(m)
    return MemberOut(
        user_id=m.user_id,
        username=username,
        roles=[r for r in _ROLE_ORDER if r in have],
    )


def _parse_roles(roles: list[str] | None, role: str | None) -> list[str]:
    raw: list[str] = list(roles or [])
    if role:
        raw.append(role)
    try:
        return normalize_roles(raw)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def _resolve_username(body: MemberAdd) -> str:
    name = (body.username or body.user_id or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="请提供已注册的用户名")
    return name


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Project:
    project = Project(name=body.name.strip())
    db.add(project)
    db.flush()
    db.add(
        Membership(project_id=project.id, user_id=user.id, roles=["owner"])
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Project]:
    stmt = (
        select(Project)
        .join(Membership, Membership.project_id == Project.id)
        .where(Membership.user_id == user.id)
        .order_by(Project.created_at.desc())
    )
    return list(db.scalars(stmt).all())


class ProjectRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def rename_project(
    project_id: UUID,
    body: ProjectRename,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    m = get_membership(db, project_id, user.id)
    if m is None or not has_any_role(m, OWNER_ROLES):
        raise ForbiddenError("仅负责人可重命名项目")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="项目名称无效")
    project.name = name
    db.commit()
    db.refresh(project)
    logger.info("project_renamed project_id=%s name=%s", project_id, name)
    return project


@router.get(
    "/projects/{project_id}/members",
    response_model=list[MemberOut],
)
def list_members(
    project_id: UUID,
    _: Annotated[Membership, Depends(require_project_role(*VALID_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> list[MemberOut]:
    if db.get(Project, project_id) is None:
        raise NotFoundError("项目不存在")
    members = list(
        db.scalars(
            select(Membership)
            .where(Membership.project_id == project_id)
            .order_by(Membership.user_id)
        ).all()
    )
    out: list[MemberOut] = []
    for m in members:
        uname = m.user_id
        try:
            u = db.get(User, UUID(m.user_id))
            if u is not None:
                uname = u.username
        except ValueError:
            pass
        out.append(_member_out(m, uname))
    return out


@router.post(
    "/projects/{project_id}/members",
    response_model=MemberOut,
    status_code=201,
)
def add_member(
    project_id: UUID,
    body: MemberAdd,
    _: Annotated[Membership, Depends(require_project_role(*OWNER_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    roles = _parse_roles(list(body.roles), body.role)
    username = _resolve_username(body)
    target = db.scalar(select(User).where(User.username == username))
    if target is None:
        from app.core.config import get_settings
        from app.auth.deps import _ensure_dev_user

        if get_settings().auth_allow_dev_header:
            # 仅开发/测试：方便 X-User-Id 流程；生产应关闭并要求对方先注册
            target = _ensure_dev_user(db, username)
        else:
            raise HTTPException(
                status_code=404,
                detail="用户不存在，请对方先注册后再邀请",
            )
    uid = str(target.id)
    existing = get_membership(db, project_id, uid)
    if existing is not None:
        raise HTTPException(status_code=409, detail="成员已存在")
    m = Membership(project_id=project_id, user_id=uid, roles=roles)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _member_out(m, target.username)


@router.patch(
    "/projects/{project_id}/members/{user_id}",
    response_model=MemberOut,
)
def patch_member_roles(
    project_id: UUID,
    user_id: str,
    body: MemberRolesPatch,
    actor: Annotated[Membership, Depends(require_project_role(*OWNER_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> MemberOut:
    roles = _parse_roles(list(body.roles), None)
    m = get_membership(db, project_id, user_id)
    if m is None:
        # 也允许用 username 定位
        u = db.scalar(select(User).where(User.username == user_id))
        if u is not None:
            m = get_membership(db, project_id, str(u.id))
    if m is None:
        raise NotFoundError("成员不存在")
    was_owner = has_any_role(m, OWNER_ROLES)
    will_be_owner = "owner" in roles
    if m.user_id == actor.user_id and was_owner and not will_be_owner:
        owners = [
            row
            for row in db.scalars(
                select(Membership).where(Membership.project_id == project_id)
            ).all()
            if has_any_role(row, OWNER_ROLES)
        ]
        if len(owners) <= 1:
            raise HTTPException(
                status_code=422,
                detail="不能取消项目唯一负责人身份，请先指定其他负责人",
            )
    m.roles = roles
    db.commit()
    db.refresh(m)
    uname = m.user_id
    try:
        u = db.get(User, UUID(m.user_id))
        if u is not None:
            uname = u.username
    except ValueError:
        pass
    return _member_out(m, uname)


@router.post("/projects/{project_id}/assets/upload", status_code=202)
def upload_asset_stub(
    project_id: UUID,
    _: Annotated[Membership, Depends(require_project_role(*WRITE_ROLES))],
) -> dict[str, str]:
    """上传入口角色门禁（P0）；完整上传在素材库任务实现。"""
    return {"status": "accepted", "project_id": str(project_id)}
