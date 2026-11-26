"""领域/应用错误：禁止静默；统一映射 HTTP。"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """可预期业务错误基类。"""

    def __init__(
        self,
        message: str,
        *,
        code: str = "app_error",
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "资源不存在", **kwargs: Any) -> None:
        super().__init__(message, code="not_found", status_code=404, **kwargs)


class ForbiddenError(AppError):
    def __init__(self, message: str = "权限不足", **kwargs: Any) -> None:
        super().__init__(message, code="forbidden", status_code=403, **kwargs)


class ConflictError(AppError):
    def __init__(self, message: str = "资源冲突", **kwargs: Any) -> None:
        super().__init__(message, code="conflict", status_code=409, **kwargs)


class ValidationAppError(AppError):
    def __init__(self, message: str = "参数无效", **kwargs: Any) -> None:
        super().__init__(message, code="validation_error", status_code=422, **kwargs)
