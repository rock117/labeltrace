"""素材引用检查：存在数据集成员或版本快照引用时禁止硬删。"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger("labeltrace.asset_refs")


def asset_has_references(db: Session, asset_id: UUID) -> bool:
    """查询是否仍被数据集或版本引用。表尚未创建时视为无引用。"""
    checks = (
        (
            "dataset_assets",
            "SELECT 1 FROM dataset_assets WHERE asset_id = :id LIMIT 1",
        ),
        (
            "dataset_versions",
            """
            SELECT 1 FROM dataset_versions
            WHERE manifest::text LIKE :needle
            LIMIT 1
            """,
        ),
    )
    for table, sql in checks:
        exists = db.execute(
            text("SELECT to_regclass(:name)"),
            {"name": f"public.{table}"},
        ).scalar()
        if not exists:
            continue
        params: dict = {"id": str(asset_id)}
        if table == "dataset_versions":
            params["needle"] = f"%{asset_id}%"
        hit = db.execute(text(sql), params).first()
        if hit:
            logger.info(
                "asset_referenced asset_id=%s via=%s", asset_id, table
            )
            return True
    return False
