from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence, Tuple, cast


_VECTOR_SYMBOL_NAMES = ("sqrt", "log", "log10", "exp", "sin", "cos", "tan", "abs", "minimum", "maximum")


def _build_math_symbols() -> dict[str, Any]:
    symbols: dict[str, Any] = {
        "__builtins__": {},
        "math": math,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sqrt": math.sqrt,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "pi": math.pi,
        "e": math.e,
    }
    np: Any = None
    try:
        import numpy as np
    except ImportError:
        pass
    if np is not None:
        symbols["np"] = np
        for name in _VECTOR_SYMBOL_NAMES:
            if hasattr(np, name):
                symbols[name] = getattr(np, name)
    return symbols


@dataclass(frozen=True)
class ExpressionContextBuilder:
    extra_symbols: Mapping[str, Any] = field(default_factory=dict)

    def build(self) -> dict[str, Any]:
        symbols = _build_math_symbols()
        symbols.update(dict(self.extra_symbols or {}))
        return symbols


class ExpressionExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class ExpressionExecutionService:
    context_builder: ExpressionContextBuilder = field(default_factory=ExpressionContextBuilder)

    def _evaluate_scalar(self, expression: str, context: Mapping[str, Any], safe_globals: dict[str, Any]) -> Any:
        return eval(expression, safe_globals, dict(context))  # noqa: S307

    def _evaluate_vector(
        self,
        expression: str,
        context: Mapping[str, Any],
        safe_globals: dict[str, Any],
        numpy_module: Any,
    ) -> Any:
        return eval(expression, safe_globals, dict(context))  # noqa: S307

    def transform_xy(
        self,
        xs: Sequence[float],
        ys: Sequence[float],
        x_expr: str,
        y_expr: str,
    ) -> Tuple[list[float], list[float]]:
        expression_x = str(x_expr or "").strip()
        expression_y = str(y_expr or "").strip()
        safe_globals = self.context_builder.build()

        try:
            import numpy as np
        except ImportError:
            np = cast(Any, None)

        if np is not None:
            try:
                x_arr = np.asarray(xs, dtype=float)
                y_arr = np.asarray(ys, dtype=float)
                ctx: dict[str, Any] = {"x": x_arr, "y": y_arr}
                nx = x_arr if not expression_x else self._evaluate_vector(expression_x, ctx, safe_globals, np)
                ny = y_arr if not expression_y else self._evaluate_vector(expression_y, ctx, safe_globals, np)
                return np.asarray(nx, dtype=float).tolist(), np.asarray(ny, dtype=float).tolist()
            except Exception:
                pass

        new_xs: list[float] = []
        new_ys: list[float] = []
        try:
            for x_value, y_value in zip(xs, ys):
                ctx_scalar: dict[str, Any] = {"x": float(x_value), "y": float(y_value)}
                nx = x_value if not expression_x else self._evaluate_scalar(expression_x, ctx_scalar, safe_globals)
                ny = y_value if not expression_y else self._evaluate_scalar(expression_y, ctx_scalar, safe_globals)
                new_xs.append(float(nx))
                new_ys.append(float(ny))
        except Exception as exc:
            raise ExpressionExecutionError(f"表达式执行失败: {expression_x!r}, {expression_y!r}") from exc
        return new_xs, new_ys

    def pairwise_xy(
        self,
        x_expr: str,
        y_expr: str,
        x1: Sequence[float],
        y1: Sequence[float],
        x2: Sequence[float],
        y2: Sequence[float],
    ) -> Tuple[list[float], list[float]]:
        expression_x = str(x_expr or "").strip()
        expression_y = str(y_expr or "").strip()
        safe_globals = self.context_builder.build()

        try:
            import numpy as np
        except ImportError:
            np = cast(Any, None)

        if np is not None:
            try:
                a1 = np.asarray(x1, dtype=float)
                b1 = np.asarray(y1, dtype=float)
                a2 = np.asarray(x2, dtype=float)
                b2 = np.asarray(y2, dtype=float)
                ctx: dict[str, Any] = {"x1": a1, "y1": b1, "x2": a2, "y2": b2}
                nx = a1 if not expression_x else self._evaluate_vector(expression_x, ctx, safe_globals, np)
                ny = b1 if not expression_y else self._evaluate_vector(expression_y, ctx, safe_globals, np)
                return np.asarray(nx, dtype=float).tolist(), np.asarray(ny, dtype=float).tolist()
            except Exception:
                pass

        new_xs: list[float] = []
        new_ys: list[float] = []
        try:
            for left_x, left_y, right_x, right_y in zip(x1, y1, x2, y2):
                ctx_scalar: dict[str, Any] = {
                    "x1": float(left_x),
                    "y1": float(left_y),
                    "x2": float(right_x),
                    "y2": float(right_y),
                }
                nx = left_x if not expression_x else self._evaluate_scalar(expression_x, ctx_scalar, safe_globals)
                ny = left_y if not expression_y else self._evaluate_scalar(expression_y, ctx_scalar, safe_globals)
                new_xs.append(float(nx))
                new_ys.append(float(ny))
        except Exception as exc:
            raise ExpressionExecutionError(f"表达式执行失败: {expression_x!r}, {expression_y!r}") from exc
        return new_xs, new_ys


DEFAULT_EXPRESSION_EXECUTOR = ExpressionExecutionService()
