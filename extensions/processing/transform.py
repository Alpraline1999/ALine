from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.base_tools import VERSION, transform_xy


def transform_handler(xs, ys, params, lines=None):
    del lines
    return transform_xy(list(xs), list(ys), dict(params or {}))


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="transform",
            name="数学变换",
            handler=transform_handler,
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
