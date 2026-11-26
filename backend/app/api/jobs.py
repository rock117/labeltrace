"""任务查询 API。"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.jobs.service import JobService, get_job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


class EnqueueRequest(BaseModel):
    job_type: str = Field(..., examples=["echo"])
    payload: dict = Field(default_factory=dict)


class JobOut(BaseModel):
    id: UUID
    job_type: str
    status: str
    progress: float | None
    result: dict | None
    error_message: str | None

    model_config = {"from_attributes": True}


@router.post("", response_model=JobOut, status_code=201)
def create_job(
    body: EnqueueRequest,
    db: Session = Depends(get_db),
    jobs: JobService = Depends(get_job_service),
) -> JobOut:
    job = jobs.enqueue(db, body.job_type, body.payload)
    return JobOut.model_validate(job)


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: UUID,
    db: Session = Depends(get_db),
    jobs: JobService = Depends(get_job_service),
) -> JobOut:
    job = jobs.get(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return JobOut.model_validate(job)
