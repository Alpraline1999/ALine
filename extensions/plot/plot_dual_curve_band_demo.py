from __future__ import annotations

from core.extension_api import ExtensionConfigField, PlotExtension
from extensions.processing.base_tools import align_lines_to_common_x


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


def _resolve_line_indices(options, total):
    raw = options.get("lines_list", [1, 2])
    if raw in (None, "", []):
        raw = [1, 2]
    if not isinstance(raw, (list, tuple)):
        raw = [raw]
    result = []
    for item in raw:
        try:
            index = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= index <= total:
            result.append(index)
    return result or [1, 2]


def _candidate_series_for_lines(plot_context, options):
    series = list(plot_context.visible_series or [])
    if len(series) < 2:
        return []
    indices = _resolve_line_indices(options, len(series))
    chosen = [series[index - 1] for index in indices[:2] if 1 <= index <= len(series)]
    if len(chosen) >= 2:
        return chosen[:2]
    return _candidate_series(plot_context)


def draw_dual_curve_band(plot_context, options):
    axis = plot_context.axis or (plot_context.axes[0] if plot_context.axes else None)
    if axis is None:
        return

    candidates = _candidate_series_for_lines(plot_context, options)
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
            version="0.1.0",
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(
                    key="align_mode",
                    description="坐标未对齐时的处理方式：auto 自动重采样，strict 直接报错。",
                    field_type="selective",
                    default="auto",
                    choices=("auto", "strict"),
                ),
                ExtensionConfigField(
                    key="resample_mode",
                    description="自动对齐时的重采样方式：count 固定点数，spacing 固定间距。",
                    field_type="selective",
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
                    field_type="color",
                    default="#F4B183",
                ),
                ExtensionConfigField(
                    key="fill_alpha",
                    description="差异带透明度。",
                    field_type="limited",
                    default=0.18,
                    min_value=0.0,
                    max_value=1.0,
                    step=0.01,
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
                ExtensionConfigField(
                    key="annotation_precision",
                    description="最大差值注释的小数位数。",
                    field_type="integer",
                    default=3,
                ),
                ExtensionConfigField(
                    key="annotation_font_size",
                    description="最大差值注释字号。",
                    field_type="integer",
                    default=9,
                ),
                ExtensionConfigField(
                    key="append_alignment_note",
                    description="是否在标题中追加对齐说明。",
                    field_type="boolean",
                    default=True,
                ),
            ],
        )
    )