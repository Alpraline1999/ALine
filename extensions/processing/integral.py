from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.builtin_ops import VERSION, build_single_line_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="integral",
            name="积分",
            handler=build_single_line_handler("integral"),
            description="计算积分或累积积分。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(key="cumulative", label="累计积分", field_type="boolean", default=False)
            ],
        )
    )
