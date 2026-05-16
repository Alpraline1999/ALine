from __future__ import annotations

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.processing.extension_tools import line_xy, normalize_lines


VERSION = "0.1.0"


def analysis_interface_contract(lines, params):
    normalized = normalize_lines(lines)
    precision = max(0, int(params.get("precision", 3) or 3))
    include_plot = bool(params.get("include_plot", True))
    title = str(params.get("title", "接口示例分析") or "接口示例分析")
    method = str(params.get("method", "summary") or "summary")

    rows = []
    result_lines = []
    plot_series = []
    total_points = 0
    for index, line in enumerate(normalized, start=1):
        xs, ys = line_xy(line)
        total_points += len(xs)
        y_min = min(ys) if ys else 0.0
        y_max = max(ys) if ys else 0.0
        y_mean = sum(ys) / len(ys) if ys else 0.0
        rows.append([index, len(xs), round(y_min, precision), round(y_max, precision), round(y_mean, precision)])
        if include_plot:
            line_name = f"line_{index}"
            result_lines.append({"line_name": line_name, "line": line})
            plot_series.append({"name": line_name, "line": line_name})

    result = {
        "analysis_type": "interface_contract_analysis",
        "title": title,
        "method": method,
        "line_count": len(normalized),
        "point_count": total_points,
        "summary_items": [
            ("曲线数量", len(normalized)),
            ("点数量", total_points),
            ("分析方法", method),
        ],
        "tables": [
            {
                "title": "输入曲线摘要",
                "headers": ["序号", "点数", "Y 最小值", "Y 最大值", "Y 均值"],
                "rows": rows,
            }
        ],
        "texts": ["该扩展示例展示分析扩展的 dict 输出结构。"],
    }
    if include_plot:
        result["lines"] = result_lines
        result["_plot_series"] = plot_series
    return result


def register_extensions(registry):
    registry.register_analysis(
        AnalysisExtension(
            type="interface_contract_analysis",
            name="接口示例：分析扩展",
            handler=analysis_interface_contract,
            description="展示分析扩展的强制签名 (lines, params) -> dict，以及摘要、表格、文本和绘图输出。",
            version=VERSION,
            lines_number=(1, -1),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            config_fields=[
                ExtensionConfigField(key="title", label="分析标题", description="string 参数示例。", field_type="string", default="接口示例分析"),
                ExtensionConfigField(key="method", label="分析方法", description="selective 参数示例。", field_type="selective", default="summary", choices=("summary", "quality", "report")),
                ExtensionConfigField(key="precision", label="小数位", description="integer 参数示例。", field_type="integer", default=3, min_value=0, max_value=8),
                ExtensionConfigField(key="include_plot", label="输出绘图序列", description="boolean 参数示例。", field_type="boolean", default=True),
                ExtensionConfigField(key="accent_color", label="强调色", description="color 参数示例。", field_type="color", default="#0078D4"),
            ],
            report_placeholders=[
                {"token": "{{line_count}}", "label": "接口示例曲线数", "description": "接口示例分析输入曲线数量。"},
                {"token": "{{point_count}}", "label": "接口示例点数", "description": "接口示例分析输入点总数。"},
            ],
        )
    )
