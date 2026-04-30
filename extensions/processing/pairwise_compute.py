from __future__ import annotations

from typing import List, Tuple

from core.expression_execution import DEFAULT_EXPRESSION_EXECUTOR
from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import align_lines_to_common_x, BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, normalize_lines


def pairwise_compute_handler(lines, params):
    input_lines = normalize_lines(lines)
    options = dict(params or {})
    if len(input_lines) != 2:
        raise ValueError("双曲线计算需要恰好选择两条输入曲线")

    aligned_lines, _warnings = align_lines_to_common_x(input_lines, {"align_mode": "strict"})
    primary, secondary = aligned_lines
    x1, y1 = line_xy(primary)
    x2, y2 = line_xy(secondary)

    x_expr, y_expr = _resolve_pairwise_expressions(options)
    new_x, new_y = _evaluate_pairwise_expression(x_expr, y_expr, x1, y1, x2, y2)
    return line_from_xy(list(new_x), list(new_y))


def _resolve_pairwise_expressions(params: dict) -> Tuple[str, str]:
    x_expr = str(params.get("x_expr", "") or "").strip()
    y_expr = str(params.get("y_expr", "") or "").strip()
    if x_expr and y_expr:
        return x_expr, y_expr
    operator = str(params.get("operator", "") or "").strip().lower()
    fallback_y = {
        "add": "y1 + y2",
        "subtract": "y1 - y2",
        "multiply": "y1 * y2",
        "divide": "y1 / y2 if y2 != 0 else 0.0",
        "abs_diff": "abs(y1 - y2)",
    }.get(operator)
    if y_expr == "":
        y_expr = fallback_y or "y1 - y2"
    if x_expr == "":
        x_expr = "x1"
    return x_expr, y_expr


def _evaluate_pairwise_expression(
    x_expr: str,
    y_expr: str,
    x1: List[float],
    y1: List[float],
    x2: List[float],
    y2: List[float],
) -> Tuple[List[float], List[float]]:
    return DEFAULT_EXPRESSION_EXECUTOR.pairwise_xy(x_expr, y_expr, x1, y1, x2, y2)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="pairwise_compute",
            name="双曲线运算",
            handler=pairwise_compute_handler,
            description="使用两条输入曲线执行 x1/y1/x2/y2 表达式运算。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="x_expr", label="X 表达式", field_type="string", default="x1"),
                ExtensionConfigField(key="y_expr", label="Y 表达式", field_type="string", default="y1"),
            ],
        )
    )
