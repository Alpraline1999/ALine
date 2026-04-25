from __future__ import annotations

from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
from matplotlib.colors import to_hex

from processing.extension_tools import line_xy, normalize_lines


def current_figure():
    try:
        return plt.gcf()
    except Exception:
        return None


def current_axis():
    figure = current_figure()
    if figure is None:
        return None
    axes = list(getattr(figure, "axes", []) or [])
    if not axes:
        return None
    try:
        return plt.gca()
    except Exception:
        return axes[0]


def current_theme_colors(axis: Any = None) -> Dict[str, str]:
    target = axis or current_axis()
    if target is None:
        return {"foreground": "#222222", "background": "#ffffff"}

    foreground = "#222222"
    for getter in (
        getattr(getattr(target, "xaxis", None), "label", None),
        getattr(getattr(target, "yaxis", None), "label", None),
    ):
        if getter is None or not hasattr(getter, "get_color"):
            continue
        value = getter.get_color()
        if isinstance(value, str) and value.strip():
            foreground = value
            break

    try:
        background = to_hex(target.get_facecolor(), keep_alpha=False)
    except Exception:
        background = "#ffffff"
    return {"foreground": str(foreground or "#222222"), "background": str(background or "#ffffff")}


def visible_points(lines: Any) -> List[Tuple[str, float, float]]:
    points: List[Tuple[str, float, float]] = []
    for index, line in enumerate(normalize_lines(lines), start=1):
        xs, ys = line_xy(line)
        for x_value, y_value in zip(xs, ys):
            try:
                points.append((f"line_{index}", float(x_value), float(y_value)))
            except (TypeError, ValueError):
                continue
    return points


def axis_line_style(axis: Any) -> Dict[str, Any]:
    if axis is None or not list(getattr(axis, "lines", []) or []):
        return {}
    line = list(axis.lines)[0]
    return {
        "color": line.get_color(),
        "linewidth": float(line.get_linewidth()),
        "marker": str(line.get_marker() or ""),
        "markersize": float(line.get_markersize()),
    }