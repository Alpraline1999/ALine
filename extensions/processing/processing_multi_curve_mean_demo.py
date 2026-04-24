from __future__ import annotations

from core.extension_api import ProcessingExtension
from extensions.processing.builtin_ops import align_lines_to_common_x


def multi_curve_mean(xs, ys, params, lines=None):
    aligned_lines, warnings = align_lines_to_common_x(list(lines or []), {"align_mode": "strict"})
    if len(aligned_lines) < 2:
        raise ValueError("多曲线均值至少需要 2 条输入曲线")

    point_count = len(aligned_lines[0].get("x", []))
    averaged = []
    for index in range(point_count):
        averaged.append(sum(float(line["y"][index]) for line in aligned_lines) / len(aligned_lines))

    primary = aligned_lines[0]
    result_name = str(params.get("result_name", "") or "").strip() or f"{primary.get('name', 'primary')}_mean"
    line_color = str(params.get("line_color", primary.get("color", "#0078D4")) or primary.get("color", "#0078D4"))
    return {
        "name": result_name,
        "x": list(primary.get("x", [])),
        "y": averaged,
        "x_label": str(primary.get("x_label", "x") or "x"),
        "y_label": str(primary.get("y_label", "y") or "y"),
        "color": line_color,
        "warnings": warnings,
    }


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="multi_curve_mean",
            name="多曲线均值",
            handler=multi_curve_mean,
            description="对已选择列表中的多条已对齐曲线计算逐点均值；若坐标未对齐，请先显式重采样。",
            version="0.1.0",
            lines_number=(2, -1),
                settings=True,
        )
    )