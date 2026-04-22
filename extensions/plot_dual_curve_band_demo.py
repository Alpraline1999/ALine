from __future__ import annotations

from core.extension_api import ExtensionConfigField, PlotExtension
from processing.data_engine import align_lines_to_common_x


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _candidate_series(plot_context):
    series = list(plot_context.visible_series or [])
    if len(series) >= 2:
        return series[:2]
    return []


def draw_dual_curve_band(plot_context, options):
    axis = plot_context.axis or (plot_context.axes[0] if plot_context.axes else None)
    if axis is None:
        return

    candidates = _candidate_series(plot_context)
    if len(candidates) < 2:
        return

    aligned_lines, warnings = align_lines_to_common_x(
        [
            {
                "name": item.get("display_name") or item.get("name") or "未命名曲线",
                "x": list(item.get("x") or []),
                "y": list(item.get("y") or []),
                "color": item.get("color") or "#0078D4",
            }
            for item in candidates
        ],
        options,
    )
    if len(aligned_lines) < 2:
        return

    first, second = aligned_lines[:2]
    x_values = list(first.get("x", []))
    first_y = list(first.get("y", []))
    second_y = list(second.get("y", []))
    if not x_values:
        return

    fill_color = str(options.get("fill_color", "#F4B183") or "#F4B183")
    fill_alpha = min(1.0, max(0.0, _as_float(options.get("fill_alpha", 0.18), 0.18)))
    label = str(options.get("label", "双曲线差异带") or "双曲线差异带")

    if plot_context.phase == "before_plot":
        axis.fill_between(x_values, first_y, second_y, color=fill_color, alpha=fill_alpha, label=label, zorder=0)
        return

    if plot_context.phase != "after_plot" or not bool(options.get("annotate_max_gap", True)):
        return

    differences = [abs(left - right) for left, right in zip(first_y, second_y)]
    if not differences:
        return
    peak_index = max(range(len(differences)), key=lambda index: differences[index])
    foreground = str(plot_context.theme_colors.get("foreground", "#222222"))
    background = str(plot_context.theme_colors.get("background", "#ffffff"))
    peak_x = x_values[peak_index]
    peak_y = (first_y[peak_index] + second_y[peak_index]) / 2.0
    precision = max(0, int(_as_float(options.get("annotation_precision", 3), 3)))
    axis.annotate(
        f"最大差值 = {differences[peak_index]:.{precision}f}",
        xy=(peak_x, peak_y),
        xytext=(10, 10),
        textcoords="offset points",
        color=foreground,
        fontsize=max(8, int(_as_float(options.get("annotation_font_size", 9), 9))),
        bbox={"boxstyle": "round,pad=0.3", "fc": background, "ec": fill_color, "alpha": 0.92},
        arrowprops={"arrowstyle": "->", "color": fill_color, "linewidth": 1.0},
    )
    if warnings and bool(options.get("append_alignment_note", True)):
        current_title = axis.get_title().strip()
        note = warnings[0]
        axis.set_title(note if not current_title else f"{current_title}\n{note}")


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_dual_curve_band",
            name="双曲线差异带",
            handler=draw_dual_curve_band,
            description="演示如何在绘图阶段对前两条可见曲线自动对齐，并绘制双曲线差异带。",
            default_options={
                "lines": {"number": 2, "lines_list": [1, 2]},
                "align_mode": "auto",
                "resample_mode": "count",
                "n": 200,
                "step": 0.1,
                "fill_color": "#F4B183",
                "fill_alpha": 0.18,
                "label": "双曲线差异带",
                "annotate_max_gap": True,
                "annotation_precision": 3,
                "annotation_font_size": 9,
                "append_alignment_note": True,
            },
            config_fields=[
                ExtensionConfigField(
                    key="align_mode",
                    description="坐标未对齐时的处理方式：auto 自动重采样，strict 直接报错。",
                    field_type="string",
                    default="auto",
                    choices=("auto", "strict"),
                ),
                ExtensionConfigField(
                    key="resample_mode",
                    description="自动对齐时的重采样方式：count 固定点数，spacing 固定间距。",
                    field_type="string",
                    default="count",
                    choices=("count", "spacing"),
                ),
                ExtensionConfigField(
                    key="n",
                    description="固定点数模式下的输出点数。",
                    field_type="integer",
                    default=200,
                ),
                ExtensionConfigField(
                    key="step",
                    description="固定间距模式下的 X 轴间距。",
                    field_type="number",
                    default=0.1,
                ),
                ExtensionConfigField(
                    key="fill_color",
                    description="差异带颜色。",
                    field_type="string",
                    default="#F4B183",
                ),
                ExtensionConfigField(
                    key="fill_alpha",
                    description="差异带透明度。",
                    field_type="number",
                    default=0.18,
                ),
                ExtensionConfigField(
                    key="label",
                    description="图例中的差异带名称。",
                    field_type="string",
                    default="双曲线差异带",
                ),
                ExtensionConfigField(
                    key="annotate_max_gap",
                    description="是否标记最大差值位置。",
                    field_type="boolean",
                    default=True,
                ),
            ],
        )
    )