from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.data_engine import align_lines_to_common_x


def multi_curve_mean(xs, ys, params, lines=None):
    aligned_lines, warnings = align_lines_to_common_x(list(lines or []), params)
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
            description="对已选择列表中的多条曲线建立公共 X 坐标后，计算逐点均值曲线。",
            default_options={
                "lines": {"number": -1, "lines_list": "all"},
                "align_mode": "auto",
                "resample_mode": "count",
                "n": 200,
                "step": 0.1,
                "result_name": "",
                "line_color": "#0078D4",
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
                    key="result_name",
                    description="输出结果曲线名称，留空则使用主曲线名称派生。",
                    field_type="string",
                    default="",
                ),
                ExtensionConfigField(
                    key="line_color",
                    description="均值曲线颜色。",
                    field_type="string",
                    default="#0078D4",
                ),
            ],
        )
    )