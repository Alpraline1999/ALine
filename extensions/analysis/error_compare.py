from __future__ import annotations

from core.extension_api import AnalysisExtension
from extensions.analysis.builtin_ops import VERSION, compute_error_metrics


def _handler(inputs, params):
    del params
    if len(inputs) < 2:
        raise ValueError("error_compare 需要两条输入数据")
    first = dict(inputs[0] or {})
    second = dict(inputs[1] or {})
    result = compute_error_metrics(
        list(first.get("x", []) or []),
        list(first.get("y", []) or []),
        list(second.get("x", []) or []),
        list(second.get("y", []) or []),
    )
    result["analysis_type"] = "error_compare"
    result["name1"] = first.get("name", "")
    result["name2"] = second.get("name", "")
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="error_compare",
            name="误差对比",
            handler=_handler,
            description="比较两条曲线的误差指标并输出误差曲线。",
            version=VERSION,
            lines_number=(2, 2),
            settings=True,
                source_kind="builtin",
        )
    )
