from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.data_engine import align_lines_to_common_x


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
            line_mode="multi",
            min_lines=2,
            description="对已选择列表中的多条已对齐曲线计算逐点均值；若坐标未对齐，请先显式重采样。",
            version="0.1.0",
            config_fields=[
                ExtensionConfigField(
                    key="lines",
                    label="输入曲线",
                    description="选择要参与均值计算的多条曲线；未显式指定时沿用已选择列表。",
                    field_type="lines",
                    default={"number": -1, "lines_list": ""},
                ),
            ],
        )
    )