"""JobService：业务只经此入口入队。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import bind_context, get_logger, reset_context
from app.jobs.base import JobBackend
from app.jobs.pg import PgJobBackend
from app.models.job import Job

logger = get_logger("labeltrace.jobs")

_backend_singleton: JobBackend | None = None


def build_job_backend(backend_id: str | None = None) -> JobBackend:
    bid = (backend_id or get_settings().job_backend).lower()
    if bid == "pg":
        return PgJobBackend()
    raise ValueError(
        f"不支持的 JOB_BACKEND={bid!r}；P0 仅支持 pg。"
        "独立 worker / 可选 redis 见 docs/jobs.md。"
    )


def get_job_backend() -> JobBackend:
    global _backend_singleton
    if _backend_singleton is None:
        _backend_singleton = build_job_backend()
    return _backend_singleton


def reset_job_backend() -> None:
    global _backend_singleton
    if isinstance(_backend_singleton, PgJobBackend):
        _backend_singleton.shutdown(wait=False)
    _backend_singleton = None
    get_job_service.cache_clear()


class JobService:
    def __init__(self, backend: JobBackend | None = None) -> None:
        self._backend = backend or get_job_backend()

    def enqueue(
        self,
        db: Session,
        job_type: str,
        payload: dict[str, Any] | None = None,
    ) -> Job:
        """创建 pending 行并通知后端；立即返回 job_id。"""
        job = Job(
            job_type=job_type,
            status="pending",
            payload=payload or {},
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        tokens = bind_context(job_id=job.id)
        try:
            logger.info("job_created job_type=%s", job_type)
            self._backend.enqueue(job.id, job.job_type, dict(job.payload))
        finally:
            reset_context(tokens)
        return job

    def get(self, db: Session, job_id: UUID) -> Job | None:
        return db.get(Job, job_id)


@lru_cache
def get_job_service() -> JobService:
    return JobService()
