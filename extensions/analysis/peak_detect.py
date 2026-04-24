from __future__ import annotations

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.analysis.builtin_ops import VERSION, detect_peaks, detect_valleys


def _handler(inputs, params):
    if not inputs:
        raise ValueError("peak_detect 需要至少一条输入数据")
    first = dict(inputs[0] or {})
    xs = list(first.get("x", []) or [])
    ys = list(first.get("y", []) or [])
    result = detect_peaks(
        xs,
        ys,
        min_height=params.get("min_height"),
        min_distance=params.get("min_distance", 1),
        min_distance_x=params.get("min_distance_x"),
        prominence=params.get("prominence"),
    )
    valleys = detect_valleys(
        xs,
        ys,
        min_depth=params.get("min_depth"),
        min_distance=params.get("min_distance", 1),
        min_distance_x=params.get("min_distance_x"),
        prominence=params.get("prominence"),
    )
    result["valleys"] = valleys.get("valleys", [])
    result["valley_count"] = valleys.get("count", 0)
    result["analysis_type"] = "peak_detect"
    result["source_name"] = first.get("name", "")
    return result


def register_extensions(registry) -> None:
    registry.register_analysis(
        AnalysisExtension(
            type="peak_detect",
            name="峰值检测",
            handler=_handler,
            description="检测波峰与波谷，支持高度、间距和突出度约束。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(key="min_height", label="最小峰高", field_type="number", default=None),
                ExtensionConfigField(key="min_distance", label="最小点间距", field_type="integer", default=1, min_value=1),
                ExtensionConfigField(key="min_distance_x", label="最小 X 间距", field_type="number", default=None),
                ExtensionConfigField(key="min_depth", label="最小谷深", field_type="number", default=None),
                ExtensionConfigField(key="prominence", label="突出度", field_type="number", default=None),
            ],
        )
    )
