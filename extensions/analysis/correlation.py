from __future__ import annotations

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.analysis.analysis_tools import correlation as _correlation
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION as VERSION, align_lines_to_common_x, line_from_xy, line_xy, normalize_lines


def _interpret_correlation(r: float) -> str:
    abs_r = abs(r)
    if abs_r >= 0.8:
        strength = "强"
    elif abs_r >= 0.5:
        strength = "中等"
    elif abs_r >= 0.3:
        strength = "弱"
    else:
        strength = "极弱或无"
    direction = "正相关" if r >= 0 else "负相关"
    return f"{strength}{direction}"


def _handler(lines, params):
    normalized_lines = normalize_lines(lines)
    if len(normalized_lines) < 2:
        raise ValueError("correlation 需要两条输入数据")
    aligned_lines, warnings = align_lines_to_common_x(normalized_lines[:2], {"align_mode": "auto"})
    if len(aligned_lines) < 2:
        raise ValueError("对齐后有效曲线不足 2 条")
    first = aligned_lines[0]
    second = aligned_lines[1]
    _x1, y1 = line_xy(first)
    _x2, y2 = line_xy(second)
    result = _correlation(
        y1,
        y2,
        str(params.get("method", "pearson") or "pearson"),
    )
    result["analysis_type"] = "correlation"
    r = result.get("r", 0.0)
    p_value = result.get("p_value")
    n = min(len(y1), len(y2))
    result["summary_items"] = [
        {"label": "相关系数 r", "value": f"{r:.6f}"},
        {"label": "样本数 n", "value": n},
        {"label": "判定", "value": _interpret_correlation(r)},
    ]
    if p_value is not None:
        significance = "显著" if p_value < 0.05 else "不显著"
        result["summary_items"].append(
            {"label": "p 值", "value": f"{p_value:.6g}（{significance}）"},
        )
    if warnings:
        result["summary_items"].append({"label": "对齐说明", "value": warnings[0]})
    # 散点图
    result["lines"] = [
        {"line_name": "散点数据", "line": line_from_xy(list(y1), list(y2))},
    ]
    result["_plot_series"] = [
        {
            "name": f"散点相关 (r={r:.4f})",
            "line": "散点数据",
            "kind": "scatter",
            "color": "#0078D4",
            "alpha": 0.7,
            "size": 20,
        },
    ]
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="correlation",
            name="相关性",
            handler=_handler,
            description="计算两条曲线之间的 Pearson 或 Spearman 相关性。",
            version=VERSION,
            lines_number=(2, 2),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="method",
                    label="相关性方法",
                    field_type="selective",
                    default="pearson",
                    choices=("pearson", "spearman"),
                )
            ],
            report_placeholders=[
                {"token": "{{r}}", "label": "相关系数", "description": "Pearson/Spearman 相关系数。"},
                {"token": "{{p_value}}", "label": "p 值", "description": "显著性 p 值。"},
                {"token": "{{interpretation}}", "label": "判定结果", "description": "相关性强弱与方向。"},
            ],
        )
    )
