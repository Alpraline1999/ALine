"""
数据处理引擎 — 非破坏性操作管道

每个操作用 dict 描述:
  {"type": "smooth",     "params": {"method": "savgol", "window": 11, "poly": 3}}
  {"type": "crop",       "params": {"x_min": 0.0, "x_max": 10.0}}
  {"type": "normalize",  "params": {"mode": "minmax"}}   # "minmax" | "zscore"
  {"type": "resample",   "params": {"n": 200}}
  {"type": "derivative", "params": {}}
  {"type": "integral",   "params": {"cumulative": True}}
  {"type": "transform",  "params": {"x_expr": "", "y_expr": "y * 1.0"}}
  {"type": "filter",     "params": {"cutoff": 0.1, "order": 4}}  # Butterworth lowpass

apply_pipeline(xs, ys, ops) → (xs_new, ys_new)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple


XY = Tuple[List[float], List[float]]


# ─────────────────────────────────────────────────────────────
# 公共入口
# ─────────────────────────────────────────────────────────────

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
    elif t == "smooth":
        return _op_smooth(xs, ys, p)
    elif t == "normalize":
        return _op_normalize(xs, ys, p)
    elif t == "resample":
        return _op_resample(xs, ys, p)
    elif t == "derivative":
        return _op_derivative(xs, ys, p)
    elif t == "integral":
        return _op_integral(xs, ys, p)
    elif t == "transform":
        return _op_transform(xs, ys, p)
    elif t == "filter":
        return _op_filter(xs, ys, p)
    return xs, ys


# ─────────────────────────────────────────────────────────────
# 操作实现
# ─────────────────────────────────────────────────────────────

def _op_crop(xs: List[float], ys: List[float], p: dict) -> XY:
    x_min = p.get("x_min", -math.inf)
    x_max = p.get("x_max",  math.inf)
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
    elif method == "moving_avg":
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
            ny = [(v - mn) / rng for v in ys]
        elif mode == "zscore":
            mean = sum(ys) / n
            std = math.sqrt(sum((v - mean) ** 2 for v in ys) / n) or 1.0
            ny = [(v - mean) / std for v in ys]
        else:
            ny = list(ys)
    return list(xs), ny


def _op_resample(xs: List[float], ys: List[float], p: dict) -> XY:
    n = int(p.get("n", 200))
    if len(xs) < 2:
        return xs, ys
    try:
        import numpy as np
        x_arr = np.array(xs, dtype=float)
        y_arr = np.array(ys, dtype=float)
        x_new = np.linspace(x_arr.min(), x_arr.max(), n)
        y_new = np.interp(x_new, x_arr, y_arr)
        return x_new.tolist(), y_new.tolist()
    except ImportError:
        # Pure Python linear interpolation
        def _lerp(xq):
            if xq <= xs[0]:
                return ys[0]
            if xq >= xs[-1]:
                return ys[-1]
            for i in range(len(xs) - 1):
                if xs[i] <= xq <= xs[i + 1]:
                    t = (xq - xs[i]) / (xs[i + 1] - xs[i])
                    return ys[i] + t * (ys[i + 1] - ys[i])
            return ys[-1]
        step = (xs[-1] - xs[0]) / (n - 1)
        x_new = [xs[0] + i * step for i in range(n)]
        return x_new, [_lerp(xi) for xi in x_new]


def _op_derivative(xs: List[float], ys: List[float], p: dict) -> XY:
    n = len(xs)
    if n < 2:
        return xs, ys
    try:
        import numpy as np
        dy = np.gradient(np.array(ys), np.array(xs)).tolist()
    except ImportError:
        dy = [0.0] * n
        for i in range(1, n - 1):
            dx = xs[i + 1] - xs[i - 1]
            dy[i] = (ys[i + 1] - ys[i - 1]) / dx if dx else 0.0
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
        # Trapezoidal rule
        acc = 0.0
        result = [0.0]
        for i in range(1, n):
            acc += (ys[i] + ys[i - 1]) * (xs[i] - xs[i - 1]) / 2
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
        safe_globals = {"__builtins__": {}, "math": _math, "abs": abs,
                        "min": min, "max": max, "round": round, "sqrt": _math.sqrt,
                        "log": _math.log, "log10": _math.log10, "exp": _math.exp,
                        "sin": _math.sin, "cos": _math.cos, "tan": _math.tan,
                        "pi": _math.pi, "e": _math.e}
        if np is not None:
            safe_globals["np"] = np
            # 向量化 eval：将 x/y 作为 numpy 数组一次性求值
            try:
                x_arr = np.asarray(xs, dtype=float)
                y_arr = np.asarray(ys, dtype=float)
                ctx = {"x": x_arr, "y": y_arr}
                # 添加 numpy ufunc 到安全上下文
                for fn in ("sqrt", "log", "log10", "exp", "sin", "cos", "tan", "abs"):
                    safe_globals[fn] = getattr(np, fn)
                nx = eval(x_expr, safe_globals, ctx) if x_expr else x_arr  # noqa: S307
                ny = eval(y_expr, safe_globals, ctx) if y_expr else y_arr  # noqa: S307
                return np.asarray(nx, dtype=float).tolist(), np.asarray(ny, dtype=float).tolist()
            except Exception:
                pass  # 向量化失败，回退逐点模式
        # 逐点回退
        new_xs, new_ys = [], []
        for x, y in zip(xs, ys):
            ctx = {"x": x, "y": y}
            nx = eval(x_expr, safe_globals, ctx) if x_expr else x   # noqa: S307
            ny = eval(y_expr, safe_globals, ctx) if y_expr else y   # noqa: S307
            new_xs.append(float(nx))
            new_ys.append(float(ny))
        return new_xs, new_ys
    except Exception:
        return list(xs), list(ys)


def _op_filter(xs: List[float], ys: List[float], p: dict) -> XY:
    cutoff = float(p.get("cutoff", 0.1))
    order = int(p.get("order", 4))
    try:
        import numpy as np
        from scipy.signal import butter, filtfilt
        b, a = butter(order, cutoff, btype="low", analog=False)
        y_filt = filtfilt(b, a, np.array(ys)).tolist()
        return list(xs), y_filt
    except ImportError:
        return list(xs), list(ys)
