"""结构化日志：便于按 request_id / job_id 排错。"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)
job_id_ctx: ContextVar[str | None] = ContextVar("job_id", default=None)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get() or "-"  # type: ignore[attr-defined]
        record.user_id = user_id_ctx.get() or "-"  # type: ignore[attr-defined]
        record.job_id = job_id_ctx.get() or "-"  # type: ignore[attr-defined]
        return True


class KeyValueFormatter(logging.Formatter):
    """单行 key=value，便于 grep / 采集。"""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        base = (
            f"ts={ts} level={record.levelname} logger={record.name} "
            f"request_id={getattr(record, 'request_id', '-')} "
            f"user_id={getattr(record, 'user_id', '-')} "
            f"job_id={getattr(record, 'job_id', '-')} "
            f"msg={record.getMessage()}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_labeltrace_configured", False):
        return
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(KeyValueFormatter())
    handler.addFilter(ContextFilter())
    root.handlers.clear()
    root.addHandler(handler)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    setattr(root, "_labeltrace_configured", True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def bind_context(**kwargs: Any) -> dict[str, Token[str | None]]:
    tokens: dict[str, Token[str | None]] = {}
    if "request_id" in kwargs and kwargs["request_id"] is not None:
        tokens["request_id"] = request_id_ctx.set(str(kwargs["request_id"]))
    if "user_id" in kwargs and kwargs["user_id"] is not None:
        tokens["user_id"] = user_id_ctx.set(str(kwargs["user_id"]))
    if "job_id" in kwargs and kwargs["job_id"] is not None:
        tokens["job_id"] = job_id_ctx.set(str(kwargs["job_id"]))
    return tokens


def reset_context(tokens: dict[str, Token[str | None]]) -> None:
    for key, token in tokens.items():
        if key == "request_id":
            request_id_ctx.reset(token)
        elif key == "user_id":
            user_id_ctx.reset(token)
        elif key == "job_id":
            job_id_ctx.reset(token)
