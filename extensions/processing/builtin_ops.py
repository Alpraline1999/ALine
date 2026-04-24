from __future__ import annotations

import cmath
import math
from typing import Any, Dict, List, Optional, Tuple

from processing.smoother import (
    resample_uniform,
    resample_uniform_spacing,
    smooth_moving_average,
    smooth_savgol,
)

VERSION = "0.1.0"

XY = Tuple[List[float], List[float]]
PipelineLine = Dict[str, Any]
PipelineResult = Tuple[List[PipelineLine], List[str]]


def build_single_line_handler(type_id: str):
    def _handler(xs, ys, params, lines=None):
        operation = _BUILTIN_PROCESSING_OPS.get(type_id)
        if operation is None:
            return list(xs), list(ys)
        return operation(list(xs), list(ys), dict(params or {}), list(lines or []))

    return _handler


def pairwise_compute_handler(xs, ys, params, lines=None):
    del xs, ys
    result_lines, warnings = _op_pairwise_compute(_normalize_pipeline_lines(list(lines or [])), dict(params or {}))
    return {"lines": result_lines, "warnings": warnings}


def align_lines_to_common_x(
    lines: List[PipelineLine],
    params: Optional[Dict[str, Any]] = None,
) -> PipelineResult:
    prepared_lines = [_sorted_line_payload(line) for line in _normalize_pipeline_lines(lines)]
    if len(prepared_lines) < 2:
        return prepared_lines, []
    if _lines_share_same_x(prepared_lines):
        return prepared_lines, []

    options = dict(params or {})
    align_mode = str(options.get("align_mode", "auto") or "auto").strip().lower()
    if align_mode == "strict":
        raise ValueError("输入曲线 X 坐标未对齐，需进行坐标间距重采样")

    grid = _build_alignment_grid(prepared_lines, options)
    aligned_lines = []
    for line in prepared_lines:
        aligned_lines.append(
            _merge_line_payload(
                line,
                {
                    "x": list(grid),
                    "y": [_interp_linear(x_value, list(line.get("x", []) or []), list(line.get("y", []) or [])) for x_value in grid],
                },
            )
        )

    description = _describe_alignment_mode(options, len(grid))
    warnings = [
        "需进行坐标间距重采样",
        f"输入曲线 X 坐标未对齐，已在重叠区间内按{description}自动重采样。",
    ]
    return aligned_lines, warnings


def _normalize_pipeline_lines(lines: List[PipelineLine]) -> List[PipelineLine]:
    normalized: List[PipelineLine] = []
    for index, item in enumerate(lines or []):
        if isinstance(item, dict):
            payload = dict(item)
            payload["x"] = list(payload.get("x", []) or [])
            payload["y"] = list(payload.get("y", []) or [])
            payload["name"] = str(payload.get("name", f"line_{index + 1}") or f"line_{index + 1}")
        else:
            payload = {
                "name": str(getattr(item, "name", f"line_{index + 1}") or f"line_{index + 1}"),
                "x": list(getattr(item, "x", []) or []),
                "y": list(getattr(item, "y", []) or []),
            }
        normalized.append(payload)
    return normalized


def _merge_line_payload(base: PipelineLine, update: Dict[str, Any]) -> PipelineLine:
    merged = dict(base or {})
    for key, value in dict(update or {}).items():
        if key in {"warnings", "lines"}:
            continue
        merged[key] = value
    merged["x"] = list(merged.get("x", []) or [])
    merged["y"] = list(merged.get("y", []) or [])
    merged["name"] = str(merged.get("name", "") or "")
    return merged


def _sorted_line_payload(line: PipelineLine) -> PipelineLine:
    xs, ys = _sorted_unique_xy(list(line.get("x", []) or []), list(line.get("y", []) or []))
    return _merge_line_payload(line, {"x": xs, "y": ys})


def _lines_share_same_x(lines: List[PipelineLine]) -> bool:
    if len(lines) < 2:
        return True
    base_x = list(lines[0].get("x", []) or [])
    for line in lines[1:]:
        current_x = list(line.get("x", []) or [])
        if len(current_x) != len(base_x):
            return False
        for left, right in zip(base_x, current_x):
            if not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9):
                return False
    return True


