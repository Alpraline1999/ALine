"""
数据处理引擎 — 非破坏性操作管道

每个操作用 dict 描述:
  {"type": "smooth",     "params": {"method": "savgol", "window": 11, "poly": 3}}
  {"type": "crop",       "params": {"x_min": 0.0, "x_max": 10.0}}
  {"type": "normalize",  "params": {"mode": "minmax"}}   # "minmax" | "zscore"
  {"type": "resample",   "params": {"n": 200}}
  {"type": "fft",        "params": {"output": "amplitude", "detrend": True}}
  {"type": "derivative", "params": {}}
  {"type": "integral",   "params": {"cumulative": True}}
  {"type": "transform",  "params": {"x_expr": "", "y_expr": "y * 1.0"}}
  {"type": "filter",     "params": {"cutoff": 0.1, "order": 4, "mode": "low"}}  # Butterworth low/high pass

apply_pipeline(xs, ys, ops) → (xs_new, ys_new)
"""
from __future__ import annotations

import cmath
import math
from typing import Any, Dict, List, Optional, Tuple

from core.extension_api import extension_registry


XY = Tuple[List[float], List[float]]


def apply_pipeline(xs: List[float], ys: List[float], ops: List[Dict[str, Any]]) -> XY:
    """按顺序执行操作列表，返回新的 (xs, ys)；原始数据不变。"""
    x, y = list(xs), list(ys)
    for op in ops:
        x, y = apply_operation(x, y, op)
    return x, y


def apply_operation(xs: List[float], ys: List[float], op: Dict[str, Any]) -> XY:
    t = op.get("type", "")
    p = op.get("params", {})
    if t == "crop":
        return _op_crop(xs, ys, p)
    if t == "smooth":
        return _op_smooth(xs, ys, p)
    if t == "normalize":
        return _op_normalize(xs, ys, p)
    if t == "resample":
        return _op_resample(xs, ys, p)
    if t == "fft":
        return _op_fft(xs, ys, p)
    if t == "derivative":
        return _op_derivative(xs, ys, p)
    if t == "integral":
        return _op_integral(xs, ys, p)
    if t == "transform":
        return _op_transform(xs, ys, p)
    if t == "filter":
        return _op_filter(xs, ys, p)
    custom_op = extension_registry.get_processing(t)
    if custom_op is not None:
        return custom_op.handler(list(xs), list(ys), dict(p))
    return xs, ys


def _op_crop(xs: List[float], ys: List[float], p: dict) -> XY:
    x_min = p.get("x_min", -math.inf)
    x_max = p.get("x_max", math.inf)
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


def _op_smooth(xs: List[float], ys: List[float], p: dict) -> XY:
    method = p.get("method", "savgol")
    if method == "savgol":
        window = int(p.get("window", 11))
        poly = int(p.get("poly", 3))
        from processing.smoother import smooth_savgol

        return smooth_savgol(xs, ys, window, poly)
    if method == "moving_avg":
        window = int(p.get("window", 5))
        from processing.smoother import smooth_moving_average

        return smooth_moving_average(xs, ys, window)
    return list(xs), list(ys)


def _op_normalize(xs: List[float], ys: List[float], p: dict) -> XY:
    mode = p.get("mode", "minmax")
    if not ys:
        return xs, ys
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


def _op_resample(xs: List[float], ys: List[float], p: dict) -> XY:
    from processing.smoother import resample_uniform, resample_uniform_spacing

    x_sorted, y_sorted = _sorted_unique_xy(xs, ys)
    if len(x_sorted) < 2:
        return list(xs), list(ys)

    mode = str(p.get("mode", "count") or "count").strip().lower()
    if mode == "spacing":
        spacing = float(p.get("step", p.get("spacing", 0.0)) or 0.0)
        if spacing <= 0:
            return x_sorted, y_sorted
        return resample_uniform_spacing(x_sorted, y_sorted, spacing)

    n = max(2, int(p.get("n", 200)))
    return resample_uniform(x_sorted, y_sorted, n)


def _op_fft(xs: List[float], ys: List[float], p: dict) -> XY:
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
        freq = []
        values = []
        for k in range(half + 1):
            total = 0j
            for index, sample in enumerate(sig):
                total += sample * cmath.exp(-2j * math.pi * k * index / n)
            amp = abs(total) / max(1, n)
            freq.append(k / (n * step))
            values.append(amp * amp if output == "power" else amp)
        return freq, values


def _op_derivative(xs: List[float], ys: List[float], p: dict) -> XY:
    n = len(xs)
    if n < 2:
        return xs, ys
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


def _op_integral(xs: List[float], ys: List[float], p: dict) -> XY:
    cumulative = p.get("cumulative", True)
    n = len(xs)
    if n < 2:
        return xs, ys
    try:
        import numpy as np
        from scipy.integrate import cumulative_trapezoid

        cum = cumulative_trapezoid(np.array(ys), np.array(xs), initial=0.0).tolist()
        if not cumulative:
            return list(xs), [cum[-1]] * n
        return list(xs), cum
    except ImportError:
        acc = 0.0
        result = [0.0]
        for index in range(1, n):
            acc += (ys[index] + ys[index - 1]) * (xs[index] - xs[index - 1]) / 2
            result.append(acc)
        if not cumulative:
            return list(xs), [result[-1]] * n
        return list(xs), result


def _op_transform(xs: List[float], ys: List[float], p: dict) -> XY:
    x_expr = p.get("x_expr", "").strip()
    y_expr = p.get("y_expr", "").strip()
    try:
        import math as _math

        try:
            import numpy as np
        except ImportError:
            np = None
        safe_globals = {
            "__builtins__": {}, "math": _math, "abs": abs,
            "min": min, "max": max, "round": round, "sqrt": _math.sqrt,
            "log": _math.log, "log10": _math.log10, "exp": _math.exp,
            "sin": _math.sin, "cos": _math.cos, "tan": _math.tan,
            "pi": _math.pi, "e": _math.e,
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
        new_xs, new_ys = [], []
        for x, y in zip(xs, ys):
            ctx = {"x": x, "y": y}
            nx = eval(x_expr, safe_globals, ctx) if x_expr else x  # noqa: S307
            ny = eval(y_expr, safe_globals, ctx) if y_expr else y  # noqa: S307
            new_xs.append(float(nx))
            new_ys.append(float(ny))
        return new_xs, new_ys
    except Exception:
        return list(xs), list(ys)


def _op_filter(xs: List[float], ys: List[float], p: dict) -> XY:
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
