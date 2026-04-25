from __future__ import annotations

from core.extension_api import ExtensionConfigField, PlotExtension
from extensions.plot._runtime import current_axis, current_theme_colors
from processing.data_engine import align_lines_to_common_x
from processing.extension_tools import line_payloads_from_lines, normalize_lines


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def draw_dual_curve_band(lines, params):
    axis = current_axis()
    if axis is None:
        return

    candidates = normalize_lines(lines)[:2]
    if len(candidates) < 2:
        return

    aligned_lines, warnings = align_lines_to_common_x(line_payloads_from_lines(candidates), params)
    if len(aligned_lines) < 2:
        return

    first, second = aligned_lines[:2]
    x_values = list(first.get("x", []))
    first_y = list(first.get("y", []))
    second_y = list(second.get("y", []))
    if not x_values:
        return

    fill_color = str(params.get("fill_color", "#F4B183") or "#F4B183")
    fill_alpha = min(1.0, max(0.0, _as_float(params.get("fill_alpha", 0.18), 0.18)))
    label = str(params.get("label", "双曲线差异带") or "双曲线差异带")
    axis.fill_between(x_values, first_y, second_y, color=fill_color, alpha=fill_alpha, label=label, zorder=0)

    if not bool(params.get("annotate_max_gap", True)):
        if warnings and bool(params.get("append_alignment_note", True)):
            current_title = axis.get_title().strip()
            note = warnings[0]
            axis.set_title(note if not current_title else f"{current_title}\n{note}")
        return

    differences = [abs(left - right) for left, right in zip(first_y, second_y)]
    if not differences:
        return
    peak_index = max(range(len(differences)), key=lambda index: differences[index])
    theme_colors = current_theme_colors(axis)
    foreground = theme_colors["foreground"]
    background = theme_colors["background"]
    peak_x = x_values[peak_index]
    peak_y = (first_y[peak_index] + second_y[peak_index]) / 2.0
    precision = max(0, int(_as_float(params.get("annotation_precision", 3), 3)))
    axis.annotate(
        f"最大差值 = {differences[peak_index]:.{precision}f}",
        xy=(peak_x, peak_y),
        xytext=(10, 10),
        textcoords="offset points",
        color=foreground,
        fontsize=max(8, int(_as_float(params.get("annotation_font_size", 9), 9))),
        bbox={"boxstyle": "round,pad=0.3", "fc": background, "ec": fill_color, "alpha": 0.92},
        arrowprops={"arrowstyle": "->", "color": fill_color, "linewidth": 1.0},
    )
    if warnings and bool(params.get("append_alignment_note", True)):
        current_title = axis.get_title().strip()
        note = warnings[0]
        axis.set_title(note if not current_title else f"{current_title}\n{note}")


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_dual_curve_band",
            name="双曲线差异带",
            handler=draw_dual_curve_band,
            description="对两条输入曲线自动对齐，并绘制双曲线差异带。",
            version="0.1.0",
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="align_mode", description="坐标未对齐时的处理方式：auto 自动重采样，strict 直接报错。", field_type="selective", default="auto", choices=("auto", "strict")),
                ExtensionConfigField(key="resample_mode", description="自动对齐时的重采样方式：count 固定点数，spacing 固定间距。", field_type="selective", default="count", choices=("count", "spacing")),
                ExtensionConfigField(key="n", description="固定点数模式下的输出点数。", field_type="integer", default=200),
                ExtensionConfigField(key="step", description="固定间距模式下的 X 轴间距。", field_type="number", default=0.1),
                ExtensionConfigField(key="fill_color", description="差异带颜色。", field_type="color", default="#F4B183"),
                ExtensionConfigField(key="fill_alpha", description="差异带透明度。", field_type="limited", default=0.18, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="label", description="图例中的差异带名称。", field_type="string", default="双曲线差异带"),
                ExtensionConfigField(key="annotate_max_gap", description="是否标记最大差值位置。", field_type="boolean", default=True),
                ExtensionConfigField(key="annotation_precision", description="最大差值注释的小数位数。", field_type="integer", default=3),
                ExtensionConfigField(key="annotation_font_size", description="最大差值注释字号。", field_type="integer", default=9),
                ExtensionConfigField(key="append_alignment_note", description="是否在标题中追加对齐说明。", field_type="boolean", default=True),
            ],
        )
    )