"""注册 / 登录。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, get_current_user
from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import create_access_token
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.user import User

logger = get_logger("labeltrace.api.auth")

router = APIRouter(tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    id: UUID
    username: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


def _normalize_username(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise HTTPException(status_code=422, detail="用户名无效")
    if any(c.isspace() for c in name):
        raise HTTPException(status_code=422, detail="用户名不能包含空格")
    return name


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(
    body: RegisterIn,
    db: Annotated[Session, Depends(get_db)],
) -> TokenOut:
    username = _normalize_username(body.username)
    user = User(username=username, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    db.refresh(user)
    token = create_access_token(user_id=user.id, username=user.username)
    logger.info("user_registered user_id=%s username=%s", user.id, user.username)
    return TokenOut(
        access_token=token,
        user=UserOut(id=user.id, username=user.username),
    )


@router.post("/auth/login", response_model=TokenOut)
def login(
    body: LoginIn,
    db: Annotated[Session, Depends(get_db)],
) -> TokenOut:
    username = _normalize_username(body.username)
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user_id=user.id, username=user.username)
    return TokenOut(
        access_token=token,
        user=UserOut(id=user.id, username=user.username),
    )


@router.get("/auth/me", response_model=UserOut)
def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> UserOut:
    return UserOut(id=UUID(user.id), username=user.username)
