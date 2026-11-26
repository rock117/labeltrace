"""按 type 校验 shapes；P0 仅注册 rect。"""

from __future__ import annotations

from typing import Any, Callable

from app.core.errors import ValidationAppError
from app.core.logging import get_logger

logger = get_logger("labeltrace.annotation.registry")

Validator = Callable[[dict[str, Any]], None]

INTERNAL_FORMAT = "xyxy_abs"


def _validate_rect(item: dict[str, Any]) -> None:
    if item.get("type") != "rect":
        raise ValidationAppError("期望 type=rect")
    if "cls" not in item:
        raise ValidationAppError("rect 缺少 cls")
    try:
        cls = int(item["cls"])
    except (TypeError, ValueError) as exc:
        raise ValidationAppError("rect.cls 必须为整数") from exc
    if cls < 0:
        raise ValidationAppError("rect.cls 不可为负")
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
            bbox = [float(v) for v in raw["bbox"]]
            normalized.append(
                {"type": "rect", "cls": int(raw["cls"]), "bbox": bbox}
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
