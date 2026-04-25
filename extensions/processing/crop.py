from __future__ import annotations

import math

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, crop_xy, primary_line


def crop_handler(lines, params):
    return crop_xy(primary_line(lines), params)


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
            ],
        )
    )
