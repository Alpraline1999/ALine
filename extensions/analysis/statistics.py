from __future__ import annotations

from core.extension_api import AnalysisExtension
from extensions.analysis.builtin_ops import VERSION, compute_statistics


def _handler(inputs, params):
    del params
    if not inputs:
        raise ValueError("statistics 需要至少一条输入数据")
    first = dict(inputs[0] or {})
    result = compute_statistics(list(first.get("x", []) or []), list(first.get("y", []) or []))
    result["analysis_type"] = "statistics"
    result["source_name"] = first.get("name", "")
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="statistics",
            name="统计分析",
            handler=_handler,
            description="计算当前曲线的常用统计量。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
        )
    )
