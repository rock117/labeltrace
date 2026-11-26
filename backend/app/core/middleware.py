"""请求中间件：request_id + 访问日志。"""

from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import bind_context, get_logger, reset_context

logger = get_logger("labeltrace.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        user_id = request.headers.get("X-User-Id")
        tokens = bind_context(request_id=request_id, user_id=user_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-Id"] = request_id
            return response
        except Exception:
            logger.exception(
                "unhandled_error method=%s path=%s",
                request.method,
                request.url.path,
            )
            raise
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            level = logger.warning if status >= 500 else logger.info
            if status >= 400:
                level(
                    "http_done method=%s path=%s status=%s latency_ms=%s",
                    request.method,
                    request.url.path,
                    status,
                    latency_ms,
                )
            else:
                logger.info(
                    "http_done method=%s path=%s status=%s latency_ms=%s",
                    request.method,
                    request.url.path,
                    status,
                    latency_ms,
                )
            reset_context(tokens)
