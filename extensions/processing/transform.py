from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, primary_line, transform_xy


def transform_handler(lines, params):
    return transform_xy(primary_line(lines), params)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="transform",
            name="数学变换",
            handler=transform_handler,
            description="用表达式批量变换 X/Y 数据。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="x_expr", label="X 表达式", field_type="string", default="x"),
                ExtensionConfigField(key="y_expr", label="Y 表达式", field_type="string", default="y"),
            ],
        )
    )
