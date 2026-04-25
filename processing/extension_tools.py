from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from processing.smoother import resample_uniform, resample_uniform_spacing


BUILTIN_EXTENSION_VERSION = "0.1.0"

Line = List[List[float]]
SeriesInput = Dict[str, Any]
XY = Tuple[List[float], List[float]]


def normalize_line(raw: Any) -> Line:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError("line 必须是 [x, y]")
    xs = list(raw[0] or [])
    ys = list(raw[1] or [])
    if len(xs) != len(ys):
        raise ValueError("line 中 x 与 y 长度必须一致")
    return [xs, ys]


def normalize_lines(raw: Any) -> List[Line]:
    if raw in (None, "", [], ()):  # type: ignore[comparison-overlap]
        return []
    return [normalize_line(item) for item in list(raw)]


def line_from_xy(xs: List[float], ys: List[float]) -> Line:
    x_values = list(xs or [])
    y_values = list(ys or [])
    if len(x_values) != len(y_values):
        raise ValueError("line 中 x 与 y 长度必须一致")
    return [x_values, y_values]


def line_xy(line: Any) -> XY:
    normalized = normalize_line(line)
    return list(normalized[0]), list(normalized[1])


def primary_line(lines: Any) -> Line:
    normalized = normalize_lines(lines)
    return normalized[0] if normalized else [[], []]


def series_payload_to_line(item: Any) -> Line:
    if isinstance(item, dict):
        return line_from_xy(list(item.get("x", []) or []), list(item.get("y", []) or []))
    return line_from_xy(list(getattr(item, "x", []) or []), list(getattr(item, "y", []) or []))


def series_payloads_to_lines(raw: Any) -> List[Line]:
    return [series_payload_to_line(item) for item in list(raw or [])]


def line_payloads_from_lines(raw: Any) -> List[SeriesInput]:
    payloads: List[SeriesInput] = []
    for index, line in enumerate(normalize_lines(raw), start=1):
        xs, ys = line_xy(line)
        payloads.append({"name": f"line_{index}", "x": xs, "y": ys})
    return payloads


def _sorted_unique_xy(xs: List[float], ys: List[float]) -> XY:
    pairs = []
    for x_value, y_value in zip(xs, ys):
        try:
            x_float = float(x_value)
            y_float = float(y_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(x_float) or not math.isfinite(y_float):
            continue
        pairs.append((x_float, y_float))
    if len(pairs) < 2:
        return list(xs), list(ys)

    pairs.sort(key=lambda item: item[0])
    unique_x: List[float] = []
    unique_y: List[float] = []
    for x_value, y_value in pairs:
        if unique_x and math.isclose(x_value, unique_x[-1], rel_tol=0.0, abs_tol=1e-12):
            unique_y[-1] = y_value
            continue
        unique_x.append(x_value)
        unique_y.append(y_value)
    return unique_x, unique_y


def _estimate_sample_spacing(xs: List[float]) -> Optional[float]:
    x_sorted, _ = _sorted_unique_xy(xs, xs)
    if len(x_sorted) < 2:
        return None
    diffs = [x_sorted[index + 1] - x_sorted[index] for index in range(len(x_sorted) - 1)]
    diffs = [abs(diff) for diff in diffs if diff and math.isfinite(diff)]
    if not diffs:
        return None
    diffs.sort()
    return diffs[len(diffs) // 2]


def resolve_sample_rate(xs: List[float], params: Dict[str, Any]) -> Optional[float]:
    raw_sample_rate = params.get("sampling_rate")
    try:
        sample_rate = float(raw_sample_rate)
    except (TypeError, ValueError):
        sample_rate = 0.0
    if sample_rate > 0:
        return sample_rate
    step = _estimate_sample_spacing(xs)
    if step is None or step <= 0:
        return None
    return 1.0 / step


def crop_xy(line: Any, params: Optional[Dict[str, Any]] = None) -> Line:
    xs, ys = line_xy(line)
    options = dict(params or {})
    raw_x_min = options.get("x_min")
    raw_x_max = options.get("x_max")
    x_min = -math.inf if raw_x_min in (None, "") else float(raw_x_min)
    x_max = math.inf if raw_x_max in (None, "") else float(raw_x_max)
    try:
        import numpy as np

        ax = np.asarray(xs, dtype=float)
        ay = np.asarray(ys, dtype=float)
        mask = (ax >= x_min) & (ax <= x_max)
        return line_from_xy(ax[mask].tolist(), ay[mask].tolist())
    except ImportError:
        pairs = [(x, y) for x, y in zip(xs, ys) if x_min <= x <= x_max]
        if not pairs:
            return [[], []]
        nx, ny = zip(*pairs)
        return line_from_xy(list(nx), list(ny))


def _interp_linear(x_value: float, xs: List[float], ys: List[float]) -> float:
    if not xs:
        return 0.0
    if x_value <= xs[0]:
        return ys[0]
    if x_value >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if xs[mid] <= x_value:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    if not span:
        return ys[lo]
    ratio = (x_value - xs[lo]) / span
    return ys[lo] + ratio * (ys[hi] - ys[lo])


def _nearest_value(x_value: float, xs: List[float], ys: List[float]) -> float:
    if not xs:
        return 0.0
    best_index = 0
    best_distance = abs(xs[0] - x_value)
    for index in range(1, len(xs)):
        distance = abs(xs[index] - x_value)
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return float(ys[best_index])


def _resample_to_grid(xs: List[float], ys: List[float], target_x: List[float], algorithm: str) -> List[float]:
    mode = str(algorithm or "linear").strip().lower()
    if mode == "nearest":
        return [_nearest_value(float(value), xs, ys) for value in target_x]
    if mode == "cubic":
        try:
            import numpy as np
            from scipy.interpolate import CubicSpline

            spline = CubicSpline(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), extrapolate=False)
            values = spline(np.asarray(target_x, dtype=float))
            result: List[float] = []
            for raw, fallback_x in zip(values.tolist(), target_x):
                if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                    result.append(_interp_linear(float(fallback_x), xs, ys))
                else:
                    result.append(float(raw))
            return result
        except Exception:
            pass
    return [_interp_linear(float(value), xs, ys) for value in target_x]


def _x_values_equal(a: List[float], b: List[float]) -> bool:
    if len(a) != len(b):
        return False
    for left, right in zip(a, b):
        if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12):
            return False
    return True


