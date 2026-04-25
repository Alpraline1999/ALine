import math

from core.extension_api import ExtensionConfigField, PlotExtension


def _as_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _context_target_series(plot_context):
    if plot_context.selected_series is not None:
        return plot_context.selected_series
    if plot_context.visible_series:
        return plot_context.visible_series[0]
    return None


def _theta_values(xs, theta_unit):
    values = []
    for raw in xs:
        angle = _as_float(raw)
        if angle is None:
            continue
        values.append(math.radians(angle) if theta_unit == "degree" else angle)
    return values


def draw_polar_projection(plot_context, options):
    if plot_context.phase == "before_plot":
        theta_label = str(options.get("theta_label", "")).strip()
        radius_label = str(options.get("radius_label", "")).strip()
        figure_patch = {}
        if theta_label:
            figure_patch["x_label"] = theta_label
        if radius_label:
            figure_patch["y_label"] = radius_label
        if figure_patch:
            plot_context.patch_figure_state(figure_patch)

        plot_context.skip_default_plot = True
        plot_context.skip_default_formatting = True
        plot_context.figure.clear()
        axis = plot_context.figure.add_subplot(111, projection="polar")
        plot_context.set_active_axis(axis)
        plot_context.refresh_axes()
        return

    if plot_context.phase != "after_plot":
        return

    axis = plot_context.axis or (plot_context.axes[0] if plot_context.axes else None)
    if axis is None:
        return

    series = _context_target_series(plot_context)
    if series is None:
        return

    theta_unit = str(options.get("theta_unit", "degree") or "degree").strip().lower()
    theta_values = _theta_values(series.get("x", []), theta_unit)
    radius_values = []
    for raw in series.get("y", []):
        radius = _as_float(raw)
        if radius is None:
            continue
        radius_values.append(radius)

    point_count = min(len(theta_values), len(radius_values))
    theta_values = theta_values[:point_count]
    radius_values = radius_values[:point_count]
    if not theta_values or not radius_values:
        return

    if bool(options.get("close_curve", False)) and point_count > 1:
        theta_values.append(theta_values[0])
        radius_values.append(radius_values[0])

    axis.set_theta_zero_location(str(options.get("zero_location", "N") or "N"))
    axis.set_theta_direction(-1 if str(options.get("direction", "counterclockwise")) == "clockwise" else 1)

    theta_min = _as_float(options.get("theta_min"))
    theta_max = _as_float(options.get("theta_max"))
    if theta_min is not None:
        axis.set_thetamin(theta_min)
    if theta_max is not None:
        axis.set_thetamax(theta_max)

    r_min = _as_float(options.get("r_min"))
    r_max = _as_float(options.get("r_max"))
    if r_min is not None or r_max is not None:
        axis.set_rlim(bottom=r_min, top=r_max)

    style = dict(series.get("style") or {})
    figure_state = dict(plot_context.figure_state or {})
    color = str(options.get("color", "") or style.get("color") or series.get("color") or "#0078D4")
    marker = str(options.get("marker", "") or style.get("marker") or "")
    line_width = _as_float(options.get("line_width"), None)
    if line_width is None:
        line_width = _as_float(style.get("linewidth"), _as_float(figure_state.get("line_width"), 1.5)) or 1.5
    marker_size = _as_float(options.get("marker_size"), None)
    if marker_size is None:
        marker_size = _as_float(style.get("marker_size"), _as_float(figure_state.get("marker_size"), 5.0)) or 5.0
    alpha = max(0.0, min(1.0, _as_float(options.get("alpha"), 0.95) or 0.95))
    fill_alpha = max(0.0, min(1.0, _as_float(options.get("fill_alpha"), 0.0) or 0.0))
    label = str(options.get("label", "")).strip() or str(series.get("display_name") or series.get("name") or "极坐标曲线")

    plot_kwargs = {
        "color": color,
        "linewidth": max(0.1, line_width),
        "alpha": alpha,
        "label": label,
    }
    if marker:
        plot_kwargs["marker"] = marker
        plot_kwargs["markersize"] = max(0.1, marker_size)

    axis.plot(theta_values, radius_values, **plot_kwargs)
    if fill_alpha > 0.0 and len(theta_values) >= 3:
        axis.fill(theta_values, radius_values, color=color, alpha=fill_alpha)

    axis.grid(bool(options.get("show_grid", True)))
    title = str(options.get("title", "")).strip()
    if title:
        axis.set_title(title)
    axis.set_xlabel(str(figure_state.get("x_label") or "角度"))
    axis.set_ylabel(str(figure_state.get("y_label") or "半径"))

    radial_label_angle = _as_float(options.get("radial_label_angle"))
    if radial_label_angle is not None:
        axis.set_rlabel_position(radial_label_angle)

    if bool(options.get("show_legend", True)):
        legend_kwargs = {
            "loc": str(figure_state.get("legend_pos") or "best"),
            "frameon": bool(options.get("legend_frame", False)),
        }
        font_family = str(figure_state.get("font_family") or "").strip()
        legend_font_size = max(1, int(_as_float(figure_state.get("legend_font_size"), 9) or 9))
        if font_family:
            legend_kwargs["prop"] = {"family": font_family, "size": legend_font_size}
        else:
            legend_kwargs["fontsize"] = legend_font_size
        axis.legend(**legend_kwargs)


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="demo_plot_polar_projection",
            name="极坐标绘图",
            handler=draw_polar_projection,
            description="将当前选中曲线或首条可见曲线重绘为极坐标图，并提供常用极坐标参数。",
            version="0.1.0",
            settings=True,
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(key="theta_unit", description="角度数据单位。", field_type="selective", default="degree", choices=("degree", "radian")),
                ExtensionConfigField(key="theta_label", description="极坐标角度轴标签；留空则保持当前设置。", field_type="string", default="角度"),
                ExtensionConfigField(key="radius_label", description="极坐标半径轴标签；留空则保持当前设置。", field_type="string", default="半径"),
                ExtensionConfigField(key="zero_location", description="极坐标零角方向。", field_type="selective", default="N", choices=("N", "E", "S", "W")),
                ExtensionConfigField(key="direction", description="角度增长方向。", field_type="selective", default="counterclockwise", choices=("counterclockwise", "clockwise")),
                ExtensionConfigField(key="theta_min", description="起始角度，单位与 theta_unit 保持一致。", field_type="number", default=None),
                ExtensionConfigField(key="theta_max", description="结束角度，单位与 theta_unit 保持一致。", field_type="number", default=None),
                ExtensionConfigField(key="r_min", description="半径下限。", field_type="number", default=None),
                ExtensionConfigField(key="r_max", description="半径上限。", field_type="number", default=None),
                ExtensionConfigField(key="close_curve", description="是否闭合首尾点。", field_type="boolean", default=False),
                ExtensionConfigField(key="show_grid", description="是否显示极坐标网格。", field_type="boolean", default=True),
                ExtensionConfigField(key="show_legend", description="是否显示图例。", field_type="boolean", default=True),
                ExtensionConfigField(key="legend_frame", description="是否显示图例边框。", field_type="boolean", default=False),
                ExtensionConfigField(key="title", description="图标题；留空则不额外设置。", field_type="string", default=""),
                ExtensionConfigField(key="label", description="图例名称；留空则沿用曲线名称。", field_type="string", default=""),
                ExtensionConfigField(key="color", description="曲线颜色；留空则沿用当前曲线颜色。", field_type="color", default=""),
                ExtensionConfigField(key="marker", description="曲线标记样式；留空则沿用当前设置。", field_type="string", default=""),
                ExtensionConfigField(key="line_width", description="曲线线宽；留空则沿用当前设置。", field_type="number", default=None),
                ExtensionConfigField(key="marker_size", description="标记大小；留空则沿用当前设置。", field_type="number", default=None),
                ExtensionConfigField(key="alpha", description="曲线透明度。", field_type="limited", default=0.95, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="fill_alpha", description="填充透明度；0 表示不填充。", field_type="limited", default=0.0, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="radial_label_angle", description="径向标签角度；留空则沿用当前设置。", field_type="number", default=None),
            ],
        )
    )