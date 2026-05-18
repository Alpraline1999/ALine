from __future__ import annotations

from core.extension_api import ExtensionConfigField, PlotExtension, normalize_extension_lines_list
from core.value_parsing import coerce_float
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, align_lines_to_common_x, line_xy, series_payloads_to_lines


def _context_series(plot_context, params):
    base_series = list(plot_context.visible_series or plot_context.plotted_series or [])
    requested = normalize_extension_lines_list(params.get("lines_list")) if "lines_list" in params else []
    if requested:
        return [base_series[index - 1] for index in requested if 1 <= index <= len(base_series)]
    if isinstance(plot_context.selected_series, dict):
        return [plot_context.selected_series]
    return base_series


def draw_uncertainty_band(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return
    options = dict(params or {})
    mode = str(options.get("mode", "from_errorbar") or "from_errorbar").strip().lower()
    color = str(options.get("fill_color", "#A6CEE3") or "#A6CEE3")
    alpha = min(1.0, max(0.0, coerce_float(options.get("fill_alpha", 0.22), 0.22) or 0.22))
    label = str(options.get("label", "不确定带") or "不确定带")
    if mode == "between_curves":
        lines = series_payloads_to_lines(_context_series(plot_context, options)[:2])
        if len(lines) < 2:
            return
        aligned_lines, _warnings = align_lines_to_common_x(lines[:2], options)
        if len(aligned_lines) < 2:
            return
        first_x, first_y = line_xy(aligned_lines[0])
        _second_x, second_y = line_xy(aligned_lines[1])
        axis.fill_between(first_x, first_y, second_y, color=color, alpha=alpha, label=label, zorder=0)
        return
    series_list = _context_series(plot_context, options)
    if not series_list:
        return
    series = series_list[0]
    x_values = list(series.get("x") or [])
    y_values = list(series.get("y") or [])
    y_err = list(series.get("y_err") or [])
    if not x_values or not y_values or len(y_err) != len(y_values):
        return
    lower = [float(y_value) - float(err) for y_value, err in zip(y_values, y_err)]
    upper = [float(y_value) + float(err) for y_value, err in zip(y_values, y_err)]
    axis.fill_between(x_values, lower, upper, color=color, alpha=alpha, label=label, zorder=0)


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_uncertainty_band",
            name="不确定带",
            handler=draw_uncertainty_band,
            description="根据误差棒或两条曲线边界绘制不确定带。",
            version=BUILTIN_EXTENSION_VERSION,
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="mode", label="绘制方式", field_type="selective", default="from_errorbar", choices=("from_errorbar", "between_curves")),
                ExtensionConfigField(key="fill_color", label="填充颜色", field_type="color", default="#A6CEE3"),
                ExtensionConfigField(key="fill_alpha", label="填充透明度", field_type="limited", default=0.22, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="label", label="图例名称", field_type="string", default="不确定带"),
                ExtensionConfigField(key="align_mode", label="对齐方式", field_type="selective", default="auto", choices=("auto", "strict")),
                ExtensionConfigField(key="resample_mode", label="重采样方式", field_type="selective", default="count", choices=("count", "spacing")),
                ExtensionConfigField(key="n", label="对齐点数", field_type="integer", default=400, min_value=2),
                ExtensionConfigField(key="step", label="对齐步长", field_type="number", default=0.1, min_value=0.0, step=0.1),
            ],
        )
    )
