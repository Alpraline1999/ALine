from __future__ import annotations

from core.extension_api import ExtensionConfigField, PlotExtension, normalize_extension_lines_list
from core.value_parsing import coerce_float
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION


def _selected_series(plot_context, params):
    series = list(plot_context.visible_series or plot_context.plotted_series or [])
    requested = normalize_extension_lines_list(params.get("lines_list")) if "lines_list" in params else []
    if requested:
        return [series[index - 1] for index in requested if 1 <= index <= len(series)]
    return series


def draw_line_end_labels(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return
    template = str(params.get("label_template", "{name}") or "{name}")
    offset_x = coerce_float(params.get("offset_x", 8.0), 8.0) or 8.0
    offset_y = coerce_float(params.get("offset_y", 0.0), 0.0) or 0.0
    color_mode = str(params.get("color_mode", "follow") or "follow").strip().lower()
    fixed_color = str(params.get("color", "#222222") or "#222222")
    font_size = max(6, int(coerce_float(params.get("font_size", 10), 10) or 10))
    precision = max(0, int(coerce_float(params.get("precision", 3), 3) or 3))
    for index, series in enumerate(_selected_series(plot_context, params), start=1):
        x_values = list(series.get("x") or [])
        y_values = list(series.get("y") or [])
        if not x_values or not y_values:
            continue
        x_value = float(x_values[-1])
        y_value = float(y_values[-1])
        label = template.format(
            name=str(series.get("display_name") or series.get("name") or f"line_{index}"),
            x=round(x_value, precision),
            y=round(y_value, precision),
            index=index,
        )
        style = dict(series.get("style") or {})
        color = fixed_color if color_mode == "fixed" else str(style.get("color") or series.get("color") or fixed_color)
        axis.annotate(
            label,
            xy=(x_value, y_value),
            xytext=(offset_x, offset_y),
            textcoords="offset points",
            color=color,
            fontsize=font_size,
            ha="left",
            va="center",
            bbox={"boxstyle": "round,pad=0.2", "fc": "#ffffff", "ec": color, "alpha": 0.78} if bool(params.get("show_box", True)) else None,
        )


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_line_end_label",
            name="末端标签",
            handler=draw_line_end_labels,
            description="在可见曲线末端自动添加名称或数值标签。",
            version=BUILTIN_EXTENSION_VERSION,
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="label_template", label="标签模板", field_type="string", default="{name}", placeholder="{name} / {y} / {name}: {y}"),
                ExtensionConfigField(key="precision", label="数值小数位", field_type="integer", default=3, min_value=0),
                ExtensionConfigField(key="offset_x", label="水平偏移", field_type="number", default=8.0),
                ExtensionConfigField(key="offset_y", label="垂直偏移", field_type="number", default=0.0),
                ExtensionConfigField(key="font_size", label="字号", field_type="integer", default=10),
                ExtensionConfigField(key="color_mode", label="颜色模式", field_type="selective", default="follow", choices=("follow", "fixed")),
                ExtensionConfigField(key="color", label="固定颜色", field_type="color", default="#222222"),
                ExtensionConfigField(key="show_box", label="显示背景框", field_type="boolean", default=True),
            ],
        )
    )
