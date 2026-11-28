"""按版本快照导出 YOLO zip（按任务剖面：detect/segment/obb/pose/classify）。"""

from __future__ import annotations

import io
import math
import re
import struct
import zipfile
from pathlib import PurePosixPath
from typing import Any, Literal
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

ExportProfile = Literal["detect", "segment", "obb", "pose", "classify"]
VALID_PROFILES: frozenset[str] = frozenset(
    {"detect", "segment", "obb", "pose", "classify"}
)
PROFILE_SHAPE_TYPE: dict[str, str] = {
    "detect": "rect",
    "segment": "polygon",
    "obb": "obb",
    "pose": "keypoint",
    "classify": "classification",
}


def normalize_export_profile(raw: Any) -> ExportProfile:
    p = str(raw or "detect").strip().lower()
    if p not in VALID_PROFILES:
        raise ValidationAppError(
            f"未知导出剖面: {raw}（可选: {', '.join(sorted(VALID_PROFILES))}）"
        )
    return p  # type: ignore[return-value]


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
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return int(w), int(h)
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
    cx = min(1.0, max(0.0, cx))
    cy = min(1.0, max(0.0, cy))
    nw = min(1.0, max(0.0, nw))
    nh = min(1.0, max(0.0, nh))
    return cx, cy, nw, nh


def _clamp01(v: float) -> float:
    return min(1.0, max(0.0, v))


def _resolve_cls_idx(
    item: dict[str, Any],
    id_to_idx: dict[str, int],
    n_classes: int,
    *,
    asset_id: UUID,
) -> int | None:
    cid = item.get("classId")
    if cid is None or str(cid) not in id_to_idx:
        logger.warning("export_missing_class asset_id=%s item=%s", asset_id, item)
        return None
    cls_idx = id_to_idx[str(cid)]
    if n_classes and (cls_idx < 0 or cls_idx >= n_classes):
        logger.warning(
            "export_cls_out_of_range asset_id=%s cls=%s nc=%s",
            asset_id,
            cls_idx,
            n_classes,
        )
        return None
    return cls_idx


def _encode_detect_line(
    item: dict[str, Any], w: int, h: int, cls_idx: int
) -> str | None:
    bbox = item.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return None
    yolo = xyxy_to_yolo(list(bbox), w, h)
    if yolo is None:
        return None
    cx, cy, nw, nh = yolo
    return f"{cls_idx} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}"


def _encode_segment_line(
    item: dict[str, Any], w: int, h: int, cls_idx: int
) -> str | None:
    points = item.get("points")
    if not isinstance(points, list) or len(points) < 3 or w <= 0 or h <= 0:
        return None
    parts = [str(cls_idx)]
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            return None
        parts.append(f"{_clamp01(float(p[0]) / w):.6f}")
        parts.append(f"{_clamp01(float(p[1]) / h):.6f}")
    return " ".join(parts)


def _obb_corners(
    cx: float, cy: float, bw: float, bh: float, angle_deg: float
) -> list[tuple[float, float]]:
    """轴对齐矩形绕中心旋转后的四个角（像素）。"""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    hw, hh = bw / 2.0, bh / 2.0
    local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    out: list[tuple[float, float]] = []
    for lx, ly in local:
        out.append((cx + lx * cos_a - ly * sin_a, cy + lx * sin_a + ly * cos_a))
    return out


def _encode_obb_line(
    item: dict[str, Any], w: int, h: int, cls_idx: int
) -> str | None:
    try:
        cx = float(item["cx"])
        cy = float(item["cy"])
        bw = float(item["w"])
        bh = float(item["h"])
        angle = float(item.get("angle") or 0)
    except (KeyError, TypeError, ValueError):
        return None
    if bw <= 0 or bh <= 0 or w <= 0 or h <= 0:
        return None
    corners = _obb_corners(cx, cy, bw, bh, angle)
    parts = [str(cls_idx)]
    for x, y in corners:
        parts.append(f"{_clamp01(x / w):.6f}")
        parts.append(f"{_clamp01(y / h):.6f}")
    return " ".join(parts)


