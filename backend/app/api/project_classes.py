"""项目类别词表 API。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import (
    ALL_ROLES,
    CurrentUser,
    get_current_user,
    require_project_role,
)
from app.db.session import get_db
from app.models.project import Membership, ProjectClass
from app.services.project_classes import (
    create_project_class,
    delete_project_class,
    list_project_classes,
    update_project_class,
)

router = APIRouter(tags=["project-classes"])


class ProjectClassOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    color: str | None = None

    model_config = {"from_attributes": True}


class ProjectClassCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    color: str | None = None


class ProjectClassPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    color: str | None = None


def _out(row: ProjectClass) -> ProjectClassOut:
    return ProjectClassOut(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        color=row.color,
    )


@router.get(
    "/projects/{project_id}/classes",
    response_model=list[ProjectClassOut],
)
def get_project_classes(
    project_id: UUID,
    _: Annotated[Membership, Depends(require_project_role(*ALL_ROLES))],
    db: Annotated[Session, Depends(get_db)],
) -> list[ProjectClassOut]:
    return [_out(row) for row in list_project_classes(db, project_id)]


@router.post(
    "/projects/{project_id}/classes",
    response_model=ProjectClassOut,
    status_code=201,
)
def post_project_class(
    project_id: UUID,
    body: ProjectClassCreate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProjectClassOut:
    row = create_project_class(
        db,
        project_id=project_id,
        name=body.name,
        color=body.color,
        user_id=user.id,
    )
    return _out(row)


@router.patch(
    "/projects/{project_id}/classes/{class_id}",
    response_model=ProjectClassOut,
)
def patch_project_class(
    project_id: UUID,
    class_id: UUID,
    body: ProjectClassPatch,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProjectClassOut:
    fields = body.model_fields_set
    row = update_project_class(
        db,
        project_id=project_id,
        class_id=class_id,
        name=body.name if "name" in fields else None,
        color=body.color,
        color_set="color" in fields,
        user_id=user.id,
    )
    return _out(row)


@router.delete(
    "/projects/{project_id}/classes/{class_id}",
    status_code=204,
)
def remove_project_class(
    project_id: UUID,
    class_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    delete_project_class(
        db,
        project_id=project_id,
        class_id=class_id,
        user_id=user.id,
    )
    return Response(status_code=204)
