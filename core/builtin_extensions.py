from __future__ import annotations

from typing import Any, Dict, List

from core.extension_api import AnalysisExtension, ExtensionConfigField, ProcessingExtension
from digitize.builtin_extensions import ensure_builtin_digitize_extensions


_BUILTIN_EXTENSION_VERSION = "0.1.0"
_FIT_MODEL_CHOICES = ("linear", "power", "exponential", "gaussian", "poly2", "poly3")
_CORRELATION_METHOD_CHOICES = ("pearson", "spearman")

_PROCESSING_DESCRIPTIONS = {
    "crop": "按 X 轴范围裁剪数据，只保留目标区间。",
    "smooth": "对 Y 序列做平滑处理，适合去除高频噪声。",
    "normalize": "按 min-max 或 z-score 归一化 Y 序列。",
    "resample": "支持按点数或间距重采样，便于多曲线对齐。",
    "fft": "将时域或空间域信号转换为频域频谱。",
    "derivative": "计算一阶导数，观察变化速率。",
    "integral": "计算积分或累积积分。",
    "transform": "用表达式批量变换 X/Y 数据。",
    "filter": "进行低通或高通滤波，去除不需要的频率成分。",
    "pairwise_compute": "使用两条输入曲线执行 x1/y1/x2/y2 表达式运算。",
}

_ANALYSIS_DESCRIPTIONS = {
    "curve_fit": "对当前曲线执行模型拟合，并输出参数与拟合曲线。",
    "peak_detect": "检测波峰与波谷，支持高度、间距和突出度约束。",
    "statistics": "计算当前曲线的常用统计量。",
    "correlation": "计算两条曲线之间的 Pearson 或 Spearman 相关性。",
    "error_compare": "比较两条曲线的误差指标并输出误差曲线。",
}


def _processing_single_handler(type_id: str):
    def _handler(xs, ys, params):
        from processing.data_engine import _apply_builtin_operation

        return _apply_builtin_operation(list(xs), list(ys), type_id, dict(params or {}))

    return _handler


def _processing_pairwise_handler(xs, ys, params, lines=None):
    from processing.data_engine import _op_pairwise_compute

    result_lines, warnings = _op_pairwise_compute(list(lines or []), dict(params or {}))
    return {"lines": result_lines, "warnings": warnings}


def _analysis_curve_fit_handler(inputs, params):
    from core.analysis_engine import fit_curve

    if not inputs:
        raise ValueError("curve_fit 需要至少一条输入数据")
    first = dict(inputs[0] or {})
    result = fit_curve(list(first.get("x", []) or []), list(first.get("y", []) or []), params.get("model", "linear"), params.get("p0"))
    result["analysis_type"] = "curve_fit"
    result["source_name"] = first.get("name", "")
    return result


def _analysis_peak_detect_handler(inputs, params):
    from core.analysis_engine import detect_peaks, detect_valleys

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


def _analysis_statistics_handler(inputs, params):
    from core.analysis_engine import compute_statistics

    del params
    if not inputs:
        raise ValueError("statistics 需要至少一条输入数据")
    first = dict(inputs[0] or {})
    result = compute_statistics(list(first.get("x", []) or []), list(first.get("y", []) or []))
    result["analysis_type"] = "statistics"
    result["source_name"] = first.get("name", "")
    return result


def _analysis_correlation_handler(inputs, params):
    from core.analysis_engine import compute_correlation

    if len(inputs) < 2:
        raise ValueError("correlation 需要两条输入数据")
    first = dict(inputs[0] or {})
    second = dict(inputs[1] or {})
    result = compute_correlation(list(first.get("y", []) or []), list(second.get("y", []) or []), str(params.get("method", "pearson")))
    result["analysis_type"] = "correlation"
    result["name1"] = first.get("name", "")
    result["name2"] = second.get("name", "")
    return result


def _analysis_error_compare_handler(inputs, params):
    from core.analysis_engine import compute_error_metrics

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
    result["name1"] = first.get("name", "")
    result["name2"] = second.get("name", "")
    return result


