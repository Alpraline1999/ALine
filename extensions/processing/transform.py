from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.expression_execution import DEFAULT_EXPRESSION_EXECUTOR
from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _transform_xy(line: Any, params: Optional[Dict[str, Any]] = None):
    xs, ys = line_xy(line)
    options = dict(params or {})
    x_expr = str(options.get("x_expr", "") or "").strip()
    y_expr = str(options.get("y_expr", "") or "").strip()
    new_xs, new_ys = DEFAULT_EXPRESSION_EXECUTOR.transform_xy(xs, ys, x_expr, y_expr)
    return line_from_xy(new_xs, new_ys)


def transform_handler(lines, params):
    return _transform_xy(primary_line(lines), params)


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
