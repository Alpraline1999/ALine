from core.extension_api import ExtensionConfigField, PlotExtension


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value, default):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _clamp(value, minimum, maximum, default):
    number = _as_float(value, default)
    return max(minimum, min(maximum, number))


def apply_science_style(plot_context, options):
    if plot_context.phase != "before_plot":
        return

    x_label = str(options.get("x_label", "")).strip()
    y_label = str(options.get("y_label", "")).strip()
    axis_label_size = max(1, _as_int(options.get("axis_label_size", 11), 11))
    tick_label_size = max(1, _as_int(options.get("tick_label_size", 10), 10))
    legend_font_size = max(1, _as_int(options.get("legend_font_size", 9), 9))
    line_width = max(0.1, _as_float(options.get("line_width", 1.6), 1.6))
    marker_size = max(0.1, _as_float(options.get("marker_size", 4.8), 4.8))
    grid_alpha = _clamp(options.get("grid_alpha", 0.18), 0.0, 1.0, 0.18)
    grid_line_width = max(0.1, _as_float(options.get("grid_line_width", 0.8), 0.8))
    spine_width = max(0.1, _as_float(options.get("spine_width", 1.0), 1.0))

    figure_patch = {
        "font_size": axis_label_size,
        "legend_font_size": legend_font_size,
        "line_width": line_width,
        "marker_size": marker_size,
        "grid": bool(options.get("show_grid", False)),
        "grid_alpha": grid_alpha,
        "grid_line_width": grid_line_width,
        "legend_pos": str(options.get("legend_location", "best") or "best"),
    }
    if x_label:
        figure_patch["x_label"] = x_label
    if y_label:
        figure_patch["y_label"] = y_label
    plot_context.patch_figure_state(figure_patch)

    legend_kwargs = {
        "frameon": bool(options.get("legend_frame", False)),
    }
    if legend_kwargs["frameon"]:
        legend_kwargs["framealpha"] = _clamp(options.get("legend_frame_alpha", 1.0), 0.0, 1.0, 1.0)
        legend_kwargs["edgecolor"] = str(options.get("legend_edge_color", "#222222"))

    plot_context.patch_plot_style(
        {
            "figure_facecolor": "#ffffff",
            "axes_facecolor": "#ffffff",
            "spine_width": spine_width,
            "tick_params": {
                "direction": str(options.get("tick_direction", "in") or "in"),
                "length": max(0.0, _as_float(options.get("tick_length", 4.0), 4.0)),
                "width": max(0.1, _as_float(options.get("tick_width", 1.0), 1.0)),
                "top": bool(options.get("show_top_ticks", True)),
                "right": bool(options.get("show_right_ticks", True)),
                "labelsize": tick_label_size,
            },
            "legend_kwargs": legend_kwargs,
        }
    )


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="demo_plot_science_style",
            name="Science 图幅样式",
            handler=apply_science_style,
            description="用最小覆盖方式套用论文风格图幅，包括坐标轴标签、刻度样式和图例边框。",
            default_options={
                "x_label": "",
                "y_label": "",
                "axis_label_size": 11,
                "tick_label_size": 10,
                "legend_font_size": 9,
                "legend_location": "best",
                "legend_frame": False,
                "legend_frame_alpha": 1.0,
                "legend_edge_color": "#222222",
                "tick_direction": "in",
                "tick_length": 4.0,
                "tick_width": 1.0,
                "show_top_ticks": True,
                "show_right_ticks": True,
                "show_grid": False,
                "grid_alpha": 0.18,
                "grid_line_width": 0.8,
                "line_width": 1.6,
                "marker_size": 4.8,
                "spine_width": 1.0,
            },
            config_fields=[
                ExtensionConfigField(key="x_label", description="X 轴标签；留空则保持当前设置。", field_type="string", default=""),
                ExtensionConfigField(key="y_label", description="Y 轴标签；留空则保持当前设置。", field_type="string", default=""),
                ExtensionConfigField(key="axis_label_size", description="坐标轴标签字号。", field_type="integer", default=11),
                ExtensionConfigField(key="tick_label_size", description="坐标轴刻度字号。", field_type="integer", default=10),
                ExtensionConfigField(key="tick_direction", description="刻度朝向。", field_type="string", default="in", choices=("in", "out", "inout")),
                ExtensionConfigField(key="tick_length", description="刻度长度。", field_type="number", default=4.0),
                ExtensionConfigField(key="tick_width", description="刻度线宽。", field_type="number", default=1.0),
                ExtensionConfigField(key="show_top_ticks", description="是否显示顶部刻度。", field_type="boolean", default=True),
                ExtensionConfigField(key="show_right_ticks", description="是否显示右侧刻度。", field_type="boolean", default=True),
                ExtensionConfigField(key="legend_font_size", description="图例字号。", field_type="integer", default=9),
                ExtensionConfigField(key="legend_location", description="图例位置。", field_type="string", default="best", choices=("best", "upper right", "upper left", "lower right", "lower left", "center right", "center left", "upper center", "lower center")),
                ExtensionConfigField(key="legend_frame", description="是否显示图例边框。", field_type="boolean", default=False),
                ExtensionConfigField(key="legend_frame_alpha", description="图例边框透明度。", field_type="number", default=1.0),
                ExtensionConfigField(key="show_grid", description="是否显示细网格。", field_type="boolean", default=False),
                ExtensionConfigField(key="line_width", description="默认曲线线宽。", field_type="number", default=1.6),
                ExtensionConfigField(key="marker_size", description="默认标记尺寸。", field_type="number", default=4.8),
            ],
        )
    )