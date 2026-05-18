from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION as VERSION, line_from_xy, line_xy, primary_line


from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION as VERSION


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
    width: Optional[int] = None,
    rel_height: Optional[float] = None,
) -> Dict[str, Any]:
    from scipy.signal import find_peaks

    y = np.array(ys)
    kwargs: Dict[str, Any] = {}
    if min_distance is not None:
        kwargs["distance"] = max(1, int(min_distance))
    if min_height is not None:
        kwargs["height"] = min_height
    if prominence is not None:
        kwargs["prominence"] = prominence
    if width is not None:
        kwargs["width"] = max(1, int(width))
    if rel_height is not None:
        kwargs["rel_height"] = rel_height
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
    width: Optional[int] = None,
    rel_height: Optional[float] = None,
) -> Dict[str, Any]:
    from scipy.signal import find_peaks

    y = np.array(ys)
    kwargs: Dict[str, Any] = {}
    if min_distance is not None:
        kwargs["distance"] = max(1, int(min_distance))
    if min_depth is not None:
        kwargs["height"] = min_depth
    if prominence is not None:
        kwargs["prominence"] = prominence
    if width is not None:
        kwargs["width"] = max(1, int(width))
    if rel_height is not None:
        kwargs["rel_height"] = rel_height
    indices, _ = find_peaks(-y, **kwargs)
    if min_distance_x is not None and min_distance_x > 0:
        indices = _filter_indices_by_x_distance(xs, ys, indices, min_distance_x, prefer="lower")
    valleys = [{"x": xs[index], "y": ys[index], "index": int(index)} for index in indices]
    return {"valleys": valleys, "count": len(valleys)}


def _handler(lines, params):
    if not lines:
        raise ValueError("peak_detect 需要至少一条输入数据")
    source_line = primary_line(lines)
    xs, ys = line_xy(source_line)
    distance_mode = "x_distance" if params.get("min_distance_x") not in (None, "") else "points"
    distance_value = params.get("min_distance_x") if distance_mode == "x_distance" else params.get("min_distance", 1)
    result = detect_peaks(
        xs,
        ys,
        min_height=params.get("min_height"),
        min_distance=params.get("min_distance", 1),
        min_distance_x=params.get("min_distance_x"),
        prominence=params.get("prominence"),
        width=params.get("width"),
        rel_height=params.get("rel_height"),
    )
    valleys = detect_valleys(
        xs,
        ys,
        min_depth=params.get("min_depth"),
        min_distance=params.get("min_distance", 1),
        min_distance_x=params.get("min_distance_x"),
        prominence=params.get("prominence"),
        width=params.get("width"),
        rel_height=params.get("rel_height"),
    )
    result["valleys"] = valleys.get("valleys", [])
    result["valley_count"] = valleys.get("count", 0)
    peak_points = result.get("peaks", []) or []
    valley_points = result.get("valleys", []) or []
    merged_points = [
        {"type": "波峰", "x": point.get("x"), "y": point.get("y")}
        for point in peak_points
    ] + [
        {"type": "波谷", "x": point.get("x"), "y": point.get("y")}
        for point in valley_points
    ]
    merged_points.sort(key=lambda item: (float("inf") if item.get("x") is None else item.get("x"), item.get("type") != "波峰"))
    result["summary_items"] = [
        {"label": "波峰数量", "value": result.get("count", 0)},
        {"label": "波谷数量", "value": result.get("valley_count", 0)},
    ]
    if distance_value not in (None, ""):
        result["summary_items"].append(
            {
                "label": "最小间距",
                "value": f"{distance_value}（{'X 值间距' if distance_mode == 'x_distance' else '采样点数'}）",
            }
        )
    if merged_points:
        rows = [
            [index + 1, item.get("type"), item.get("x"), item.get("y")]
            for index, item in enumerate(merged_points)
        ]
        result["table_sections"] = [
            {
                "title": "峰谷列表",
                "headers": ["序号", "类型", "X", "Y"],
                "rows": rows,
            }
        ]
    result_lines = []
    plot_series = [
        {
            "name": "原始数据",
            "line": source_line,
            "kind": "line",
            "color": "#0078D4",
            "line_width": 1.4,
        }
    ]
    if merged_points:
        merged_line_points = [
            (float(item["x"]), float(item["y"]))
            for item in merged_points
            if item.get("x") is not None and item.get("y") is not None
        ]
        result_lines.append(
            {
                "line_name": "峰谷点",
                "line": line_from_xy(
                    [point[0] for point in merged_line_points],
                    [point[1] for point in merged_line_points],
                ),
            }
        )
        plot_series.append(
            {
                "name": f"峰谷点 ({len(merged_line_points)}个)",
                "line": "峰谷点",
                "kind": "markers",
                "marker": "o",
                "size": 42,
                "color": "#605E5C",
            }
        )
    if peak_points:
        result_lines.append(
            {
                "line_name": "波峰点",
                "line": line_from_xy([point.get("x") for point in peak_points], [point.get("y") for point in peak_points]),
            }
        )
        plot_series.append(
            {
                "name": f"波峰 ({len(peak_points)}个)",
                "line": "波峰点",
                "kind": "markers",
                "marker": "^",
                "size": 50,
                "color": "#D13438",
            }
        )
    if valley_points:
        result_lines.append(
            {
                "line_name": "波谷点",
                "line": line_from_xy([point.get("x") for point in valley_points], [point.get("y") for point in valley_points]),
            }
        )
        plot_series.append(
            {
                "name": f"波谷 ({len(valley_points)}个)",
                "line": "波谷点",
                "kind": "markers",
                "marker": "v",
                "size": 50,
                "color": "#107C10",
            }
        )
    if result_lines:
        result["lines"] = result_lines
    if plot_series:
        result["_plot_series"] = plot_series
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
                ExtensionConfigField(key="min_distance", label="最小点间距", field_type="integer", default=1, min_value=1),
                ExtensionConfigField(key="min_distance_x", label="最小 X 间距", field_type="number", default=None),
                ExtensionConfigField(key="min_height", label="最小峰高", field_type="number", default=None),
                ExtensionConfigField(key="min_depth", label="最小谷深", field_type="number", default=None),
                ExtensionConfigField(key="prominence", label="突出度", field_type="number", default=None),
                ExtensionConfigField(key="width", label="最小峰宽（点数）", field_type="integer", default=None),
                ExtensionConfigField(key="rel_height", label="峰宽相对高度", field_type="number", default=0.5, min_value=0.0, max_value=1.0),
            ],
            tool_tier="tool",
            report_placeholders=[
                {"token": "{{peak_count}}", "label": "波峰数", "description": "检测到的波峰数量。"},
                {"token": "{{valley_count}}", "label": "波谷数", "description": "检测到的波谷数量。"},
            ],
        )
    )