def _build_alignment_grid(lines: List[PipelineLine], params: Dict[str, Any]) -> List[float]:
    starts = [float(line["x"][0]) for line in lines if len(line.get("x", []) or []) >= 2]
    ends = [float(line["x"][-1]) for line in lines if len(line.get("x", []) or []) >= 2]
    if not starts or not ends:
        raise ValueError("自动对齐至少需要每条曲线包含两个有效采样点")
    x_start = max(starts)
    x_end = min(ends)
    if x_end - x_start <= 1e-12:
        raise ValueError("输入曲线没有足够的重叠区间，无法执行自动对齐")

    resample_mode = str(params.get("resample_mode", params.get("mode", "count")) or "count").strip().lower()
    if resample_mode == "spacing":
        step = float(params.get("step", params.get("spacing", 0.0)) or 0.0)
        if step <= 0:
            step = _recommended_alignment_spacing(lines)
        if step <= 0:
            raise ValueError("无法推断有效的自动对齐重采样间距")
        grid = [x_start]
        next_x = x_start + step
        while next_x < x_end - 1e-12:
            grid.append(next_x)
            next_x += step
        if not math.isclose(grid[-1], x_end, rel_tol=0.0, abs_tol=1e-12):
            grid.append(x_end)
        return grid

    n_points = int(params.get("n", 0) or 0)
    if n_points < 2:
        n_points = max(len(line.get("x", []) or []) for line in lines)
    n_points = max(2, n_points)
    return [x_start + index * (x_end - x_start) / (n_points - 1) for index in range(n_points)]


def _recommended_alignment_spacing(lines: List[PipelineLine]) -> float:
    spacings = [
        spacing
        for line in lines
        for spacing in [_estimate_sample_spacing(list(line.get("x", []) or []))]
        if spacing is not None and spacing > 0
    ]
    return min(spacings) if spacings else 0.0


def _describe_alignment_mode(params: Dict[str, Any], point_count: int) -> str:
    resample_mode = str(params.get("resample_mode", params.get("mode", "count")) or "count").strip().lower()
    if resample_mode == "spacing":
        step = float(params.get("step", params.get("spacing", 0.0)) or 0.0)
        return f"固定间距({step:g})"
    return f"固定点数({point_count}点)"


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


def _op_pairwise_compute(lines: List[PipelineLine], p: Dict[str, Any]) -> PipelineResult:
    if len(lines) != 2:
        raise ValueError("双曲线计算需要恰好选择两条输入曲线")

    aligned_lines, _warnings = align_lines_to_common_x(lines, {"align_mode": "strict"})
    primary, secondary = aligned_lines
    x1 = list(primary.get("x", []) or [])
    y1 = list(primary.get("y", []) or [])
    x2 = list(secondary.get("x", []) or [])
    y2 = list(secondary.get("y", []) or [])

    x_expr, y_expr = _resolve_pairwise_expressions(p)
    new_x, new_y = _evaluate_pairwise_expression(x_expr, y_expr, x1, y1, x2, y2)

    default_name = f"{primary.get('name', '主曲线')} ⊕ {secondary.get('name', '副曲线')}"
    result_name = str(p.get("result_name", "") or "").strip() or default_name
    result_line = _merge_line_payload(primary, {"name": result_name, "x": list(new_x), "y": list(new_y)})
    return [result_line], []


def _resolve_pairwise_expressions(p: Dict[str, Any]) -> Tuple[str, str]:
    x_expr = str(p.get("x_expr", "") or "").strip()
    y_expr = str(p.get("y_expr", "") or "").strip()
    if x_expr and y_expr:
        return x_expr, y_expr
    operator = str(p.get("operator", "") or "").strip().lower()
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
    import math as _math

    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore

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
        for name in ("sqrt", "log", "log10", "exp", "sin", "cos", "tan", "abs", "minimum", "maximum"):
            if hasattr(np, name):
                safe_globals[name] = getattr(np, name)
        try:
            a1 = np.asarray(x1, dtype=float)
            b1 = np.asarray(y1, dtype=float)
            a2 = np.asarray(x2, dtype=float)
            b2 = np.asarray(y2, dtype=float)
            ctx = {"x1": a1, "y1": b1, "x2": a2, "y2": b2}
            nx = eval(x_expr, safe_globals, ctx)  # noqa: S307
            ny = eval(y_expr, safe_globals, ctx)  # noqa: S307
            return np.asarray(nx, dtype=float).tolist(), np.asarray(ny, dtype=float).tolist()
        except Exception:
            pass

    nx_list: List[float] = []
    ny_list: List[float] = []
    for left_x, left_y, right_x, right_y in zip(x1, y1, x2, y2):
        ctx = {"x1": float(left_x), "y1": float(left_y), "x2": float(right_x), "y2": float(right_y)}
        nx_list.append(float(eval(x_expr, safe_globals, ctx)))  # noqa: S307
        ny_list.append(float(eval(y_expr, safe_globals, ctx)))  # noqa: S307
    return nx_list, ny_list


def _x_values_equal(a: List[float], b: List[float]) -> bool:
    if len(a) != len(b):
        return False
    for left, right in zip(a, b):
        if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12):
            return False
    return True