def _encode_pose_line(
    item: dict[str, Any],
    w: int,
    h: int,
    cls_idx: int,
    *,
    kpt_count: int,
) -> str | None:
    points = item.get("points")
    if not isinstance(points, list) or len(points) < 1 or w <= 0 or h <= 0:
        return None
    xs: list[float] = []
    ys: list[float] = []
    kpts: list[tuple[float, float, int]] = []
    for raw in points:
        if isinstance(raw, dict):
            try:
                x = float(raw["x"])
                y = float(raw["y"])
            except (KeyError, TypeError, ValueError):
                continue
            v = int(raw.get("v") if raw.get("v") is not None else 2)
            if v not in (0, 1, 2):
                v = 2
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            x, y = float(raw[0]), float(raw[1])
            v = 2
        else:
            continue
        xs.append(x)
        ys.append(y)
        kpts.append((x, y, v))
    if not kpts:
        return None
    x1, x2 = min(xs), max(xs)
    y1, y2 = min(ys), max(ys)
    # 退化点集给最小框
    if x2 - x1 < 1:
        x2 = x1 + 1
    if y2 - y1 < 1:
        y2 = y1 + 1
    box = xyxy_to_yolo([x1, y1, x2, y2], w, h)
    if box is None:
        return None
    cx, cy, nw, nh = box
    parts = [str(cls_idx), f"{cx:.6f}", f"{cy:.6f}", f"{nw:.6f}", f"{nh:.6f}"]
    for i in range(kpt_count):
        if i < len(kpts):
            x, y, v = kpts[i]
            parts.append(f"{_clamp01(x / w):.6f}")
            parts.append(f"{_clamp01(y / h):.6f}")
            parts.append(str(v))
        else:
            parts.extend(["0.000000", "0.000000", "0"])
    return " ".join(parts)


def _build_data_yaml(
    classes: list[str],
    *,
    profile: ExportProfile,
    kpt_count: int = 0,
) -> str:
    lines = [
        "path: .",
        "train: train/images" if profile != "classify" else "train: train",
        "val: val/images" if profile != "classify" else "val: val",
        "test: test/images" if profile != "classify" else "test: test",
        f"nc: {len(classes)}",
        "names:",
    ]
    for i, name in enumerate(classes):
        safe = str(name).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'  {i}: "{safe}"')
    if profile == "pose" and kpt_count > 0:
        lines.append(f"kpt_shape: [{kpt_count}, 3]")
    if profile == "obb":
        lines.append("task: obb")
    elif profile == "segment":
        lines.append("task: segment")
    elif profile == "pose":
        lines.append("task: pose")
    elif profile == "classify":
        lines.append("task: classify")
    else:
        lines.append("task: detect")
    lines.append("")
    return "\n".join(lines)


def _safe_download_name(
    dataset_name: str, version_name: str, profile: str
) -> str:
    parts = [
        sanitize_stem(dataset_name, max_len=32) or "dataset",
        sanitize_stem(version_name, max_len=32) or "version",
        sanitize_stem(profile, max_len=16) or "detect",
    ]
    return f"{'_'.join(parts)}.zip"


def export_storage_key(
    project_id: UUID, version_id: UUID, profile: str = "detect"
) -> str:
    p = normalize_export_profile(profile)
    return f"proj/{project_id}/exports/{version_id}_{p}.zip"


