from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.builtin_ops import VERSION, build_single_line_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="transform",
            name="数学变换",
            handler=build_single_line_handler("transform"),
            description="用表达式批量变换 X/Y 数据。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(key="x_expr", label="X 表达式", field_type="string", default="x"),
                ExtensionConfigField(key="y_expr", label="Y 表达式", field_type="string", default="y"),
            ],
        )
    )
