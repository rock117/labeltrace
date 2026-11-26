"""PgJobBackend：jobs 表作队列（SKIP LOCKED + 租约）。"""

from __future__ import annotations

import socket
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import bind_context, get_logger, reset_context
from app.db.session import SessionLocal
from app.jobs.base import JobBackend
from app.jobs.handlers import get_handler
from app.models.job import Job

logger = get_logger("labeltrace.jobs.pg")


def _worker_id() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


class PgJobBackend(JobBackend):
    """enqueue 仅依赖 INSERT；本类负责消费循环。"""

    backend_id = "pg"

    def __init__(
        self,
        *,
        poll_interval_sec: float | None = None,
        lease_sec: int | None = None,
        worker_id: str | None = None,
        auto_start: bool = True,
    ) -> None:
        settings = get_settings()
        self._poll_interval = (
            poll_interval_sec
            if poll_interval_sec is not None
            else settings.job_poll_interval_sec
        )
        self._lease_sec = (
            lease_sec if lease_sec is not None else settings.job_lease_sec
        )
        self._worker_id = worker_id or _worker_id()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if auto_start:
            self.start()

    def enqueue(self, job_id: UUID, job_type: str, payload: dict[str, Any]) -> None:
        # 行已由 JobService 写入 pending；此处只记日志，由 poller claim
        logger.info(
            "job_enqueued job_type=%s payload_keys=%s",
            job_type,
            sorted(payload.keys()),
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"lt-pg-worker-{self._worker_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "pg_worker_started worker_id=%s poll=%.2fs lease=%ss",
            self._worker_id,
            self._poll_interval,
            self._lease_sec,
        )

    def shutdown(self, wait: bool = False) -> None:
        self._stop.set()
        if wait and self._thread is not None:
            self._thread.join(timeout=10)
        logger.info("pg_worker_stopped worker_id=%s", self._worker_id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                claimed = self._claim_and_run_one()
                if not claimed:
                    self._stop.wait(self._poll_interval)
            except Exception:
                logger.exception(
                    "pg_worker_loop_error worker_id=%s", self._worker_id
                )
                self._stop.wait(self._poll_interval)

    def _claim_and_run_one(self) -> bool:
        db = SessionLocal()
        tokens: dict = {}
        try:
            now = datetime.now(timezone.utc)
            lease_until = now + timedelta(seconds=self._lease_sec)
            # 回收过期租约 + 抢一条 pending/过期 running
            row = db.execute(
                text(
                    """
                    WITH candidate AS (
                      SELECT id FROM jobs
                      WHERE status = 'pending'
                         OR (status = 'running' AND lease_until IS NOT NULL
                             AND lease_until < :now)
                      ORDER BY created_at
                      FOR UPDATE SKIP LOCKED
                      LIMIT 1
                    )
                    UPDATE jobs j
                    SET status = 'running',
                        locked_by = :worker_id,
                        lease_until = :lease_until,
                        started_at = COALESCE(j.started_at, :now),
                        attempt = j.attempt + 1,
                        updated_at = :now,
                        error_message = NULL
                    FROM candidate
                    WHERE j.id = candidate.id
                    RETURNING j.id, j.job_type, j.payload, j.attempt
                    """
                ),
                {
                    "now": now,
                    "worker_id": self._worker_id,
                    "lease_until": lease_until,
                },
            ).mappings().first()
            db.commit()
            if row is None:
                return False

            job_id = row["id"]
            job_type = row["job_type"]
            payload = dict(row["payload"] or {})
            attempt = row["attempt"]
            tokens = bind_context(job_id=job_id)
            logger.info(
                "job_claimed job_type=%s attempt=%s worker_id=%s",
                job_type,
                attempt,
                self._worker_id,
            )
            self._execute(job_id, job_type, payload)
            return True
        except Exception:
            db.rollback()
            logger.exception("job_claim_failed worker_id=%s", self._worker_id)
            raise
        finally:
            reset_context(tokens)
            db.close()

    def _execute(
        self, job_id: UUID, job_type: str, payload: dict[str, Any]
    ) -> None:
        handler = get_handler(job_type)
        db = SessionLocal()
        try:
            if handler is None:
                msg = f"未注册的任务类型: {job_type}"
                logger.error("job_failed reason=unknown_type job_type=%s", job_type)
                self._mark_failed(db, job_id, msg)
                return
            result = handler(job_id, payload)
            job = db.get(Job, job_id)
            if job is None:
                logger.error("job_missing_after_run")
                return
            job.status = "succeeded"
            job.progress = 1.0
            job.result = result or {}
            job.finished_at = datetime.now(timezone.utc)
            job.locked_by = None
            job.lease_until = None
            db.commit()
            logger.info("job_succeeded job_type=%s", job_type)
        except Exception as exc:
            logger.exception("job_failed job_type=%s", job_type)
            db.rollback()
            self._mark_failed(db, job_id, str(exc))
        finally:
            db.close()

    def _mark_failed(self, db: Any, job_id: UUID, message: str) -> None:
        job = db.get(Job, job_id)
        if job is None:
            logger.error("job_mark_failed_missing job_id=%s", job_id)
            return
        job.status = "failed"
        job.error_message = message[:4000]
        job.finished_at = datetime.now(timezone.utc)
        job.locked_by = None
        job.lease_until = None
        db.commit()
