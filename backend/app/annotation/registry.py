"""按 type 校验 shapes；已注册 rect/polygon/mask/keypoint/obb/classification。"""

from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from app.core.errors import ValidationAppError
from app.core.logging import get_logger

logger = get_logger("labeltrace.annotation.registry")

Validator = Callable[[dict[str, Any]], dict[str, Any]]

INTERNAL_FORMAT = "xyxy_abs"
REGISTERED_TYPES = frozenset(
    {"rect", "polygon", "mask", "keypoint", "obb", "classification"}
)


def _parse_class_id(raw: Any, *, label: str = "classId") -> str:
    if raw is None or raw == "":
        raise ValidationAppError(f"{label} 缺少 classId")
    try:
        return str(UUID(str(raw)))
    except (TypeError, ValueError) as exc:
        raise ValidationAppError(f"{label} 须为 UUID") from exc


def _f(v: Any, *, what: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError) as exc:
        raise ValidationAppError(f"{what} 须为数值") from exc


def _xy(raw: Any, *, what: str) -> list[float]:
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise ValidationAppError(f"{what} 须为 [x,y]")
    return [_f(raw[0], what=f"{what}.x"), _f(raw[1], what=f"{what}.y")]


def _validate_rect(item: dict[str, Any]) -> dict[str, Any]:
    class_id = _parse_class_id(item.get("classId"), label="rect")
    bbox = item.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValidationAppError("rect.bbox 须为 [x1,y1,x2,y2]")
    x1, y1, x2, y2 = (_f(v, what="rect.bbox") for v in bbox)
    if x2 <= x1 or y2 <= y1:
        raise ValidationAppError("rect.bbox 须满足 x2>x1 且 y2>y1")
    return {"type": "rect", "classId": class_id, "bbox": [x1, y1, x2, y2]}


def _validate_polygon(item: dict[str, Any]) -> dict[str, Any]:
    class_id = _parse_class_id(item.get("classId"), label="polygon")
    points = item.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise ValidationAppError("polygon.points 至少 3 个点")
    pts = [_xy(p, what=f"polygon.points[{i}]") for i, p in enumerate(points)]
    return {"type": "polygon", "classId": class_id, "points": pts}


def _validate_obb(item: dict[str, Any]) -> dict[str, Any]:
    class_id = _parse_class_id(item.get("classId"), label="obb")
    cx = _f(item.get("cx"), what="obb.cx")
    cy = _f(item.get("cy"), what="obb.cy")
    w = _f(item.get("w"), what="obb.w")
    h = _f(item.get("h"), what="obb.h")
    angle = _f(item.get("angle"), what="obb.angle")
    if w <= 0 or h <= 0:
        raise ValidationAppError("obb.w/h 须大于 0")
    return {
        "type": "obb",
        "classId": class_id,
        "cx": cx,
        "cy": cy,
        "w": w,
        "h": h,
        "angle": angle,
    }


def _validate_keypoint(item: dict[str, Any]) -> dict[str, Any]:
    class_id = _parse_class_id(item.get("classId"), label="keypoint")
    points = item.get("points")
    if not isinstance(points, list) or len(points) < 1:
        raise ValidationAppError("keypoint.points 至少 1 个点")
    out_pts: list[dict[str, Any]] = []
    for i, raw in enumerate(points):
        if isinstance(raw, dict):
            x = _f(raw.get("x"), what=f"keypoint.points[{i}].x")
            y = _f(raw.get("y"), what=f"keypoint.points[{i}].y")
            pt: dict[str, Any] = {"x": x, "y": y}
            if "v" in raw and raw.get("v") is not None:
                v = int(raw["v"])
                if v not in (0, 1, 2):
                    raise ValidationAppError(
                        f"keypoint.points[{i}].v 须为 0/1/2"
                    )
                pt["v"] = v
            out_pts.append(pt)
        elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
            x, y = _xy(raw, what=f"keypoint.points[{i}]")
            out_pts.append({"x": x, "y": y})
        else:
            raise ValidationAppError(
                f"keypoint.points[{i}] 须为 {{x,y}} 或 [x,y]"
            )
    return {"type": "keypoint", "classId": class_id, "points": out_pts}