def _version_class_names(raw: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(raw, list):
        return names
    for item in raw:
        if isinstance(item, dict) and item.get("name") is not None:
            names.append(str(item["name"]))
    return names


def _class_id_to_index(raw: Any) -> dict[str, int]:
    mapping: dict[str, int] = {}
    if not isinstance(raw, list):
        return mapping
    for i, item in enumerate(raw):
        if isinstance(item, dict) and item.get("id") is not None:
            mapping[str(item["id"])] = i
    return mapping


def _class_id_to_name(raw: Any) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not isinstance(raw, list):
        return mapping
    for item in raw:
        if isinstance(item, dict) and item.get("id") is not None:
            mapping[str(item["id"])] = str(item.get("name") or item["id"])
    return mapping


def _safe_class_folder(name: str) -> str:
    cleaned = _SAFE_RE.sub("_", str(name or "class")).strip("._")
    return (cleaned or "class")[:64]


def _items_of_type(items: list[Any], shape_type: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if shape_type == "rect" and t in (None, "rect"):
            out.append(item)
        elif t == shape_type:
            out.append(item)
    return out


def _max_pose_keypoints(entries: list[Any]) -> int:
    m = 0
    for entry in entries:
        shapes = entry.get("shapes") or {}
        items = shapes.get("items") if isinstance(shapes, dict) else []
        if not isinstance(items, list):
            continue
        for item in _items_of_type(items, "keypoint"):
            pts = item.get("points")
            if isinstance(pts, list):
                m = max(m, len(pts))
    return max(m, 1)


def build_yolo_zip_bytes(
    db: Session,
    version: DatasetVersion,
    dataset: Dataset,
    *,
    profile: ExportProfile = "detect",
) -> tuple[bytes, dict[str, Any]]:
    """根据版本快照组装 zip 字节与统计。"""
    profile = normalize_export_profile(profile)
    shape_type = PROFILE_SHAPE_TYPE[profile]
    classes = _version_class_names(version.classes)
    id_to_idx = _class_id_to_index(version.classes)
    id_to_name = _class_id_to_name(version.classes)
    entries = list((version.manifest or {}).get("entries") or [])
    if not entries:
        raise ValidationAppError("版本无成员，无法导出")

    kpt_count = _max_pose_keypoints(entries) if profile == "pose" else 0
    used_stems: set[str] = set()
    buf = io.BytesIO()
    image_count = 0
    counts = {
        "train": 0,
        "val": 0,
        "test": 0,
        "labels_with_boxes": 0,
        "empty_labels": 0,
    }

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

            shapes = entry.get("shapes") or {}
            items = shapes.get("items") if isinstance(shapes, dict) else []
            if not isinstance(items, list):
                items = []
            typed = _items_of_type(items, shape_type)

            if profile != "classify":
                if not w or not h:
                    if typed:
                        raise ValidationAppError(
                            f"无法取得图片尺寸，不能归一化标注: {original_name}"
                        )
                    w, h = 1, 1

                label_lines: list[str] = []
                for item in typed:
                    cls_idx = _resolve_cls_idx(
                        item, id_to_idx, len(classes), asset_id=asset_id
                    )
                    if cls_idx is None:
                        continue
                    line: str | None = None
                    if profile == "detect":
                        line = _encode_detect_line(item, int(w), int(h), cls_idx)
                    elif profile == "segment":
                        line = _encode_segment_line(item, int(w), int(h), cls_idx)
                    elif profile == "obb":
                        line = _encode_obb_line(item, int(w), int(h), cls_idx)
                    elif profile == "pose":
                        line = _encode_pose_line(
                            item,
                            int(w),
                            int(h),
                            cls_idx,
                            kpt_count=kpt_count,
                        )
                    if line:
                        label_lines.append(line)

                zf.writestr(f"{split}/images/{img_name}", data)
                zf.writestr(
                    f"{split}/labels/{label_name}",
                    ("\n".join(label_lines) + ("\n" if label_lines else "")),
                )
                if label_lines:
                    counts["labels_with_boxes"] += 1
                else:
                    counts["empty_labels"] += 1
            else:
                # ImageFolder：每个分类一个目录；无标签 → _unlabeled
                class_folders: list[str] = []
                for item in typed:
                    cid = item.get("classId")
                    if cid is None:
                        continue
                    name = id_to_name.get(str(cid))
                    if name:
                        class_folders.append(_safe_class_folder(name))
                if not class_folders:
                    class_folders = ["_unlabeled"]
                    counts["empty_labels"] += 1
                else:
                    counts["labels_with_boxes"] += 1
                # 多标签：复制进多个类目录
                for folder in dict.fromkeys(class_folders):
                    zf.writestr(f"{split}/{folder}/{img_name}", data)

            counts[split] += 1
            image_count += 1

        zf.writestr(
            "data.yaml",
            _build_data_yaml(classes, profile=profile, kpt_count=kpt_count),
        )

    stats = {
        "imageCount": image_count,
        "classCount": len(classes),
        "profile": profile,
        "splits": {
            "train": counts["train"],
            "val": counts["val"],
            "test": counts["test"],
        },
        "labelsWithBoxes": counts["labels_with_boxes"],
        "emptyLabels": counts["empty_labels"],
        "downloadName": _safe_download_name(dataset.name, version.name, profile),
    }
    return buf.getvalue(), stats


def run_yolo_export(
    version_id: UUID, *, profile: str = "detect"
) -> dict[str, Any]:
    """Job 入口：读快照 → 写 zip → BlobStore。"""
    db = SessionLocal()
    try:
        version = db.get(DatasetVersion, version_id)
        if version is None:
            raise NotFoundError("版本不存在")
        dataset = db.get(Dataset, version.dataset_id)
        if dataset is None:
            raise NotFoundError("数据集不存在")

        prof = normalize_export_profile(profile)
        zip_bytes, stats = build_yolo_zip_bytes(
            db, version, dataset, profile=prof
        )
        backend = get_default_write_backend()
        key = export_storage_key(dataset.project_id, version.id, prof)
        store = get_blob_store(backend)
        store.put(key, zip_bytes, content_type="application/zip")

        result = {
            "versionId": str(version.id),
            "datasetId": str(dataset.id),
            "projectId": str(dataset.project_id),
            "profile": prof,
            "storageBackend": backend,
            "storageKey": key,
            "downloadName": stats["downloadName"],
            "bytes": len(zip_bytes),
            **{k: v for k, v in stats.items() if k != "downloadName"},
        }
        logger.info(
            "yolo_export_done version_id=%s profile=%s images=%s bytes=%s key=%s",
            version_id,
            prof,
            result["imageCount"],
            result["bytes"],
            key,
        )
        return result
    finally:
        db.close()
