from __future__ import annotations

import math
from typing import Any, Dict, Optional

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _crop_xy(line: Any, params: Optional[Dict[str, Any]] = None):
    xs, ys = line_xy(line)
    if not xs or not ys:
        return line_from_xy(list(xs), list(ys))
    options = dict(params or {})
    auto_range = bool(options.get("auto_range", False))
    if auto_range:
        return line_from_xy(list(xs), list(ys))
    raw_x_min = options.get("x_min")
    raw_x_max = options.get("x_max")
    x_min = -math.inf if raw_x_min in (None, "") else float(raw_x_min)
    x_max = math.inf if raw_x_max in (None, "") else float(raw_x_max)
    min_x, max_x = min(xs), max(xs)
    if math.isinf(x_min) and x_min < 0:
        x_min = min_x
    if math.isinf(x_max) and x_max > 0:
        x_max = max_x
    pairs = [(x_value, y_value) for x_value, y_value in zip(xs, ys) if x_min <= x_value <= x_max]
    if not pairs:
        return []
    nx, ny = zip(*pairs)
    return line_from_xy(list(nx), list(ny))


def crop_handler(lines, params):
    return _crop_xy(primary_line(lines), params)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="crop",
            name="裁剪",
            handler=crop_handler,
            description="按 X 轴范围裁剪数据，只保留目标区间。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="x_min", label="X 最小值", field_type="number", default=None),
                ExtensionConfigField(key="x_max", label="X 最大值", field_type="number", default=None),
                ExtensionConfigField(key="auto_range", label="自动范围（不裁剪）", field_type="boolean", default=False),
            ],
        )
    )
