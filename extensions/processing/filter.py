from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.builtin_ops import VERSION, build_single_line_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="filter",
            name="滤波",
            handler=build_single_line_handler("filter"),
            description="进行低通或高通滤波，去除不需要的频率成分。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(
                    key="mode",
                    label="滤波模式",
                    field_type="selective",
                    default="low",
                    choices=["low", "high"],
                ),
                ExtensionConfigField(
                    key="cutoff_mode",
                    label="截止频率模式",
                    field_type="selective",
                    default="normalized",
                    choices=["normalized", "actual"],
                ),
                ExtensionConfigField(key="cutoff", label="截止频率", field_type="number", default=0.2),
                ExtensionConfigField(key="order", label="滤波阶数", field_type="integer", default=3, min_value=1),
                ExtensionConfigField(key="sampling_rate", label="采样率", field_type="number", default=1.0),
            ],
        )
    )
