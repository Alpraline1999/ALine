from core.extension_api import ExtensionConfigField, PlotExtension


_NAMED_SIZES = {
    "xx-small": 6.0,
    "x-small": 7.0,
    "small": 8.0,
    "medium": 10.0,
    "large": 12.0,
    "x-large": 14.0,
    "xx-large": 16.0,
}


def _named_size(value):
    text = str(value or "").strip().lower()
    return _NAMED_SIZES.get(text)


def _as_float(value, default):
    named = _named_size(value)
    if named is not None:
        return named
    try:
        return float(value)
    except (TypeError, ValueError):
        named_default = _named_size(default)
        if named_default is not None:
            return named_default
        return float(default)


def _as_int(value, default):
    return int(round(_as_float(value, default)))


def _clamp(value, minimum, maximum, default):
    number = _as_float(value, default)
    return max(minimum, min(maximum, number))


def _science_style_rcparams():
    import matplotlib.pyplot as plt
    import scienceplots  # noqa: F401

    original = plt.rcParams.copy()
    try:
        plt.style.use("science")
        plt.rcParams["text.usetex"] = False
        return dict(plt.rcParams)
    finally:
        plt.rcParams.update(original)


def _apply_legend(axis, legend_location, legend_font_size, legend_frame, legend_frame_alpha, legend_edge_color):
    handles, labels = axis.get_legend_handles_labels()
    if not handles:
        return
    legend = axis.legend(
        handles,
        labels,
        loc=legend_location,
        frameon=legend_frame,
        framealpha=legend_frame_alpha,
        edgecolor=legend_edge_color,
        fontsize=legend_font_size,
    )
    for text in legend.get_texts():
        text.set_fontsize(legend_font_size)


