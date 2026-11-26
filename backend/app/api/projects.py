"""项目与成员 API。"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import (
    ADMIN_ROLES,
    WRITE_ROLES,
    CurrentUser,
    get_current_user,
    get_membership,
    require_project_role,
)
from app.core.errors import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.project import Membership, Project

logger = get_logger("labeltrace.api.projects")

router = APIRouter(tags=["projects"])

Role = Literal["admin", "annotator", "viewer"]


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class ProjectOut(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class MemberAdd(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    role: Role = "annotator"


class MemberOut(BaseModel):
    user_id: str
    role: str

    model_config = {"from_attributes": True}


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
        Membership(project_id=project.id, user_id=user.id, role="admin")
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
    if m is None or m.role not in ADMIN_ROLES:
        raise ForbiddenError("仅管理员可重命名项目")
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="项目名称无效")
    project.name = name
    db.commit()
    db.refresh(project)
    logger.info("project_renamed project_id=%s name=%s", project_id, name)
    return project


@router.post(
    "/projects/{project_id}/members",
    response_model=MemberOut,
    status_code=201,
)
def add_member(
    project_id: UUID,
    body: MemberAdd,
    _: Annotated[Membership, Depends(require_project_role(*ADMIN_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> Membership:
    if body.role not in ("admin", "annotator", "viewer"):
        raise HTTPException(status_code=422, detail="非法角色")
    existing = get_membership(db, project_id, body.user_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="成员已存在")
    m = Membership(project_id=project_id, user_id=body.user_id, role=body.role)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.post("/projects/{project_id}/assets/upload", status_code=202)
def upload_asset_stub(
    project_id: UUID,
    _: Annotated[Membership, Depends(require_project_role(*WRITE_ROLES))],
) -> dict[str, str]:
    """上传入口角色门禁（P0）；完整上传在素材库任务实现。"""
    return {"status": "accepted", "project_id": str(project_id)}