def _op_crop(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    del lines
    raw_x_min = p.get("x_min")
    raw_x_max = p.get("x_max")
    x_min = -math.inf if raw_x_min in (None, "") else float(raw_x_min)
    x_max = math.inf if raw_x_max in (None, "") else float(raw_x_max)
    try:
        import numpy as np

        ax = np.asarray(xs, dtype=float)
        ay = np.asarray(ys, dtype=float)
        mask = (ax >= x_min) & (ax <= x_max)
        return ax[mask].tolist(), ay[mask].tolist()
    except ImportError:
        pairs = [(x, y) for x, y in zip(xs, ys) if x_min <= x <= x_max]
        if not pairs:
            return [], []
        nx, ny = zip(*pairs)
        return list(nx), list(ny)


def _op_smooth(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    del lines
    method = p.get("method", "savgol")
    if method == "savgol":
        return smooth_savgol(xs, ys, int(p.get("window", 11)), int(p.get("poly", 3)))
    if method == "moving_avg":
        return smooth_moving_average(xs, ys, int(p.get("window", 5)))
    return list(xs), list(ys)


def _op_normalize(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    del lines
    mode = p.get("mode", "minmax")
    if not ys:
        return list(xs), list(ys)
    try:
        import numpy as np

        ay = np.asarray(ys, dtype=float)
        if mode == "minmax":
            mn, mx = ay.min(), ay.max()
            ny = ((ay - mn) / (mx - mn or 1.0)).tolist()
        elif mode == "zscore":
            std = ay.std() or 1.0
            ny = ((ay - ay.mean()) / std).tolist()
        else:
            ny = list(ys)
    except ImportError:
        n = len(ys)
        if mode == "minmax":
            mn, mx = min(ys), max(ys)
            rng = mx - mn or 1.0
            ny = [(value - mn) / rng for value in ys]
        elif mode == "zscore":
            mean = sum(ys) / n
            std = math.sqrt(sum((value - mean) ** 2 for value in ys) / n) or 1.0
            ny = [(value - mean) / std for value in ys]
        else:
            ny = list(ys)
    return list(xs), ny


def _op_resample(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    x_sorted, y_sorted = _sorted_unique_xy(xs, ys)
    if len(x_sorted) < 2:
        return list(xs), list(ys)

    mode = str(p.get("mode", "spacing") or "spacing").strip().lower()
    if mode == "align":
        pool = _normalize_pipeline_lines(lines or [])
        if not pool:
            return x_sorted, y_sorted
        try:
            target_idx = int(p.get("target_index", 1) or 1)
        except Exception:
            target_idx = 1
        if target_idx < 1 or target_idx > len(pool):
            return x_sorted, y_sorted
        target = pool[target_idx - 1]
        target_x = list(target.get("x", []) or [])
        if not target_x or _x_values_equal(x_sorted, target_x):
            return x_sorted, y_sorted
        algorithm = str(p.get("algorithm", "linear") or "linear").strip().lower()
        return list(target_x), _resample_to_grid(x_sorted, y_sorted, target_x, algorithm)

    if mode == "spacing":
        spacing_mode = str(p.get("spacing_mode", "") or "").strip().lower()
        if not spacing_mode:
            spacing_mode = "coord" if ("step" in p or "spacing" in p) else "point"
        if spacing_mode == "coord":
            spacing = float(p.get("step", p.get("spacing", 0.0)) or 0.0)
            if spacing <= 0:
                raise ValueError("坐标间距必须大于 0")
            return resample_uniform_spacing(x_sorted, y_sorted, spacing)
        return resample_uniform(x_sorted, y_sorted, max(2, int(p.get("n", 200) or 200)))

    return resample_uniform(x_sorted, y_sorted, max(2, int(p.get("n", 200) or 200)))


def _resample_to_grid(xs: List[float], ys: List[float], target_x: List[float], algorithm: str) -> List[float]:
    algorithm = str(algorithm or "linear").strip().lower()
    if algorithm == "nearest":
        return [_nearest_value(float(value), xs, ys) for value in target_x]
    if algorithm == "cubic":
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


def _op_fft(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    del lines
    n = len(ys)
    if n < 2:
        return list(xs), list(ys)

    output = p.get("output", "amplitude")
    detrend = bool(p.get("detrend", True))
    sample_rate = _resolve_sample_rate(xs, p)
    try:
        import numpy as np

        y_arr = np.asarray(ys, dtype=float)
        if detrend:
            y_arr = y_arr - y_arr.mean()
        step = 1.0 / sample_rate if sample_rate and sample_rate > 0 else 1.0
        freq = np.fft.rfftfreq(n, d=step)
        spec = np.fft.rfft(y_arr)
        if output == "power":
            values = (np.abs(spec) ** 2 / max(1, n)).tolist()
        else:
            values = (np.abs(spec) / max(1, n)).tolist()
        return freq.tolist(), values
    except ImportError:
        step = 1.0 / sample_rate if sample_rate and sample_rate > 0 else 1.0
        sig = list(ys)
        if detrend:
            mean = sum(sig) / len(sig)
            sig = [value - mean for value in sig]
        half = n // 2
        freq: List[float] = []
        values: List[float] = []
        for k in range(half + 1):
            total = 0j
            for index, sample in enumerate(sig):
                total += sample * cmath.exp(-2j * math.pi * k * index / n)
            amp = abs(total) / max(1, n)
            freq.append(k / (n * step))
            values.append(amp * amp if output == "power" else amp)
        return freq, values


def _op_derivative(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    del p, lines
    n = len(xs)
    if n < 2:
        return list(xs), list(ys)
    try:
        import numpy as np

        dy = np.gradient(np.array(ys), np.array(xs)).tolist()
    except ImportError:
        dy = [0.0] * n
        for index in range(1, n - 1):
            dx = xs[index + 1] - xs[index - 1]
            dy[index] = (ys[index + 1] - ys[index - 1]) / dx if dx else 0.0
        dy[0] = (ys[1] - ys[0]) / (xs[1] - xs[0]) if xs[1] != xs[0] else 0.0
        dy[-1] = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2]) if xs[-1] != xs[-2] else 0.0
    return list(xs), dy


def _op_integral(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    del lines
    cumulative = bool(p.get("cumulative", True))
    n = len(xs)
    if n < 2:
        return list(xs), list(ys)
    try:
        import numpy as np
        from scipy.integrate import cumulative_trapezoid

        cum = cumulative_trapezoid(np.array(ys), np.array(xs), initial=0.0).tolist()
        return (list(xs), cum) if cumulative else (list(xs), [cum[-1]] * n)
    except ImportError:
        acc = 0.0
        result = [0.0]
        for index in range(1, n):
            acc += (ys[index] + ys[index - 1]) * (xs[index] - xs[index - 1]) / 2
            result.append(acc)
        return (list(xs), result) if cumulative else (list(xs), [result[-1]] * n)


def _op_transform(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    del lines
    x_expr = str(p.get("x_expr", "") or "").strip()
    y_expr = str(p.get("y_expr", "") or "").strip()
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
                return np.asarray(nx, dtype=float).tolist(), np.asarray(ny, dtype=float).tolist()
            except Exception:
                pass
        new_xs: List[float] = []
        new_ys: List[float] = []
        for x, y in zip(xs, ys):
            ctx = {"x": x, "y": y}
            nx = eval(x_expr, safe_globals, ctx) if x_expr else x  # noqa: S307
            ny = eval(y_expr, safe_globals, ctx) if y_expr else y  # noqa: S307
            new_xs.append(float(nx))
            new_ys.append(float(ny))
        return new_xs, new_ys
    except Exception:
        return list(xs), list(ys)


def _op_filter(xs: List[float], ys: List[float], p: dict, lines: Optional[List[PipelineLine]] = None) -> XY:
    del lines
    cutoff = float(p.get("cutoff", 0.1))
    order = int(p.get("order", 4))
    mode = p.get("mode", "low")
    cutoff_mode = str(p.get("cutoff_mode", "normalized") or "normalized").strip().lower()
    sample_rate = _resolve_sample_rate(xs, p)
    if cutoff_mode == "actual":
        if sample_rate is None or sample_rate <= 0:
            return list(xs), list(ys)
        nyquist = sample_rate / 2.0
        if nyquist <= 0:
            return list(xs), list(ys)
        cutoff = cutoff / nyquist
    cutoff = max(0.001, min(0.999, cutoff))
    try:
        import numpy as np
        from scipy.signal import butter, filtfilt

        btype = "high" if mode == "high" else "low"
        coeffs = butter(order, cutoff, btype=btype, analog=False)
        if coeffs is None or len(coeffs) < 2:
            return list(xs), list(ys)
        b, a = coeffs[0], coeffs[1]
        y_filt = filtfilt(b, a, np.array(ys)).tolist()
        return list(xs), y_filt
    except ImportError:
        return list(xs), list(ys)


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


def _resolve_sample_rate(xs: List[float], p: dict) -> Optional[float]:
    raw_sample_rate = p.get("sampling_rate")
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


_BUILTIN_PROCESSING_OPS = {
    "crop": _op_crop,
    "smooth": _op_smooth,
    "normalize": _op_normalize,
    "resample": _op_resample,
    "fft": _op_fft,
    "derivative": _op_derivative,
    "integral": _op_integral,
    "transform": _op_transform,
    "filter": _op_filter,
}


def register_extensions(registry) -> None:
    del registry
