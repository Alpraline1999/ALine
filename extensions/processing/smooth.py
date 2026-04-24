from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.builtin_ops import VERSION, build_single_line_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="smooth",
            name="平滑",
            handler=build_single_line_handler("smooth"),
            description="对 Y 序列做平滑处理，适合去除高频噪声。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(
                    key="method",
                    label="平滑方法",
                    field_type="selective",
                    default="savgol",
                    choices=["savgol", "moving_avg"],
                ),
                ExtensionConfigField(key="window", label="窗口大小", field_type="integer", default=9, min_value=1),
                ExtensionConfigField(key="poly", label="多项式阶数", field_type="integer", default=3, min_value=1),
            ],
        )
    )
