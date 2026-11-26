"""数据集工作区 memberSources 摘要。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.dataset import DatasetAsset
from app.models.frame_extract_job import FrameExtractJob


def build_member_sources(db: Session, dataset_id: UUID) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(
            select(DatasetAsset).where(DatasetAsset.dataset_id == dataset_id)
        ).all()
    )
    if not rows:
        return []

    assets = {
        a.id: a
        for a in db.scalars(
            select(Asset).where(Asset.id.in_([r.asset_id for r in rows]))
        ).all()
    }

    extract_groups: dict[UUID, list[Asset]] = defaultdict(list)
    upload_images: list[Asset] = []
    import_groups: dict[UUID | None, list[Asset]] = defaultdict(list)

    for r in rows:
        a = assets.get(r.asset_id)
        if a is None:
            continue
        if a.media_kind == "frame" and a.extract_job_id:
            extract_groups[a.extract_job_id].append(a)
        elif a.origin == "import":
            import_groups[a.import_id].append(a)
        elif a.media_kind == "image" and a.origin == "upload":
            upload_images.append(a)
        elif a.media_kind == "image":
            upload_images.append(a)

    sources: list[dict[str, Any]] = []
    for ej_id, frames in extract_groups.items():
        job = db.get(FrameExtractJob, ej_id)
        video = db.get(Asset, job.video_asset_id) if job else None
        sources.append(
            {
                "kind": "extract",
                "extractJobId": str(ej_id),
                "videoId": str(job.video_asset_id) if job else None,
                "videoName": video.filename if video else None,
                "mode": job.mode if job else None,
                "stride": job.stride if job else None,
                "intervalMs": job.interval_ms if job else None,
                "frameCount": len(frames),
            }
        )
    if upload_images:
        sources.append(
            {"kind": "upload", "imageCount": len(upload_images)}
        )
    for iid, imgs in import_groups.items():
        sources.append(
            {
                "kind": "import",
                "importId": str(iid) if iid else None,
                "imageCount": len(imgs),
            }
        )
    return sources
