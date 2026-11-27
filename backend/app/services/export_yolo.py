"""按版本快照导出 YOLO detect zip。"""

from __future__ import annotations

import io
import re
import struct
import zipfile
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.asset import Asset
from app.models.dataset import Dataset
from app.models.version import DatasetVersion
from app.services.assets import read_asset_bytes
from app.storage.factory import get_blob_store, get_default_write_backend

logger = get_logger("labeltrace.export_yolo")

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SPLITS = frozenset({"train", "val", "test"})


def sanitize_stem(name: str, *, max_len: int = 48) -> str:
    """仅保留 [A-Za-z0-9._-]；空则用 img。"""
    base = PurePosixPath(str(name or "").replace("\\", "/")).stem
    cleaned = _SAFE_RE.sub("_", base).strip("._")
    if not cleaned:
        cleaned = "img"
    return cleaned[:max_len]


def export_stem(asset_id: UUID, original_filename: str, used: set[str]) -> str:
    """包内唯一 stem：{id前8}_{安全化原名}；冲突再追加 id 片段。"""
    hex_id = str(asset_id).replace("-", "")
    base = f"{hex_id[:8]}_{sanitize_stem(original_filename)}"
    stem = base
    n = 8
    while stem in used:
        n = min(n + 4, len(hex_id))
        stem = f"{hex_id[:n]}_{sanitize_stem(original_filename)}"
        if n >= len(hex_id) and stem in used:
            stem = f"{hex_id}_{sanitize_stem(original_filename)}_{len(used)}"
            break
    used.add(stem)
    return stem


def ext_from_filename(filename: str | None, mime: str | None = None) -> str:
    ext = PurePosixPath(str(filename or "").replace("\\", "/")).suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
        return ".jpg" if ext == ".jpeg" else ext
    if mime:
        if "png" in mime:
            return ".png"
        if "webp" in mime:
            return ".webp"
        if "jpeg" in mime or "jpg" in mime:
            return ".jpg"
    return ".jpg"


def image_size_from_bytes(data: bytes) -> tuple[int, int] | None:
    """无 Pillow 时解析常见格式尺寸。"""
    if len(data) < 24:
        return None
    # PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
    # JPEG
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0xD9):
                i += 2
                continue
            if marker == 0x01 or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            if i + 4 > len(data):
                break
            seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB):
                if i + 9 < len(data):
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    return int(w), int(h)
            i += 2 + seg_len
    return None


def xyxy_to_yolo(
    bbox: list[Any],
    width: int,
    height: int,
) -> tuple[float, float, float, float] | None:
    if width <= 0 or height <= 0 or len(bbox) < 4:
        return None
    x1, y1, x2, y2 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    bw = max(0.0, x2 - x1)
    bh = max(0.0, y2 - y1)
    if bw <= 0 or bh <= 0:
        return None
    cx = (x1 + x2) / 2.0 / width
    cy = (y1 + y2) / 2.0 / height
    nw = bw / width
    nh = bh / height
    # clamp 到 [0,1]
    cx = min(1.0, max(0.0, cx))
    cy = min(1.0, max(0.0, cy))
    nw = min(1.0, max(0.0, nw))
    nh = min(1.0, max(0.0, nh))
    return cx, cy, nw, nh


def _build_data_yaml(classes: list[str]) -> str:
    lines = [
        "path: .",
        "train: train/images",
        "val: val/images",
        "test: test/images",
        f"nc: {len(classes)}",
        "names:",
    ]
    for i, name in enumerate(classes):
        safe = str(name).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  {i}: "{safe}"')
    lines.append("")
    return "\n".join(lines)


def _safe_download_name(dataset_name: str, version_name: str) -> str:
    parts = [
        sanitize_stem(dataset_name, max_len=32) or "dataset",
        sanitize_stem(version_name, max_len=32) or "version",
    ]
    return f"{'_'.join(parts)}.zip"


def export_storage_key(project_id: UUID, version_id: UUID) -> str:
    return f"proj/{project_id}/exports/{version_id}.zip"