def apply_science_style(plot_context, params):
    figure = plot_context.figure
    axis = plot_context.axis
    if figure is None or axis is None:
        return

    rc_params = _science_style_rcparams()

    x_label = str(params.get("x_label", "")).strip()
    y_label = str(params.get("y_label", "")).strip()
    axis_label_size = max(1, _as_int(params.get("axis_label_size", rc_params.get("axes.labelsize", 11)), rc_params.get("axes.labelsize", 11)))
    tick_label_size = max(1, _as_int(params.get("tick_label_size", rc_params.get("xtick.labelsize", 10)), rc_params.get("xtick.labelsize", 10)))
    legend_font_size = max(1, _as_int(params.get("legend_font_size", rc_params.get("legend.fontsize", 9)), rc_params.get("legend.fontsize", 9)))
    line_width = max(0.1, _as_float(params.get("line_width", rc_params.get("lines.linewidth", 1.6)), rc_params.get("lines.linewidth", 1.6)))
    marker_size = max(0.1, _as_float(params.get("marker_size", rc_params.get("lines.markersize", 4.8)), rc_params.get("lines.markersize", 4.8)))
    grid_alpha = _clamp(params.get("grid_alpha", rc_params.get("grid.alpha", 0.18)), 0.0, 1.0, rc_params.get("grid.alpha", 0.18))
    grid_line_width = max(0.1, _as_float(params.get("grid_line_width", rc_params.get("grid.linewidth", 0.8)), rc_params.get("grid.linewidth", 0.8)))
    spine_width = max(0.1, _as_float(params.get("spine_width", rc_params.get("axes.linewidth", 1.0)), rc_params.get("axes.linewidth", 1.0)))
    show_grid = bool(params.get("show_grid", rc_params.get("axes.grid", False)))
    legend_location = str(params.get("legend_location", rc_params.get("legend.loc", "best")) or "best")
    legend_frame = bool(params.get("legend_frame", rc_params.get("legend.frameon", False)))
    legend_frame_alpha = _clamp(params.get("legend_frame_alpha", rc_params.get("legend.framealpha", 1.0)), 0.0, 1.0, rc_params.get("legend.framealpha", 1.0))
    legend_edge_color = str(params.get("legend_edge_color", "#222222"))

    figure.set_facecolor(str(rc_params.get("figure.facecolor", "#ffffff")))
    for current in list(getattr(figure, "axes", []) or [axis]):
        current.set_facecolor(str(rc_params.get("axes.facecolor", "#ffffff")))
        if x_label:
            current.set_xlabel(x_label, fontsize=axis_label_size)
        elif current.get_xlabel():
            current.xaxis.label.set_size(axis_label_size)
        if y_label:
            current.set_ylabel(y_label, fontsize=axis_label_size)
        elif current.get_ylabel():
            current.yaxis.label.set_size(axis_label_size)
        current.tick_params(
            direction=str(params.get("tick_direction", rc_params.get("xtick.direction", "in")) or "in"),
            length=max(0.0, _as_float(params.get("tick_length", rc_params.get("xtick.major.size", 4.0)), rc_params.get("xtick.major.size", 4.0))),
            width=max(0.1, _as_float(params.get("tick_width", rc_params.get("xtick.major.width", 1.0)), rc_params.get("xtick.major.width", 1.0))),
            top=bool(params.get("show_top_ticks", rc_params.get("xtick.top", True))),
            right=bool(params.get("show_right_ticks", rc_params.get("ytick.right", True))),
            labelsize=tick_label_size,
        )
        current.grid(show_grid, alpha=grid_alpha, linewidth=grid_line_width)
        for spine in current.spines.values():
            spine.set_linewidth(spine_width)
        for line in list(getattr(current, "lines", []) or []):
            line.set_linewidth(line_width)
            if str(line.get_marker() or ""):
                line.set_markersize(marker_size)
        _apply_legend(current, legend_location, legend_font_size, legend_frame, legend_frame_alpha, legend_edge_color)


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_science_style",
            name="Science 图幅样式",
            handler=apply_science_style,
            description="套用 scienceplots 论文风格，并叠加当前图幅的少量覆盖设置。",
            version="0.1.0",
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="x_label", description="X 轴标签；留空则保持当前设置。", field_type="string", default=""),
                ExtensionConfigField(key="y_label", description="Y 轴标签；留空则保持当前设置。", field_type="string", default=""),
                ExtensionConfigField(key="axis_label_size", description="坐标轴标签字号。", field_type="integer", default=11),
                ExtensionConfigField(key="tick_label_size", description="坐标轴刻度字号。", field_type="integer", default=10),
                ExtensionConfigField(key="tick_direction", description="刻度朝向。", field_type="selective", default="in", choices=("in", "out", "inout")),
                ExtensionConfigField(key="tick_length", description="刻度长度。", field_type="number", default=4.0),
                ExtensionConfigField(key="tick_width", description="刻度线宽。", field_type="number", default=1.0),
                ExtensionConfigField(key="show_top_ticks", description="是否显示顶部刻度。", field_type="boolean", default=True),
                ExtensionConfigField(key="show_right_ticks", description="是否显示右侧刻度。", field_type="boolean", default=True),
                ExtensionConfigField(key="legend_font_size", description="图例字号。", field_type="integer", default=9),
                ExtensionConfigField(key="legend_location", description="图例位置。", field_type="selective", default="best", choices=("best", "upper right", "upper left", "lower right", "lower left", "center right", "center left", "upper center", "lower center")),
                ExtensionConfigField(key="legend_frame", description="是否显示图例边框。", field_type="boolean", default=False),
                ExtensionConfigField(key="legend_frame_alpha", description="图例边框透明度。", field_type="limited", default=1.0, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="legend_edge_color", description="图例边框颜色。", field_type="color", default="#222222"),
                ExtensionConfigField(key="show_grid", description="是否显示细网格。", field_type="boolean", default=False),
                ExtensionConfigField(key="grid_alpha", description="网格透明度。", field_type="limited", default=0.18, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="grid_line_width", description="网格线宽。", field_type="number", default=0.8),
                ExtensionConfigField(key="line_width", description="默认曲线线宽。", field_type="number", default=1.6),
                ExtensionConfigField(key="marker_size", description="默认标记尺寸。", field_type="number", default=4.8),
                ExtensionConfigField(key="spine_width", description="坐标轴边框线宽。", field_type="number", default=1.0),
            ],
        )
    )