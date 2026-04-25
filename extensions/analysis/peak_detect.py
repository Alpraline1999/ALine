from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.extension_api import AnalysisExtension, ExtensionConfigField
from processing.extension_tools import line_xy, primary_line


VERSION = "0.1.0"


def _filter_indices_by_x_distance(xs: List[float], ys: List[float], indices, min_distance_x: float, *, prefer: str) -> List[int]:
    if min_distance_x <= 0:
        return [int(index) for index in indices]
    ordered = [int(index) for index in indices]
    ranked = sorted(ordered, key=(lambda index: (ys[index], xs[index])) if prefer == "lower" else (lambda index: (-ys[index], xs[index])))
    kept: List[int] = []
    for index in ranked:
        x_value = xs[index]
        if all(abs(x_value - xs[kept_index]) >= min_distance_x for kept_index in kept):
            kept.append(index)
    return sorted(kept)


def detect_peaks(
    xs: List[float],
    ys: List[float],
    min_height: Optional[float] = None,
    min_distance: Optional[int] = 1,
    min_distance_x: Optional[float] = None,
    prominence: Optional[float] = None,
) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy.signal import find_peaks
    except ImportError:
        raise ImportError("需要 numpy 和 scipy")

    y = np.array(ys)
    kwargs: Dict[str, Any] = {}
    if min_distance is not None:
        kwargs["distance"] = max(1, int(min_distance))
    if min_height is not None:
        kwargs["height"] = min_height
    if prominence is not None:
        kwargs["prominence"] = prominence
    indices, _props = find_peaks(y, **kwargs)
    if min_distance_x is not None and min_distance_x > 0:
        indices = _filter_indices_by_x_distance(xs, ys, indices, min_distance_x, prefer="higher")
    peaks = [{"x": xs[index], "y": ys[index], "index": int(index)} for index in indices]
    return {"peaks": peaks, "count": len(peaks)}


def detect_valleys(
    xs: List[float],
    ys: List[float],
    min_depth: Optional[float] = None,
    min_distance: Optional[int] = 1,
    min_distance_x: Optional[float] = None,
    prominence: Optional[float] = None,
) -> Dict[str, Any]:
    try:
        import numpy as np
        from scipy.signal import find_peaks
    except ImportError:
        raise ImportError("需要 numpy 和 scipy")

    y = np.array(ys)
    kwargs: Dict[str, Any] = {}
    if min_distance is not None:
        kwargs["distance"] = max(1, int(min_distance))
    if min_depth is not None:
        kwargs["height"] = min_depth
    if prominence is not None:
        kwargs["prominence"] = prominence
    indices, _ = find_peaks(-y, **kwargs)
    if min_distance_x is not None and min_distance_x > 0:
        indices = _filter_indices_by_x_distance(xs, ys, indices, min_distance_x, prefer="lower")
    valleys = [{"x": xs[index], "y": ys[index], "index": int(index)} for index in indices]
    return {"valleys": valleys, "count": len(valleys)}


def _handler(lines, params):
    if not lines:
        raise ValueError("peak_detect 需要至少一条输入数据")
    xs, ys = line_xy(primary_line(lines))
    distance_mode = "x_distance" if params.get("min_distance_x") not in (None, "") else "points"
    distance_value = params.get("min_distance_x") if distance_mode == "x_distance" else params.get("min_distance", 1)
    result = detect_peaks(
        xs,
        ys,
        min_height=params.get("min_height"),
        min_distance=params.get("min_distance", 1),
        min_distance_x=params.get("min_distance_x"),
        prominence=params.get("prominence"),
    )
    valleys = detect_valleys(
        xs,
        ys,
        min_depth=params.get("min_depth"),
        min_distance=params.get("min_distance", 1),
        min_distance_x=params.get("min_distance_x"),
        prominence=params.get("prominence"),
    )
    result["valleys"] = valleys.get("valleys", [])
    result["valley_count"] = valleys.get("count", 0)
    result["analysis_type"] = "peak_detect"
    result["distance_mode"] = distance_mode
    result["distance_value"] = distance_value
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="peak_detect",
            name="峰值检测",
            handler=_handler,
            description="检测波峰与波谷，支持高度、间距和突出度约束。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(key="min_height", label="最小峰高", field_type="number", default=None),
                ExtensionConfigField(key="min_distance", label="最小点间距", field_type="integer", default=1, min_value=1),
                ExtensionConfigField(key="min_distance_x", label="最小 X 间距", field_type="number", default=None),
                ExtensionConfigField(key="min_depth", label="最小谷深", field_type="number", default=None),
                ExtensionConfigField(key="prominence", label="突出度", field_type="number", default=None),
            ],
        )
    )