def build_yolo_zip_bytes(
    db: Session,
    version: DatasetVersion,
    dataset: Dataset,
) -> tuple[bytes, dict[str, Any]]:
    """根据版本快照组装 zip 字节与统计。"""
    classes = [str(c) for c in (version.classes or [])]
    entries = list((version.manifest or {}).get("entries") or [])
    if not entries:
        raise ValidationAppError("版本无成员，无法导出")

    used_stems: set[str] = set()
    buf = io.BytesIO()
    image_count = 0
    counts = {"train": 0, "val": 0, "test": 0, "labels_with_boxes": 0, "empty_labels": 0}

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            raw_id = entry.get("assetId")
            if not raw_id:
                continue
            try:
                asset_id = UUID(str(raw_id))
            except ValueError as e:
                raise ValidationAppError(f"快照含非法 assetId: {raw_id}") from e

            asset = db.get(Asset, asset_id)
            if asset is None:
                raise ValidationAppError(
                    f"快照引用的素材不存在: {asset_id}（禁止硬删被引用素材后仍应存在）"
                )

            split = str(entry.get("split") or "train").lower()
            if split not in _SPLITS:
                split = "train"

            original_name = str(entry.get("filename") or asset.filename or "img.jpg")
            stem = export_stem(asset_id, original_name, used_stems)
            ext = ext_from_filename(original_name, asset.mime)
            img_name = f"{stem}{ext}"
            label_name = f"{stem}.txt"

            data = read_asset_bytes(asset)
            w = asset.width
            h = asset.height
            if not w or not h:
                size = image_size_from_bytes(data)
                if size:
                    w, h = size
            if not w or not h:
                # 无框时尚可导出；有框则必须有尺寸
                shapes = entry.get("shapes") or {}
                items = shapes.get("items") if isinstance(shapes, dict) else []
                if items:
                    raise ValidationAppError(
                        f"无法取得图片尺寸，不能归一化标注: {original_name}"
                    )
                w, h = 1, 1

            label_lines: list[str] = []
            shapes = entry.get("shapes") or {}
            items = shapes.get("items") if isinstance(shapes, dict) else []
            if not isinstance(items, list):
                items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("type") not in (None, "rect"):
                    continue
                bbox = item.get("bbox")
                if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
                    continue
                cls_idx = int(item.get("cls") or 0)
                if classes and (cls_idx < 0 or cls_idx >= len(classes)):
                    logger.warning(
                        "export_cls_out_of_range asset_id=%s cls=%s nc=%s",
                        asset_id,
                        cls_idx,
                        len(classes),
                    )
                yolo = xyxy_to_yolo(list(bbox), int(w), int(h))
                if yolo is None:
                    continue
                cx, cy, nw, nh = yolo
                label_lines.append(
                    f"{cls_idx} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"
                )

            zf.writestr(f"{split}/images/{img_name}", data)
            zf.writestr(
                f"{split}/labels/{label_name}",
                ("\n".join(label_lines) + ("\n" if label_lines else "")),
            )
            counts[split] += 1
            image_count += 1
            if label_lines:
                counts["labels_with_boxes"] += 1
            else:
                counts["empty_labels"] += 1

        zf.writestr("data.yaml", _build_data_yaml(classes))

    stats = {
        "imageCount": image_count,
        "classCount": len(classes),
        "splits": {
            "train": counts["train"],
            "val": counts["val"],
            "test": counts["test"],
        },
        "labelsWithBoxes": counts["labels_with_boxes"],
        "emptyLabels": counts["empty_labels"],
        "downloadName": _safe_download_name(dataset.name, version.name),
    }
    return buf.getvalue(), stats


def run_yolo_export(version_id: UUID) -> dict[str, Any]:
    """Job 入口：读快照 → 写 zip → BlobStore。"""
    db = SessionLocal()
    try:
        version = db.get(DatasetVersion, version_id)
        if version is None:
            raise NotFoundError("版本不存在")
        dataset = db.get(Dataset, version.dataset_id)
        if dataset is None:
            raise NotFoundError("数据集不存在")

        zip_bytes, stats = build_yolo_zip_bytes(db, version, dataset)
        backend = get_default_write_backend()
        key = export_storage_key(dataset.project_id, version.id)
        store = get_blob_store(backend)
        store.put(key, zip_bytes, content_type="application/zip")

        result = {
            "versionId": str(version.id),
            "datasetId": str(dataset.id),
            "projectId": str(dataset.project_id),
            "storageBackend": backend,
            "storageKey": key,
            "downloadName": stats["downloadName"],
            "bytes": len(zip_bytes),
            **{k: v for k, v in stats.items() if k != "downloadName"},
        }
        logger.info(
            "yolo_export_done version_id=%s images=%s bytes=%s key=%s",
            version_id,
            result["imageCount"],
            result["bytes"],
            key,
        )
        return result
    finally:
        db.close()
