from __future__ import annotations

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.analysis.builtin_ops import VERSION, fit_curve, parse_optional_json_list


def _handler(inputs, params):
    if not inputs:
        raise ValueError("curve_fit 需要至少一条输入数据")
    first = dict(inputs[0] or {})
    result = fit_curve(
        list(first.get("x", []) or []),
        list(first.get("y", []) or []),
        str(params.get("model", "linear") or "linear"),
        parse_optional_json_list(params.get("p0")),
    )
    result["analysis_type"] = "curve_fit"
    result["source_name"] = first.get("name", "")
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="curve_fit",
            name="曲线拟合",
            handler=_handler,
            description="对当前曲线执行模型拟合，并输出参数与拟合曲线。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
                source_kind="builtin",
            config_fields=[
                ExtensionConfigField(
                    key="model",
                    label="拟合模型",
                    description="选择拟合模型，默认使用线性模型。",
                    field_type="selective",
                    default="linear",
                    choices=("linear", "power", "exponential", "gaussian", "poly2", "poly3"),
                ),
                ExtensionConfigField(
                    key="p0",
                    label="初始参数",
                    description="可选；以 JSON 列表形式提供初始猜测参数。",
                    field_type="string",
                    default=None,
                    placeholder="[1.0, 0.5]",
                ),
            ],
        )
    )
