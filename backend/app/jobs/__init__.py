"""任务抽象与 PG 队列后端。"""

from app.jobs.base import JobBackend
from app.jobs.service import JobService, get_job_service

__all__ = ["JobBackend", "JobService", "get_job_service"]
