from __future__ import annotations

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.analysis.analysis_tools import correlation as _correlation
from extensions.processing.extension_tools import line_from_xy, line_xy, normalize_lines


def multi_curve_correlation(lines, params):
    aligned_lines = normalize_lines(lines)
    if len(aligned_lines) < 2:
        raise ValueError("多曲线相关性分析至少需要 2 条输入曲线")

    method = str(params.get("method", "pearson") or "pearson").strip().lower()
    primary = aligned_lines[0]
    _primary_x, primary_y = line_xy(primary)
    comparison_items = []
    for index, line in enumerate(aligned_lines[1:], start=2):
        _line_x, line_y = line_xy(line)
        corr_result = _correlation(primary_y, line_y, method)
        comparison_items.append({
            "name": f"line_{index}",
            "correlation": corr_result["r"],
            "p_value": corr_result.get("p_value"),
        })

    best_match = max(comparison_items, key=lambda item: abs(item["correlation"])) if comparison_items else {"name": "", "correlation": 0.0}
    average_correlation = sum(item["correlation"] for item in comparison_items) / len(comparison_items)
    line_color = str(params.get("line_color", "#C23B22") or "#C23B22")
    primary_name = "line_1"
    correlation_line = line_from_xy(
        list(range(1, len(comparison_items) + 1)),
        [item["correlation"] for item in comparison_items],
    )

    p_values = [item["p_value"] for item in comparison_items if item.get("p_value") is not None]
    summary_items = [
        {"label": "主曲线", "value": primary_name},
        {"label": "对比数量", "value": len(comparison_items)},
        {"label": "方法", "value": method},
        {"label": "最佳匹配", "value": f"{best_match['name']} (r={best_match['correlation']:.4f})"},
        {"label": "平均相关系数", "value": f"{average_correlation:.4f}"},
    ]
    if p_values:
        min_p = min(p_values)
        significant = sum(1 for p in p_values if p < 0.05)
        summary_items.append({"label": "显著对比数", "value": f"{significant}/{len(p_values)}（p<0.05）"})

    return {
        "analysis_type": "multi_curve_correlation",
        "source_name": primary_name,
        "primary_name": primary_name,
        "method": method,
        "compared_count": len(comparison_items),
        "best_match_name": best_match["name"],
        "best_correlation": best_match["correlation"],
        "average_correlation": average_correlation,
        "alignment_note": "",
        "summary_items": summary_items,
        "comparison_details": comparison_items,
        "x_label": "对比序号",
        "y_label": "相关系数",
        "plot_title": f"{primary_name} 多曲线相关性",
        "lines": [
            {
                "line_name": "相关系数",
                "line": correlation_line,
            }
        ],
        "_plot_series": [
            {
                "name": "相关系数",
                "line": "相关系数",
                "color": line_color,
            }
        ],
    }


def register_extensions(registry):
    registry.register_analysis(
        AnalysisExtension(
            type="multi_curve_correlation",
            name="多曲线相关性",
            handler=multi_curve_correlation,
            description="以第一条输入曲线为主曲线，对其余曲线执行多曲线相关性比较。",
            version="0.1.0",
            lines_number=(2, -1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="method",
                    description="相关系数算法：pearson 或 spearman。",
                    field_type="selective",
                    default="pearson",
                    choices=("pearson", "spearman"),
                ),
                ExtensionConfigField(
                    key="line_color",
                    description="相关性结果曲线颜色。",
                    field_type="color",
                    default="#C23B22",
                ),
            ],
            report_placeholders=[
                {"token": "{{primary_name}}", "label": "主曲线", "description": "当前多曲线相关性分析的主曲线名称。"},
                {"token": "{{compared_count}}", "label": "对比数量", "description": "参与比较的副曲线数量。"},
                {"token": "{{best_match_name}}", "label": "最佳匹配", "description": "与主曲线最接近的副曲线名称。"},
                {"token": "{{best_correlation}}", "label": "最佳相关系数", "description": "最佳匹配对应的相关系数。"},
                {"token": "{{average_correlation}}", "label": "平均相关系数", "description": "全部副曲线相关系数平均值。"},
            ],
        )
    )