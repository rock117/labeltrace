"""导入 YOLO detect zip → 数据集成员与标注。"""

from __future__ import annotations

import io
import mimetypes
import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.models.dataset import Dataset, DatasetAsset
from app.models.dataset_import import DatasetImport
from app.services.assets import _sha256, _storage_key
from app.services.dataset_classes import create_classes_from_names, list_classes
from app.services.export_yolo import image_size_from_bytes
from app.storage.factory import get_blob_store, get_default_write_backend

logger = get_logger("labeltrace.import_yolo")

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
_SPLITS = ("train", "val", "test")


@dataclass
class ParsedImage:
    split: str
    source_path: str
    filename: str
    stem: str
    data: bytes
    label_text: str | None  # None = 无 label 文件；"" = 空负样本


def _norm_zip_path(name: str) -> str:
    return name.replace("\\", "/").lstrip("/")


def parse_data_yaml_names(text: str) -> list[str]:
    """解析常见 YOLO data.yaml 的 names（无 PyYAML 依赖）。"""
    # names: [a, b] 或 names: ['a', "b"]
    m = re.search(
        r"^names\s*:\s*\[([^\]]*)\]",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    if m:
        inner = m.group(1).strip()
        if not inner:
            return []
        parts = re.findall(r"""(['"])(.*?)\1|([^,\s]+)""", inner)
        out: list[str] = []
        for q, quoted, bare in parts:
            name = quoted if q else bare
            name = name.strip()
            if name:
                out.append(name)
        if out:
            return out

    # names:\n  0: xx\n  1: yy  或  - xx
    block = re.search(
        r"^names\s*:\s*\n((?:[ \t]+.+\n?)*)",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    if block:
        lines = block.group(1).splitlines()
        indexed: dict[int, str] = {}
        listed: list[str] = []
        for line in lines:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            m_idx = re.match(
                r"""^(\d+)\s*:\s*['"]?(.+?)['"]?\s*$""",
                s,
            )
            if m_idx:
                indexed[int(m_idx.group(1))] = m_idx.group(2).strip()
                continue
            m_list = re.match(r"""^-\s*['"]?(.+?)['"]?\s*$""", s)
            if m_list:
                listed.append(m_list.group(1).strip())
        if indexed:
            return [indexed[i] for i in sorted(indexed)]
        if listed:
            return listed

    raise ValidationAppError("data.yaml 缺少可解析的 names")


def yolo_line_to_xyxy(
    parts: list[str],
    width: int,
    height: int,
    *,
    class_ids: list[str],
) -> dict[str, Any] | None:
    if len(parts) < 5 or width <= 0 or height <= 0:
        return None
    try:
        cls_idx = int(float(parts[0]))
        cx, cy, nw, nh = (
            float(parts[1]),
            float(parts[2]),
            float(parts[3]),
            float(parts[4]),
        )
    except ValueError:
        return None
    if cls_idx < 0 or cls_idx >= len(class_ids):
        return None
    bw = nw * width
    bh = nh * height
    x1 = (cx * width) - bw / 2.0
    y1 = (cy * height) - bh / 2.0
    x2 = x1 + bw
    y2 = y1 + bh
    # clamp
    x1 = max(0.0, min(float(width), x1))
    y1 = max(0.0, min(float(height), y1))
    x2 = max(0.0, min(float(width), x2))
    y2 = max(0.0, min(float(height), y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return {
        "type": "rect",
        "classId": class_ids[cls_idx],
        "bbox": [x1, y1, x2, y2],
    }


def _find_data_yaml(names: list[str]) -> str | None:
    candidates = [n for n in names if _norm_zip_path(n).lower().endswith("data.yaml")]
    if not candidates:
        return None
    # 优先根目录较短路径
    candidates.sort(key=lambda n: (_norm_zip_path(n).count("/"), len(n)))
    return candidates[0]


def _infer_split_and_role(path: str) -> tuple[str | None, str | None, str]:
    """返回 (split|None, 'images'|'labels'|None, filename)。"""
    p = PurePosixPath(_norm_zip_path(path))
    parts = [x.lower() for x in p.parts]
    filename = p.name
    split: str | None = None
    for s in _SPLITS:
        if s in parts:
            split = s
            break
    role: str | None = None
    if "images" in parts:
        role = "images"
    elif "labels" in parts:
        role = "labels"
    return split, role, filename


def parse_yolo_zip(zip_bytes: bytes) -> tuple[list[str], list[ParsedImage]]:
    """解析 YOLO detect zip；非法结构抛 ValidationAppError。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise ValidationAppError("不是有效的 zip 文件") from e

    with zf:
        names = [
            n
            for n in zf.namelist()
            if not n.endswith("/") and not PurePosixPath(n).name.startswith(".")
        ]
        yaml_path = _find_data_yaml(names)
        if not yaml_path:
            raise ValidationAppError("缺少 data.yaml")
        try:
            yaml_text = zf.read(yaml_path).decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValidationAppError("data.yaml 不是合法 UTF-8") from e
        classes = parse_data_yaml_names(yaml_text)
        if not classes:
            raise ValidationAppError("data.yaml names 为空")

        # 建 labels 索引： (split or '_', stem) -> text
        labels: dict[tuple[str, str], str] = {}
        images_meta: list[tuple[str, str, str, str]] = []
        # (split, source_path, filename, stem)

        for name in names:
            path = _norm_zip_path(name)
            if path.lower().endswith("data.yaml"):
                continue
            split, role, filename = _infer_split_and_role(path)
            ext = PurePosixPath(filename).suffix.lower()
            stem = PurePosixPath(filename).stem
            if role == "labels" and ext == ".txt":
                key_split = split or "_"
                try:
                    labels[(key_split, stem)] = zf.read(name).decode("utf-8")
                except UnicodeDecodeError:
                    labels[(key_split, stem)] = ""
            elif role == "images" and ext in _IMAGE_EXTS:
                images_meta.append((split or "train", path, filename, stem))
            elif role is None and ext in _IMAGE_EXTS and "labels" not in path.lower():
                # 平面 images/ 已由 role 覆盖；其它宽松：仅当路径含 images
                continue

        if not images_meta:
            # 再试：任意 */*.jpg 且同级或平行 labels
            for name in names:
                path = _norm_zip_path(name)
                ext = PurePosixPath(path).suffix.lower()
                if ext not in _IMAGE_EXTS:
                    continue
                split, role, filename = _infer_split_and_role(path)
                if role == "labels":
                    continue
                if role == "images" or any(
                    f"/{s}/" in f"/{path.lower()}" for s in _SPLITS
                ):
                    stem = PurePosixPath(filename).stem
                    images_meta.append((split or "train", path, filename, stem))

        if not images_meta:
            raise ValidationAppError(
                "未找到图像（期望 train|val|test/images 或 images/）"
            )

        path_to_member = {_norm_zip_path(n): n for n in names}
        parsed: list[ParsedImage] = []
        for split, path, filename, stem in images_meta:
            member = path_to_member.get(path)
            if member is None:
                continue
            data = zf.read(member)
            label_key = (split, stem)
            alt_key = ("_", stem)
            if label_key in labels:
                label_text: str | None = labels[label_key]
            elif alt_key in labels:
                label_text = labels[alt_key]
            else:
                label_text = ""
            parsed.append(
                ParsedImage(
                    split=split if split in _SPLITS else "train",
                    source_path=path,
                    filename=filename,
                    stem=stem,
                    data=data,
                    label_text=label_text,
                )
            )

    if not parsed:
        raise ValidationAppError("zip 内没有可导入的图像")
    return classes, parsed


def _ensure_classes(db: Session, dataset_id: UUID, classes: list[str]) -> list[str]:
    """覆盖为空集写入类别，返回有序 classId 列表。"""
    existing = list_classes(db, dataset_id)
    for row in existing:
        db.delete(row)
    db.flush()
    rows = create_classes_from_names(db, dataset_id, classes)
    return [str(r.id) for r in rows]


def run_dataset_import(import_id: UUID) -> dict[str, Any]:
    db = SessionLocal()
    try:
        imp = db.get(DatasetImport, import_id)
        if imp is None:
            raise NotFoundError("导入记录不存在")
        if not imp.storage_key or not imp.storage_backend:
            raise ValidationAppError("导入包文件缺失")

        imp.status = "running"
        db.commit()

        store = get_blob_store(imp.storage_backend)
        if not store.exists(imp.storage_key):
            raise ValidationAppError("导入包对象不存在")
        zip_bytes = b"".join(store.get(imp.storage_key))

        classes, images = parse_yolo_zip(zip_bytes)

        ds = db.get(Dataset, imp.dataset_id) if imp.dataset_id else None
        if ds is None:
            raise ValidationAppError("目标数据集不存在")

        member_count = db.scalar(
            select(func.count())
            .select_from(DatasetAsset)
            .where(DatasetAsset.dataset_id == ds.id)
        )
        # 允许空集导入；非空则拒绝（P0）
        if member_count and member_count > 0:
            raise ValidationAppError("目标数据集非空，P0 仅支持导入到新建或空数据集")

        class_ids = _ensure_classes(db, ds.id, classes)

        created = 0
        reused = 0
        annotated = 0
        write_backend = get_default_write_backend()
        write_store = get_blob_store(write_backend)

        for img in images:
            digest = _sha256(img.data)
            existing = db.scalar(
                select(Asset).where(
                    Asset.project_id == imp.project_id,
                    Asset.content_hash == digest,
                    Asset.media_kind == "image",
                )
            )
            size = image_size_from_bytes(img.data)
            w, h = (size if size else (None, None))
            mime = mimetypes.guess_type(img.filename)[0] or "application/octet-stream"

            if existing is not None:
                asset = existing
                reused += 1
                if (not asset.width or not asset.height) and w and h:
                    asset.width = w
                    asset.height = h
            else:
                ext = PurePosixPath(img.filename).suffix.lower() or ".jpg"
                key = _storage_key(imp.project_id, digest, ext)
                if not write_store.exists(key):
                    write_store.put(key, img.data, content_type=mime)
                asset = Asset(
                    project_id=imp.project_id,
                    media_kind="image",
                    folder_id=None,
                    library_visible=False,
                    origin="import",
                    import_id=imp.id,
                    content_hash=digest,
                    storage_backend=write_backend,
                    storage_key=key,
                    filename=img.filename,
                    source_path=img.source_path,
                    width=w,
                    height=h,
                    mime=mime,
                )
                db.add(asset)
                db.flush()
                created += 1

            member = db.get(DatasetAsset, (ds.id, asset.id))
            if member is None:
                db.add(
                    DatasetAsset(
                        dataset_id=ds.id,
                        asset_id=asset.id,
                        split=img.split,
                    )
                )
            else:
                member.split = img.split

            # 标注
            items: list[dict[str, Any]] = []
            iw = asset.width or w
            ih = asset.height or h
            if img.label_text and iw and ih:
                for line in img.label_text.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    shape = yolo_line_to_xyxy(
                        parts, int(iw), int(ih), class_ids=class_ids
                    )
                    if shape is not None:
                        items.append(shape)

            shapes = {"format": "xyxy_abs", "items": items}
            ann = db.scalar(
                select(Annotation).where(
                    Annotation.dataset_id == ds.id,
                    Annotation.asset_id == asset.id,
                )
            )
            if ann is None:
                db.add(
                    Annotation(
                        dataset_id=ds.id,
                        asset_id=asset.id,
                        shapes=shapes,
                        status="submitted",
                        updated_by=imp.created_by,
                    )
                )
            else:
                ann.shapes = shapes
                ann.status = "submitted"
                ann.updated_by = imp.created_by
            annotated += 1

        stats = {
            "images": len(images),
            "created": created,
            "reused": reused,
            "annotated": annotated,
            "classes": classes,
            "packageName": imp.package_name,
        }
        imp.status = "succeeded"
        imp.stats = stats
        imp.error_message = None
        db.commit()
        logger.info(
            "dataset_import_done import_id=%s dataset_id=%s images=%s created=%s reused=%s",
            import_id,
            ds.id,
            len(images),
            created,
            reused,
        )
        return {
            "importId": str(imp.id),
            "datasetId": str(ds.id),
            "status": "succeeded",
            "stats": stats,
        }
    except Exception as e:
        db.rollback()
        imp = db.get(DatasetImport, import_id)
        if imp is not None:
            imp.status = "failed"
            imp.error_message = str(e)[:2000]
            db.commit()
        logger.exception("dataset_import_failed import_id=%s", import_id)
        raise
    finally:
        db.close()


def create_dataset_import(
    db: Session,
    *,
    project_id: UUID,
    package_name: str,
    zip_bytes: bytes,
    user_id: str,
    dataset_name: str | None,
    dataset_id: UUID | None,
    enqueue_job,
) -> DatasetImport:
    """校验权限与目标集，落盘 zip，创建记录并入队。"""
    from app.auth.deps import OWNER_ROLES, get_membership, has_any_role
    from app.models.project import Project

    if db.get(Project, project_id) is None:
        raise NotFoundError("项目不存在")
    m = get_membership(db, project_id, user_id)
    if m is None or not has_any_role(m, OWNER_ROLES):
        raise ForbiddenError("仅负责人可导入数据集")

    if not zip_bytes:
        raise ValidationAppError("上传文件为空")
    # 预校验结构（失败则不建记录）
    classes, images = parse_yolo_zip(zip_bytes)
    if not images:
        raise ValidationAppError("包内无图像")

    ds: Dataset | None = None
    if dataset_id is not None:
        ds = db.get(Dataset, dataset_id)
        if ds is None or ds.project_id != project_id:
            raise NotFoundError("数据集不存在")
        cnt = db.scalar(
            select(func.count())
            .select_from(DatasetAsset)
            .where(DatasetAsset.dataset_id == ds.id)
        )
        if cnt and cnt > 0:
            raise ValidationAppError("目标数据集非空，请新建数据集或清空后再导入")
    elif dataset_name and dataset_name.strip():
        ds = Dataset(
            project_id=project_id,
            name=dataset_name.strip(),
            enabled_annotation_types=["rect"],
        )
        db.add(ds)
        db.flush()
        create_classes_from_names(db, ds.id, classes)
    else:
        raise ValidationAppError("须提供 datasetName 或 datasetId")

    imp = DatasetImport(
        project_id=project_id,
        dataset_id=ds.id,
        package_name=(package_name or "package.zip").strip() or "package.zip",
        status="pending",
        stats={},
        created_by=user_id,
    )
    db.add(imp)
    db.flush()

    backend = get_default_write_backend()
    key = f"proj/{project_id}/imports/{imp.id}.zip"
    get_blob_store(backend).put(key, zip_bytes, content_type="application/zip")
    imp.storage_backend = backend
    imp.storage_key = key

    job = enqueue_job(db, "yolo_import", {"import_id": str(imp.id)})
    imp.job_id = job.id
    db.commit()
    db.refresh(imp)
    logger.info(
        "dataset_import_created import_id=%s dataset_id=%s job_id=%s images=%s",
        imp.id,
        ds.id,
        job.id,
        len(images),
    )
    return imp
