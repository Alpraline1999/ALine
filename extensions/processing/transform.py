from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _transform_xy(line: Any, params: Optional[Dict[str, Any]] = None):
    xs, ys = line_xy(line)
    options = dict(params or {})
    x_expr = str(options.get("x_expr", "") or "").strip()
    y_expr = str(options.get("y_expr", "") or "").strip()
    try:
        import math as _math

        try:
            import numpy as np
        except ImportError:
            np = None
        safe_globals = {
            "__builtins__": {},
            "math": _math,
            "abs": abs,
            "min": min,
            "max": max,
            "round": round,
            "sqrt": _math.sqrt,
            "log": _math.log,
            "log10": _math.log10,
            "exp": _math.exp,
            "sin": _math.sin,
            "cos": _math.cos,
            "tan": _math.tan,
            "pi": _math.pi,
            "e": _math.e,
        }
        if np is not None:
            safe_globals["np"] = np
            try:
                x_arr = np.asarray(xs, dtype=float)
                y_arr = np.asarray(ys, dtype=float)
                ctx = {"x": x_arr, "y": y_arr}
                for fn in ("sqrt", "log", "log10", "exp", "sin", "cos", "tan", "abs"):
                    safe_globals[fn] = getattr(np, fn)
                nx = eval(x_expr, safe_globals, ctx) if x_expr else x_arr  # noqa: S307
                ny = eval(y_expr, safe_globals, ctx) if y_expr else y_arr  # noqa: S307
                return line_from_xy(np.asarray(nx, dtype=float).tolist(), np.asarray(ny, dtype=float).tolist())
            except Exception:
                pass
        new_xs: List[float] = []
        new_ys: List[float] = []
        for x_value, y_value in zip(xs, ys):
            ctx = {"x": x_value, "y": y_value}
            nx = eval(x_expr, safe_globals, ctx) if x_expr else x_value  # noqa: S307
            ny = eval(y_expr, safe_globals, ctx) if y_expr else y_value  # noqa: S307
            new_xs.append(float(nx))
            new_ys.append(float(ny))
        return line_from_xy(new_xs, new_ys)
    except Exception:
        return line_from_xy(xs, ys)


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
