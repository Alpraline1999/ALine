from __future__ import annotations

import math

from core.extension_api import AnalysisExtension, ExtensionConfigField


def _pearson(values_a, values_b):
    count = min(len(values_a), len(values_b))
    if count < 2:
        return 0.0
    trimmed_a = list(values_a[:count])
    trimmed_b = list(values_b[:count])
    mean_a = sum(trimmed_a) / count
    mean_b = sum(trimmed_b) / count
    covariance = sum((left - mean_a) * (right - mean_b) for left, right in zip(trimmed_a, trimmed_b))
    std_a = math.sqrt(sum((value - mean_a) ** 2 for value in trimmed_a))
    std_b = math.sqrt(sum((value - mean_b) ** 2 for value in trimmed_b))
    if std_a <= 1e-12 or std_b <= 1e-12:
        return 0.0
    return covariance / (std_a * std_b)


def _ranks(values):
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index
        while end + 1 < len(indexed) and indexed[end + 1][1] == indexed[index][1]:
            end += 1
        rank = (index + end) / 2.0 + 1.0
        for current in range(index, end + 1):
            ranks[indexed[current][0]] = rank
        index = end + 1
    return ranks


def _correlation(values_a, values_b, method):
    if method == "spearman":
        return _pearson(_ranks(values_a), _ranks(values_b))
    return _pearson(values_a, values_b)


def multi_curve_correlation(inputs, params, lines_list=None):
    aligned_lines = list(lines_list or inputs or [])
    if len(aligned_lines) < 2:
        raise ValueError("多曲线相关性分析至少需要 2 条输入曲线")

    method = str(params.get("method", "pearson") or "pearson").strip().lower()
    primary = aligned_lines[0]
    comparison_items = []
    for line in aligned_lines[1:]:
        comparison_items.append({
            "name": str(line.get("name", "") or "未命名曲线"),
            "correlation": _correlation(list(primary.get("y", [])), list(line.get("y", [])), method),
        })

    best_match = max(comparison_items, key=lambda item: abs(item["correlation"])) if comparison_items else {"name": "", "correlation": 0.0}
    average_correlation = sum(item["correlation"] for item in comparison_items) / len(comparison_items)
    line_color = str(params.get("line_color", "#C23B22") or "#C23B22")
    primary_name = str(primary.get("name", "") or "主曲线")

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
        "comparison_details": comparison_items,
        "x_label": "对比序号",
        "y_label": "相关系数",
        "plot_title": f"{primary_name} 多曲线相关性",
        "_plot_series": [
            {
                "name": "相关系数",
                "x": list(range(1, len(comparison_items) + 1)),
                "y": [item["correlation"] for item in comparison_items],
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
            description="以 lines_list 第一项为主曲线，对其余曲线按样本顺序做多曲线相关性比较，不内置重采样。",
            version="0.1.0",
            config_fields=[
                ExtensionConfigField(
                    key="lines",
                    label="输入曲线",
                    description="选择要参与相关性比较的多条曲线；第一条视为主曲线。",
                    field_type="lines",
                    default={"number": -1, "lines_list": ""},
                ),
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
                {"key": "primary_name", "label": "主曲线", "description": "当前多曲线相关性分析的主曲线名称。"},
                {"key": "compared_count", "label": "对比数量", "description": "参与比较的副曲线数量。"},
                {"key": "best_match_name", "label": "最佳匹配", "description": "与主曲线最接近的副曲线名称。"},
                {"key": "best_correlation", "label": "最佳相关系数", "description": "最佳匹配对应的相关系数。"},
                {"key": "average_correlation", "label": "平均相关系数", "description": "全部副曲线相关系数平均值。"},
            ],
        )
    )