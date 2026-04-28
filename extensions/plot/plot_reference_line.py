from core.extension_api import ExtensionConfigField, PlotExtension, normalize_extension_lines_list
from extensions.processing.extension_tools import line_xy, series_payloads_to_lines


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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


def _theme_colors(plot_context, axis):
    foreground = str((plot_context.theme_colors or {}).get("foreground") or "#222222")
    background = str((plot_context.theme_colors or {}).get("background") or "#ffffff")
    if axis is not None:
        try:
            background = background or axis.get_facecolor()
        except Exception:
            pass
    return {"foreground": foreground, "background": background}


def draw_reference_overlay(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return

    points = _visible_points(plot_context, params)
    if not points:
        return

    label = str(params.get("label", "平均参考线"))
    offset = _as_float(params.get("offset", 0.0), 0.0)
    line_color = str(params.get("line_color", "#C23B22"))
    line_style = str(params.get("line_style", "--"))
    line_width = max(0.1, _as_float(params.get("line_width", 1.3), 1.3))
    line_alpha = min(1.0, max(0.0, _as_float(params.get("line_alpha", 0.85), 0.85)))
    band_color = str(params.get("band_color", line_color))
    band_alpha = min(1.0, max(0.0, _as_float(params.get("band_alpha", 0.12), 0.12)))
    band_half_width = max(0.0, _as_float(params.get("band_half_width", 0.0), 0.0))
    show_reference_line = bool(params.get("show_reference_line", True))
    show_band = bool(params.get("show_band", True))

    mean_level = sum(point[2] for point in points) / len(points) + offset

    if show_band and band_half_width > 0.0:
        axis.axhspan(mean_level - band_half_width, mean_level + band_half_width, color=band_color, alpha=band_alpha, zorder=0)
    if show_reference_line:
        axis.axhline(mean_level, color=line_color, linestyle=line_style, linewidth=line_width, alpha=line_alpha, label=label)

    precision = max(0, int(_as_float(params.get("annotation_precision", 3), 3)))
    if bool(params.get("annotate_peak", True)):
        peak_name, peak_x, peak_y = max(points, key=lambda item: item[2])
        marker_size = max(10.0, _as_float(params.get("marker_size", 42.0), 42.0))
        axis.scatter([peak_x], [peak_y], color=line_color, s=marker_size, zorder=6)
        theme_colors = _theme_colors(plot_context, axis)
        foreground = theme_colors["foreground"]
        background = theme_colors["background"]
        annotation_prefix = str(params.get("annotation_prefix", "峰值"))
        axis.annotate(
            f"{annotation_prefix}: {peak_name}\nY = {peak_y:.{precision}f}",
            xy=(peak_x, peak_y),
            xytext=(10, 12),
            textcoords="offset points",
            color=foreground,
            fontsize=max(8, int(_as_float(params.get("annotation_font_size", 9), 9))),
            bbox={"boxstyle": "round,pad=0.3", "fc": background, "ec": line_color, "alpha": 0.92},
            arrowprops={"arrowstyle": "->", "color": line_color, "linewidth": 1.0},
        )

    if bool(params.get("append_summary_to_title", True)):
        current_title = axis.get_title().strip()
        summary = f"{label} = {mean_level:.{precision}f}"
        axis.set_title(summary if not current_title else f"{current_title}\n{summary}")


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_reference_line",
            name="参考线标注",
            handler=draw_reference_overlay,
            description="按当前可见曲线生成均值参考线，并可在峰值处追加注释。",
            version="0.1.0",
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="show_reference_line", description="在 before_plot 阶段绘制一条水平参考线。", field_type="boolean", default=True),
                ExtensionConfigField(key="show_band", description="在参考线附近绘制一段半透明带状区域。", field_type="boolean", default=True),
                ExtensionConfigField(key="line_color", description="参考线和峰值标记使用的颜色。", field_type="color", default="#C23B22"),
                ExtensionConfigField(key="line_style", description="matplotlib 兼容的线型字符串。", field_type="selective", default="--", choices=("-", "--", "-.", ":")),
                ExtensionConfigField(key="line_width", description="参考线宽度。", field_type="number", default=1.3),
                ExtensionConfigField(key="line_alpha", description="参考线透明度。", field_type="limited", default=0.85, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="band_color", description="参考带颜色。", field_type="color", default="#F4B183"),
                ExtensionConfigField(key="band_half_width", description="以均值为中心，上下各扩展多少 Y 值。", field_type="number", default=0.15),
                ExtensionConfigField(key="band_alpha", description="参考带透明度。", field_type="limited", default=0.12, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="offset", description="在均值基础上额外增加的偏移量。", field_type="number", default=0.0),
                ExtensionConfigField(key="label", description="添加到图例中的名称。", field_type="string", default="平均参考线"),
                ExtensionConfigField(key="annotate_peak", description="在 after_plot 阶段标记最高点并附加注释。", field_type="boolean", default=True),
                ExtensionConfigField(key="marker_size", description="峰值标记点大小。", field_type="number", default=42.0),
                ExtensionConfigField(key="annotation_prefix", description="峰值注释前缀。", field_type="string", default="峰值"),
                ExtensionConfigField(key="annotation_precision", description="最高点注释中 Y 值的小数位数。", field_type="integer", default=3),
                ExtensionConfigField(key="annotation_font_size", description="峰值注释字号。", field_type="integer", default=9),
                ExtensionConfigField(key="append_summary_to_title", description="在标题末尾追加参考线数值摘要。", field_type="boolean", default=True),
            ],
        )
    )