def _validate_mask(item: dict[str, Any]) -> dict[str, Any]:
    class_id = _parse_class_id(item.get("classId"), label="mask")
    strokes = item.get("strokes")
    if not isinstance(strokes, list) or len(strokes) < 1:
        raise ValidationAppError("mask.strokes 至少 1 笔")
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(strokes):
        if not isinstance(raw, dict):
            raise ValidationAppError(f"mask.strokes[{i}] 须为对象")
        pts_raw = raw.get("points")
        if not isinstance(pts_raw, list) or len(pts_raw) < 1:
            raise ValidationAppError(f"mask.strokes[{i}].points 至少 1 点")
        pts = [
            _xy(p, what=f"mask.strokes[{i}].points[{j}]")
            for j, p in enumerate(pts_raw)
        ]
        width = _f(raw.get("width", 12), what=f"mask.strokes[{i}].width")
        if width <= 0:
            raise ValidationAppError(f"mask.strokes[{i}].width 须大于 0")
        out.append({"points": pts, "width": width})
    return {"type": "mask", "classId": class_id, "strokes": out}


def _validate_classification(item: dict[str, Any]) -> dict[str, Any]:
    class_id = _parse_class_id(item.get("classId"), label="classification")
    return {"type": "classification", "classId": class_id}


class AnnotationTypeRegistry:
    def __init__(self) -> None:
        self._validators: dict[str, Validator] = {}

    def register(self, type_name: str, validator: Validator) -> None:
        self._validators[type_name] = validator
        logger.info("annotation_type_registered type=%s", type_name)

    def is_registered(self, type_name: str) -> bool:
        return type_name in self._validators

    def registered_types(self) -> frozenset[str]:
        return frozenset(self._validators)

    def validate_shapes(
        self,
        shapes: dict[str, Any],
        *,
        enabled_types: list[str],
        allowed_class_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(shapes, dict):
            raise ValidationAppError("shapes 须为对象")
        fmt = shapes.get("format") or INTERNAL_FORMAT
        if fmt not in (INTERNAL_FORMAT, "image_abs"):
            raise ValidationAppError(
                f"仅支持 format={INTERNAL_FORMAT}，收到 {fmt}"
            )
        items = shapes.get("items")
        if items is None:
            items = []
        if not isinstance(items, list):
            raise ValidationAppError("shapes.items 须为数组")
        enabled = set(enabled_types or [])
        normalized: list[dict[str, Any]] = []
        for i, raw in enumerate(items):
            if not isinstance(raw, dict):
                raise ValidationAppError(f"shapes.items[{i}] 须为对象")
            t = raw.get("type")
            if not t:
                raise ValidationAppError(f"shapes.items[{i}] 缺少 type")
            t = str(t)
            if t not in enabled:
                raise ValidationAppError(
                    f"类型 {t} 未在数据集启用（enabled={sorted(enabled)}）"
                )
            validator = self._validators.get(t)
            if validator is None:
                raise ValidationAppError(f"类型 {t} 服务端未注册")
            try:
                item = validator(raw)
            except ValidationAppError as exc:
                raise ValidationAppError(
                    f"shapes.items[{i}]: {exc}"
                ) from exc
            class_id = str(item["classId"])
            if allowed_class_ids is not None and class_id not in allowed_class_ids:
                raise ValidationAppError(
                    f"shapes.items[{i}] classId 不属于本数据集"
                )
            normalized.append(item)
        return {"format": INTERNAL_FORMAT, "items": normalized}


_registry: AnnotationTypeRegistry | None = None


def get_registry() -> AnnotationTypeRegistry:
    global _registry
    if _registry is None:
        reg = AnnotationTypeRegistry()
        reg.register("rect", _validate_rect)
        reg.register("polygon", _validate_polygon)
        reg.register("obb", _validate_obb)
        reg.register("keypoint", _validate_keypoint)
        reg.register("mask", _validate_mask)
        reg.register("classification", _validate_classification)
        _registry = reg
    return _registry
