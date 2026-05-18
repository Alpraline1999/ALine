from __future__ import annotations

from core.extension_api import ExtensionConfigField, PlotExtension, normalize_extension_lines_list
from extensions.processing.extension_tools import line_xy, series_payloads_to_lines


VERSION = "0.1.0"


def _context_series(plot_context, params):
    base_series = list(plot_context.visible_series or plot_context.plotted_series or [])
    requested = normalize_extension_lines_list(params.get("lines_list")) if "lines_list" in params else []
    if requested:
        return [base_series[index - 1] for index in requested if 1 <= index <= len(base_series)]

    ordered = []
    if isinstance(plot_context.selected_series, dict):
        ordered.append(plot_context.selected_series)
    for item in base_series:
        if isinstance(plot_context.selected_series, dict) and item is plot_context.selected_series:
            continue
        ordered.append(item)
    return ordered


def _visible_points(plot_context, params):
    points = []
    for index, line in enumerate(series_payloads_to_lines(_context_series(plot_context, params)), start=1):
        xs, ys = line_xy(line)
        for x_value, y_value in zip(xs, ys):
            points.append((f"line_{index}", float(x_value), float(y_value)))
    return points


def plot_interface_contract(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return None

    points = _visible_points(plot_context, params)
    color = str(params.get("color", "#0078D4") or "#0078D4")
    alpha = max(0.0, min(1.0, float(params.get("alpha", 0.9) or 0.9)))
    label = str(params.get("label", "接口示例绘图") or "接口示例绘图")
    show_centroid = bool(params.get("show_centroid", True))
    marker = str(params.get("marker", "o") or "o")
    size = max(1.0, float(params.get("marker_size", 36.0) or 36.0))

    if show_centroid and points:
        center_x = sum(point[1] for point in points) / len(points)
        center_y = sum(point[2] for point in points) / len(points)
        axis.scatter([center_x], [center_y], s=size, marker=marker, color=color, alpha=alpha, label=label, zorder=8)
        axis.annotate(label, xy=(center_x, center_y), xytext=(8, 8), textcoords="offset points", color=color)
    axis.grid(bool(params.get("show_grid", True)))
    return None


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="interface_contract_plot",
            name="接口示例：绘图扩展",
            handler=plot_interface_contract,
            description="展示绘图扩展的强制签名 (plot_context, params) -> None，只操作当前 matplotlib 图元。",
            version=VERSION,
            lines_number=(1, -1),
            phases=("after_plot",),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            hidden=True,
            config_fields=[
                ExtensionConfigField(key="label", label="标注文本", description="string 参数示例。", field_type="string", default="接口示例绘图"),
                ExtensionConfigField(key="color", label="标注颜色", description="color 参数示例。", field_type="color", default="#0078D4"),
                ExtensionConfigField(key="marker", label="点形状", description="selective 参数示例。", field_type="selective", default="o", choices=("o", "s", "^", "D")),
                ExtensionConfigField(key="marker_size", label="点大小", description="number 参数示例。", field_type="number", default=36.0, min_value=1.0, step=1.0),
                ExtensionConfigField(key="alpha", label="透明度", description="limited 参数示例。", field_type="limited", default=0.9, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="show_centroid", label="显示中心点", description="boolean 参数示例。", field_type="boolean", default=True),
                ExtensionConfigField(key="show_grid", label="显示网格", description="boolean 参数示例。", field_type="boolean", default=True),
            ],
        )
    )
