"""按 type 校验 shapes；P0 仅注册 rect；类别用稳定 classId。"""

from __future__ import annotations

from typing import Any, Callable
from uuid import UUID

from app.core.errors import ValidationAppError
from app.core.logging import get_logger

logger = get_logger("labeltrace.annotation.registry")

Validator = Callable[[dict[str, Any]], None]

INTERNAL_FORMAT = "xyxy_abs"


def _parse_class_id(raw: Any) -> str:
    if raw is None or raw == "":
        raise ValidationAppError("rect 缺少 classId")
    try:
        return str(UUID(str(raw)))
    except (TypeError, ValueError) as exc:
        raise ValidationAppError("rect.classId 须为 UUID") from exc


def _validate_rect(item: dict[str, Any]) -> None:
    if item.get("type") != "rect":
        raise ValidationAppError("期望 type=rect")
    _parse_class_id(item.get("classId"))
    bbox = item.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValidationAppError("rect.bbox 须为 [x1,y1,x2,y2]")
    try:
        x1, y1, x2, y2 = (float(v) for v in bbox)
    except (TypeError, ValueError) as exc:
        raise ValidationAppError("rect.bbox 须为数值") from exc
    if x2 <= x1 or y2 <= y1:
        raise ValidationAppError("rect.bbox 须满足 x2>x1 且 y2>y1")


class AnnotationTypeRegistry:
    def __init__(self) -> None:
        self._validators: dict[str, Validator] = {}

    def register(self, type_name: str, validator: Validator) -> None:
        self._validators[type_name] = validator
        logger.info("annotation_type_registered type=%s", type_name)

    def is_registered(self, type_name: str) -> bool:
        return type_name in self._validators

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
        if fmt != INTERNAL_FORMAT:
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
            if t not in enabled:
                raise ValidationAppError(
                    f"类型 {t} 未在数据集启用（enabled={sorted(enabled)}）"
                )
            validator = self._validators.get(str(t))
            if validator is None:
                raise ValidationAppError(f"类型 {t} 服务端未注册")
            validator(raw)
            class_id = _parse_class_id(raw.get("classId"))
            if allowed_class_ids is not None and class_id not in allowed_class_ids:
                raise ValidationAppError(
                    f"shapes.items[{i}] classId 不属于本数据集"
                )
            bbox = [float(v) for v in raw["bbox"]]
            normalized.append(
                {"type": "rect", "classId": class_id, "bbox": bbox}
            )
        return {"format": INTERNAL_FORMAT, "items": normalized}


_registry: AnnotationTypeRegistry | None = None


def get_registry() -> AnnotationTypeRegistry:
    global _registry
    if _registry is None:
        reg = AnnotationTypeRegistry()
        reg.register("rect", _validate_rect)
        _registry = reg
    return _registry
