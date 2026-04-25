from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


BUILTIN_EXTENSION_VERSION = "0.1.0"

SeriesInput = Dict[str, Any]
XY = Tuple[List[float], List[float]]


def normalize_series_inputs(raw: Any) -> List[SeriesInput]:
    normalized: List[SeriesInput] = []
    for index, item in enumerate(list(raw or [])):
        if isinstance(item, dict):
            payload = dict(item)
        else:
            payload = {
                "name": str(getattr(item, "name", f"line_{index + 1}") or f"line_{index + 1}"),
                "x": list(getattr(item, "x", []) or []),
                "y": list(getattr(item, "y", []) or []),
            }
        payload["name"] = str(payload.get("name", f"line_{index + 1}") or f"line_{index + 1}")
        payload["x"] = list(payload.get("x", []) or [])
        payload["y"] = list(payload.get("y", []) or [])
        normalized.append(payload)
    return normalized


def coerce_processing_handler_call(
    inputs_or_xs: Any,
    ys_or_params: Any = None,
    params: Optional[Dict[str, Any]] = None,
    *,
    lines: Optional[List[SeriesInput]] = None,
) -> Tuple[List[SeriesInput], Dict[str, Any]]:
    if params is None and isinstance(ys_or_params, dict):
        return normalize_series_inputs(inputs_or_xs), dict(ys_or_params or {})

    xs = list(inputs_or_xs or [])
    ys = list(ys_or_params or [])
    inputs = normalize_series_inputs(lines or [])
    if not inputs:
        inputs = [{"name": "", "x": xs, "y": ys}]
    else:
        inputs[0] = dict(inputs[0])
        inputs[0]["x"] = xs
        inputs[0]["y"] = ys
    return inputs, dict(params or {})


def primary_series_input(inputs: List[SeriesInput]) -> SeriesInput:
    normalized = normalize_series_inputs(inputs)
    if normalized:
        return normalized[0]
    return {"name": "", "x": [], "y": []}


def primary_series_xy(inputs: List[SeriesInput]) -> XY:
    primary = primary_series_input(inputs)
    return list(primary.get("x", []) or []), list(primary.get("y", []) or [])


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