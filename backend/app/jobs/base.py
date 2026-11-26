"""JobBackend 抽象：enqueue；状态以 DB jobs 表为准。"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class JobBackend(ABC):
    backend_id: str

    @abstractmethod
    def enqueue(self, job_id: UUID, job_type: str, payload: dict[str, Any]) -> None:
        """将已写入 DB 的任务交给执行器（立即返回，不阻塞 HTTP）。"""

    def cancel(self, job_id: UUID) -> bool:
        """可选取消；默认不支持。"""
        return False
