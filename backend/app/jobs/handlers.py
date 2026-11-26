"""任务类型 → 处理函数注册表。抽帧/导出在后续任务注册。"""

from collections.abc import Callable
from typing import Any
from uuid import UUID

JobHandler = Callable[[UUID, dict[str, Any]], dict[str, Any] | None]

_HANDLERS: dict[str, JobHandler] = {}


def register_handler(job_type: str, handler: JobHandler) -> None:
    _HANDLERS[job_type] = handler


def get_handler(job_type: str) -> JobHandler | None:
    return _HANDLERS.get(job_type)


def echo_handler(job_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    """骨架用：立即成功并回显 payload。"""
    return {"echo": payload, "job_id": str(job_id)}


# P0 骨架：注册 echo 便于验收 enqueue + 轮询
register_handler("echo", echo_handler)