def resample_xy(
    line: Any,
    params: Optional[Dict[str, Any]] = None,
    *,
    lines: Optional[List[Line]] = None,
) -> Line:
    xs, ys = line_xy(line)
    options = dict(params or {})
    x_sorted, y_sorted = _sorted_unique_xy(xs, ys)
    if len(x_sorted) < 2:
        return line_from_xy(xs, ys)

    mode = str(options.get("mode", "spacing") or "spacing").strip().lower()
    if mode == "align":
        pool = normalize_lines(lines or [])
        if not pool:
            return line_from_xy(x_sorted, y_sorted)
        try:
            target_idx = int(options.get("target_line", options.get("target_index", 1)) or 1)
        except Exception:
            target_idx = 1
        if target_idx < 1 or target_idx > len(pool):
            return line_from_xy(x_sorted, y_sorted)
        target_x, _target_y = line_xy(pool[target_idx - 1])
        if not target_x or _x_values_equal(x_sorted, target_x):
            return line_from_xy(x_sorted, y_sorted)
        algorithm = str(options.get("algorithm", "linear") or "linear").strip().lower()
        return line_from_xy(list(target_x), _resample_to_grid(x_sorted, y_sorted, target_x, algorithm))

    if mode == "spacing":
        spacing_mode = str(options.get("spacing_mode", "") or "").strip().lower()
        if not spacing_mode:
            spacing_mode = "coord" if ("step" in options or "spacing" in options) else "point"
        if spacing_mode == "coord":
            spacing = float(options.get("step", options.get("spacing", 0.0)) or 0.0)
            if spacing <= 0:
                raise ValueError("坐标间距必须大于 0")
            nx, ny = resample_uniform_spacing(x_sorted, y_sorted, spacing)
            return line_from_xy(nx, ny)
        nx, ny = resample_uniform(x_sorted, y_sorted, max(2, int(options.get("n", 200) or 200)))
        return line_from_xy(nx, ny)

    nx, ny = resample_uniform(x_sorted, y_sorted, max(2, int(options.get("n", 200) or 200)))
    return line_from_xy(nx, ny)


def transform_xy(line: Any, params: Optional[Dict[str, Any]] = None) -> Line:
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