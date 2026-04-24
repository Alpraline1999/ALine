from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.builtin_ops import VERSION, build_single_line_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="crop",
            name="裁剪",
            handler=build_single_line_handler("crop"),
            description="按 X 轴范围裁剪数据，只保留目标区间。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(key="x_min", label="X 最小值", field_type="number", default=None),
                ExtensionConfigField(key="x_max", label="X 最大值", field_type="number", default=None),
            ],
        )
    )