def register_core_builtin_extensions(registry) -> None:
    processing_specs: List[ProcessingExtension] = [
        ProcessingExtension(type="crop", name="裁剪", handler=_processing_single_handler("crop"), description=_PROCESSING_DESCRIPTIONS["crop"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(type="smooth", name="平滑", handler=_processing_single_handler("smooth"), description=_PROCESSING_DESCRIPTIONS["smooth"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(type="normalize", name="归一化", handler=_processing_single_handler("normalize"), description=_PROCESSING_DESCRIPTIONS["normalize"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(type="resample", name="重采样", handler=_processing_single_handler("resample"), description=_PROCESSING_DESCRIPTIONS["resample"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(type="fft", name="FFT", handler=_processing_single_handler("fft"), description=_PROCESSING_DESCRIPTIONS["fft"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(type="derivative", name="导数", handler=_processing_single_handler("derivative"), description=_PROCESSING_DESCRIPTIONS["derivative"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(type="integral", name="积分", handler=_processing_single_handler("integral"), description=_PROCESSING_DESCRIPTIONS["integral"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(type="transform", name="数学变换", handler=_processing_single_handler("transform"), description=_PROCESSING_DESCRIPTIONS["transform"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(type="filter", name="滤波", handler=_processing_single_handler("filter"), description=_PROCESSING_DESCRIPTIONS["filter"], version=_BUILTIN_EXTENSION_VERSION, source_kind="base", hidden=True),
        ProcessingExtension(
            type="pairwise_compute",
            name="双曲线运算",
            handler=_processing_pairwise_handler,
            description=_PROCESSING_DESCRIPTIONS["pairwise_compute"],
            version=_BUILTIN_EXTENSION_VERSION,
            source_kind="base",
            hidden=True,
            line_mode="multi",
            min_lines=2,
            max_lines=2,
        ),
    ]
    for extension in processing_specs:
        if registry.get_processing(extension.type) is None:
            registry.register_processing(extension)

    analysis_specs: List[AnalysisExtension] = [
        AnalysisExtension(
            type="curve_fit",
            name="曲线拟合",
            handler=_analysis_curve_fit_handler,
            description=_ANALYSIS_DESCRIPTIONS["curve_fit"],
            version=_BUILTIN_EXTENSION_VERSION,
            default_options={"model": "linear"},
            config_fields=[
                ExtensionConfigField(
                    key="model",
                    label="拟合模型",
                    description="选择拟合模型，默认使用线性模型。",
                    field_type="selective",
                    default="linear",
                    choices=_FIT_MODEL_CHOICES,
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
            source_kind="base",
            hidden=True,
        ),
        AnalysisExtension(
            type="peak_detect",
            name="峰值检测",
            handler=_analysis_peak_detect_handler,
            description=_ANALYSIS_DESCRIPTIONS["peak_detect"],
            version=_BUILTIN_EXTENSION_VERSION,
            default_options={"min_distance": 1},
            config_fields=[
                ExtensionConfigField(
                    key="min_height",
                    label="最小峰高",
                    description="可选；低于该值的峰将被忽略。",
                    field_type="number",
                    default=None,
                ),
                ExtensionConfigField(
                    key="min_distance",
                    label="最小点间距",
                    description="按采样点数限制相邻峰/谷的最小间隔。",
                    field_type="integer",
                    default=1,
                    min_value=1,
                ),
                ExtensionConfigField(
                    key="min_distance_x",
                    label="最小 X 间距",
                    description="可选；按 X 轴距离限制相邻峰/谷的最小间隔。",
                    field_type="number",
                    default=None,
                ),
                ExtensionConfigField(
                    key="min_depth",
                    label="最小谷深",
                    description="可选；低于该值的波谷将被忽略。",
                    field_type="number",
                    default=None,
                ),
                ExtensionConfigField(
                    key="prominence",
                    label="突出度",
                    description="可选；用于过滤不明显的峰或谷。",
                    field_type="number",
                    default=None,
                ),
            ],
            source_kind="base",
            hidden=True,
        ),
        AnalysisExtension(
            type="statistics",
            name="统计分析",
            handler=_analysis_statistics_handler,
            description=_ANALYSIS_DESCRIPTIONS["statistics"],
            version=_BUILTIN_EXTENSION_VERSION,
            source_kind="base",
            hidden=True,
        ),
        AnalysisExtension(
            type="correlation",
            name="相关性",
            handler=_analysis_correlation_handler,
            description=_ANALYSIS_DESCRIPTIONS["correlation"],
            version=_BUILTIN_EXTENSION_VERSION,
            default_options={"method": "pearson"},
            config_fields=[
                ExtensionConfigField(
                    key="method",
                    label="相关性方法",
                    description="选择 Pearson 或 Spearman 相关性。",
                    field_type="selective",
                    default="pearson",
                    choices=_CORRELATION_METHOD_CHOICES,
                )
            ],
            source_kind="base",
            hidden=True,
        ),
        AnalysisExtension(
            type="error_compare",
            name="误差对比",
            handler=_analysis_error_compare_handler,
            description=_ANALYSIS_DESCRIPTIONS["error_compare"],
            version=_BUILTIN_EXTENSION_VERSION,
            source_kind="base",
            hidden=True,
        ),
    ]
    for extension in analysis_specs:
        if registry.get_analysis(extension.type) is None:
            registry.register_analysis(extension)

    ensure_builtin_digitize_extensions(registry)