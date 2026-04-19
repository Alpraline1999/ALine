"""PlotExtension 示例：演示上下文式 matplotlib 扩展的常见写法。"""

from core.extension_api import ExtensionConfigField, PlotExtension


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _visible_points(visible_series):
    points = []
    for item in visible_series:
        name = str(item.get("display_name") or item.get("name") or "未命名曲线")
        xs = list(item.get("x") or [])
        ys = list(item.get("y") or [])
        for x_value, y_value in zip(xs, ys):
            try:
                points.append((name, float(x_value), float(y_value)))
            except (TypeError, ValueError):
                continue
    return points


def draw_reference_overlay(plot_context, options):
    axis = plot_context.axis or (plot_context.axes[0] if plot_context.axes else None)
    if axis is None:
        return

    points = _visible_points(plot_context.visible_series)
    if not points:
        return

    label = str(options.get("label", "平均参考线"))
    offset = _as_float(options.get("offset", 0.0), 0.0)
    line_color = str(options.get("line_color", "#C23B22"))
    line_style = str(options.get("line_style", "--"))
    line_width = max(0.1, _as_float(options.get("line_width", 1.3), 1.3))
    line_alpha = min(1.0, max(0.0, _as_float(options.get("line_alpha", 0.85), 0.85)))
    band_color = str(options.get("band_color", line_color))
    band_alpha = min(1.0, max(0.0, _as_float(options.get("band_alpha", 0.12), 0.12)))
    band_half_width = max(0.0, _as_float(options.get("band_half_width", 0.0), 0.0))
    show_reference_line = bool(options.get("show_reference_line", True))
    show_band = bool(options.get("show_band", True))

    mean_level = sum(point[2] for point in points) / len(points) + offset

    if plot_context.phase == "before_plot":
        if show_band and band_half_width > 0.0:
            axis.axhspan(
                mean_level - band_half_width,
                mean_level + band_half_width,
                color=band_color,
                alpha=band_alpha,
                zorder=0,
            )
        if show_reference_line:
            axis.axhline(
                mean_level,
                color=line_color,
                linestyle=line_style,
                linewidth=line_width,
                alpha=line_alpha,
                label=label,
            )
        return

    if plot_context.phase != "after_plot":
        return

    precision = max(0, int(_as_float(options.get("annotation_precision", 3), 3)))
    if bool(options.get("annotate_peak", True)):
        peak_name, peak_x, peak_y = max(points, key=lambda item: item[2])
        marker_size = max(10.0, _as_float(options.get("marker_size", 42.0), 42.0))
        axis.scatter([peak_x], [peak_y], color=line_color, s=marker_size, zorder=6)
        foreground = str(plot_context.theme_colors.get("foreground", "#222222"))
        background = str(plot_context.theme_colors.get("background", "#ffffff"))
        annotation_prefix = str(options.get("annotation_prefix", "峰值"))
        axis.annotate(
            f"{annotation_prefix}: {peak_name}\nY = {peak_y:.{precision}f}",
            xy=(peak_x, peak_y),
            xytext=(10, 12),
            textcoords="offset points",
            color=foreground,
            fontsize=max(8, int(_as_float(options.get("annotation_font_size", 9), 9))),
            bbox={"boxstyle": "round,pad=0.3", "fc": background, "ec": line_color, "alpha": 0.92},
            arrowprops={"arrowstyle": "->", "color": line_color, "linewidth": 1.0},
        )

    if bool(options.get("append_summary_to_title", True)):
        current_title = axis.get_title().strip()
        summary = f"{label} = {mean_level:.{precision}f}"
        axis.set_title(summary if not current_title else f"{current_title}\n{summary}")


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="demo_plot_reference_line",
            name="示例·参考线与峰值标注",
            handler=draw_reference_overlay,
            description="演示 PlotExtensionContext 的 before_plot/after_plot 两阶段绘制能力。",
            default_options={
                "show_reference_line": True,
                "show_band": True,
                "line_color": "#C23B22",
                "line_style": "--",
                "line_width": 1.3,
                "line_alpha": 0.85,
                "band_color": "#F4B183",
                "band_alpha": 0.12,
                "band_half_width": 0.15,
                "offset": 0.0,
                "label": "平均参考线",
                "annotate_peak": True,
                "marker_size": 42.0,
                "annotation_prefix": "峰值",
                "annotation_precision": 3,
                "annotation_font_size": 9,
                "append_summary_to_title": True,
            },
            config_fields=[
                ExtensionConfigField(
                    key="show_reference_line",
                    description="在 before_plot 阶段绘制一条水平参考线。",
                    field_type="boolean",
                    default=True,
                ),
                ExtensionConfigField(
                    key="show_band",
                    description="在参考线附近绘制一段半透明带状区域。",
                    field_type="boolean",
                    default=True,
                ),
                ExtensionConfigField(
                    key="line_color",
                    description="参考线和峰值标记使用的颜色。",
                    field_type="string",
                    default="#C23B22",
                ),
                ExtensionConfigField(
                    key="line_style",
                    description="matplotlib 兼容的线型字符串。",
                    field_type="string",
                    default="--",
                ),
                ExtensionConfigField(
                    key="line_width",
                    description="参考线宽度。",
                    field_type="number",
                    default=1.3,
                ),
                ExtensionConfigField(
                    key="band_half_width",
                    description="以均值为中心，上下各扩展多少 Y 值。",
                    field_type="number",
                    default=0.15,
                ),
                ExtensionConfigField(
                    key="band_alpha",
                    description="参考带透明度。",
                    field_type="number",
                    default=0.12,
                ),
                ExtensionConfigField(
                    key="offset",
                    description="在均值基础上额外增加的偏移量。",
                    field_type="number",
                    default=0.0,
                ),
                ExtensionConfigField(
                    key="label",
                    description="添加到图例中的名称。",
                    field_type="string",
                    default="平均参考线",
                ),
                ExtensionConfigField(
                    key="annotate_peak",
                    description="在 after_plot 阶段标记最高点并附加注释。",
                    field_type="boolean",
                    default=True,
                ),
                ExtensionConfigField(
                    key="annotation_precision",
                    description="最高点注释中 Y 值的小数位数。",
                    field_type="integer",
                    default=3,
                ),
                ExtensionConfigField(
                    key="append_summary_to_title",
                    description="在标题末尾追加参考线数值摘要。",
                    field_type="boolean",
                    default=True,
                ),
            ],
        )
    )