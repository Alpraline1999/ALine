from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.builtin_ops import VERSION, build_single_line_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="normalize",
            name="归一化",
            handler=build_single_line_handler("normalize"),
            description="按 min-max 或 z-score 归一化 Y 序列。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(
                    key="mode",
                    label="归一化方式",
                    field_type="selective",
                    default="minmax",
                    choices=["minmax", "zscore"],
                )
            ],
        )
    )
