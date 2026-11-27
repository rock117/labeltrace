"""密码哈希。"""

from __future__ import annotations

import bcrypt

# 占位哈希：仅用于测试头自动建号，无法登录
_UNUSABLE = "!"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash or password_hash.startswith(_UNUSABLE):
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def unusable_password_hash() -> str:
    return _UNUSABLE
