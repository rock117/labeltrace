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


def frame_extract_handler(job_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    from uuid import UUID as _UUID

    from app.services.extract import run_frame_extract

    raw = payload.get("extract_job_id")
    if not raw:
        raise ValueError("frame_extract 缺少 extract_job_id")
    return run_frame_extract(_UUID(str(raw)))


register_handler("echo", echo_handler)
register_handler("frame_extract", frame_extract_handler)
