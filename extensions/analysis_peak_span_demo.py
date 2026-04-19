from core.extension_api import AnalysisExtension, ExtensionConfigField


def peak_span(inputs, params):
    source = inputs[0] if inputs else {}
    values = [float(value) for value in source.get("y", [])]
    span = (max(values) - min(values)) if values else 0.0
    return {
        "analysis_type": "demo_analysis_peak_span",
        "source_name": source.get("name", ""),
        "span": span,
        "unit": str(params.get("unit", "a.u.")),
        "sample_count": len(values),
    }


def register_extensions(registry):
    registry.register_analysis(
        AnalysisExtension(
            type="demo_analysis_peak_span",
            name="示例·峰谷跨度",
            handler=peak_span,
            description="返回输入序列的峰谷跨度与样本点数量。",
            default_options={"unit": "MPa"},
            config_fields=[
                ExtensionConfigField(
                    key="unit",
                    label="结果单位",
                    description="写入分析结果中的单位文本。",
                    field_type="string",
                    default="MPa",
                )
            ],
        )
    )