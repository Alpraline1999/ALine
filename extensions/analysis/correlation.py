from __future__ import annotations

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.analysis.builtin_ops import VERSION, compute_correlation


def _handler(inputs, params):
    if len(inputs) < 2:
        raise ValueError("correlation 需要两条输入数据")
    first = dict(inputs[0] or {})
    second = dict(inputs[1] or {})
    result = compute_correlation(
        list(first.get("y", []) or []),
        list(second.get("y", []) or []),
        str(params.get("method", "pearson") or "pearson"),
    )
    result["analysis_type"] = "correlation"
    result["name1"] = first.get("name", "")
    result["name2"] = second.get("name", "")
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
            config_fields=[
                ExtensionConfigField(
                    key="method",
                    label="相关性方法",
                    field_type="selective",
                    default="pearson",
                    choices=("pearson", "spearman"),
                )
            ],
        )
    )
