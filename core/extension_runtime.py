from __future__ import annotations

"""扩展运行时契约层。

该模块为 Phase 10 提供运行时请求/结果对象，以及一个可逐步替换
core.extension_api 直接调用的轻量 façade。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from core.curve_data import CurveBuffer, series_payloads_to_curve_batch
from core.line_tools import normalize_line, series_payloads_to_lines


@dataclass(frozen=True, slots=True)
class ExtensionExecutionRequest:
    category: str
    type_id: str
    inputs: tuple[CurveBuffer, ...] = field(default_factory=tuple)
    params: Dict[str, Any] = field(default_factory=dict)
    context: Any = None

    @classmethod
    def from_series_payloads(
        cls,
        category: str,
        type_id: str,
        inputs: Iterable[Any],
        params: Optional[Dict[str, Any]] = None,
        context: Any = None,
    ) -> "ExtensionExecutionRequest":
        return cls(
            category=str(category or ""),
            type_id=str(type_id or ""),
            inputs=tuple(series_payloads_to_curve_batch(inputs)),
            params=dict(params or {}),
            context=context,
        )


@dataclass(frozen=True, slots=True)
class ExtensionExecutionResult:
    value: Any = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error in (None, "")


class ExtensionRuntime:
    """兼容现有 extension_api 的轻量运行时 façade。"""

    def invoke_processing(self, handler: Any, inputs: List[Dict[str, Any]], params: Dict[str, Any]) -> Any:
        return invoke_processing_extension_handler(handler, inputs, params)

    def invoke_analysis(self, handler: Any, inputs: List[Dict[str, Any]], params: Dict[str, Any]) -> Any:
        return invoke_analysis_extension_handler(handler, inputs, params)

    def invoke_plot(self, extension_or_handler: Any, context: Any, params: Dict[str, Any]) -> None:
        return invoke_plot_extension_handler(extension_or_handler, context, params)

    def invoke_digitize(self, handler: Any, figure: Any, params: Dict[str, Any]) -> Any:
        return invoke_digitize_extension_handler(handler, figure, params)


DEFAULT_EXTENSION_RUNTIME = ExtensionRuntime()


def invoke_processing_extension_handler(
    handler: Any,
    inputs: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> Any:
    result = handler(series_payloads_to_lines(inputs), dict(params))
    return normalize_line(result)


def _normalize_analysis_result_lines(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_lines = payload.get("lines")
    if raw_lines is None:
        return {}
    if not isinstance(raw_lines, (list, tuple)):
        raise ValueError("分析扩展结果中的 lines 必须是包含 {line_name, line} 的列表")

    line_lookup: Dict[str, Any] = {}
    normalized_lines: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_lines, start=1):
        if not isinstance(item, dict):
            raise ValueError("分析扩展结果中的 lines 必须是包含 {line_name, line} 的字典列表")
        line_name = str(item.get("line_name") or item.get("name") or f"line_{index}").strip()
        if not line_name:
            raise ValueError("分析扩展结果中的 line_name 不能为空")
        if line_name in line_lookup:
            raise ValueError(f"分析扩展结果中的 line_name 不能重复: {line_name}")
        normalized_item = dict(item)
        normalized_item["line_name"] = line_name
        normalized_item["line"] = normalize_line(item.get("line"))
        normalized_lines.append(normalized_item)
        line_lookup[line_name] = normalized_item["line"]

    payload["lines"] = normalized_lines
    return line_lookup


def _normalize_analysis_plot_series(payload: Dict[str, Any], line_lookup: Dict[str, Any]) -> None:
    raw_plot_series = payload.get("_plot_series", payload.get("plot_series"))
    if raw_plot_series is None:
        return
    if not isinstance(raw_plot_series, (list, tuple)):
        raise ValueError("分析扩展结果中的 _plot_series 必须是列表")

    normalized_plot_series: List[Dict[str, Any]] = []
    for index, item in enumerate(raw_plot_series, start=1):
        if not isinstance(item, dict):
            raise ValueError("分析扩展结果中的 _plot_series 必须是字典列表")
        if "x" in item or "y" in item:
            raise ValueError("分析扩展结果曲线已改为 line 协议，请使用顶层 lines 和 _plot_series[].line")
        line_value = item.get("line")
        if line_value in (None, ""):
            raise ValueError("分析扩展结果中的 _plot_series 每项都必须通过 line 字段指定结果曲线")
        normalized_item = dict(item)
        if isinstance(line_value, str):
            if line_value not in line_lookup:
                raise ValueError(f"_plot_series 引用了未知结果曲线: {line_value}")
        else:
            normalized_item["line"] = normalize_line(line_value)
        normalized_plot_series.append(normalized_item)

    if "_plot_series" in payload or "plot_series" not in payload:
        payload["_plot_series"] = [dict(item) for item in normalized_plot_series]
    if "plot_series" in payload:
        payload["plot_series"] = [dict(item) for item in normalized_plot_series]


def invoke_analysis_extension_handler(
    handler: Any,
    inputs: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> Any:
    normalized_inputs = [dict(item or {}) for item in inputs]
    result = handler(series_payloads_to_lines(normalized_inputs), dict(params))
    if not isinstance(result, dict):
        return result

    payload = dict(result)
    if normalized_inputs:
        source_name = str(normalized_inputs[0].get("name", "") or "")
        if source_name and not str(payload.get("source_name", "") or "").strip():
            payload["source_name"] = source_name
    if len(normalized_inputs) >= 2:
        name1 = str(normalized_inputs[0].get("name", "") or "")
        name2 = str(normalized_inputs[1].get("name", "") or "")
        if name1 and not str(payload.get("name1", "") or "").strip():
            payload["name1"] = name1
        if name2 and not str(payload.get("name2", "") or "").strip():
            payload["name2"] = name2
    line_lookup = _normalize_analysis_result_lines(payload)
    _normalize_analysis_plot_series(payload, line_lookup)
    return payload


def invoke_plot_extension_handler(
    extension_or_handler: Any,
    context: Any,
    params: Dict[str, Any],
) -> None:
    from core.extension_api import PlotExtension, normalize_plot_extension_phases

    extension = extension_or_handler if isinstance(extension_or_handler, PlotExtension) else None
    handler = extension.handler if extension is not None else extension_or_handler
    supported_phases = normalize_plot_extension_phases(getattr(extension, "phases", None)) if extension is not None else ("before_plot", "after_plot")
    if context.phase not in supported_phases:
        return

    try:
        import matplotlib.pyplot as plt
    except Exception:
        plt = None  # type: ignore[assignment]

    if plt is not None and context.figure is not None:
        try:
            plt.figure(context.figure.number)
        except Exception:
            pass
    if plt is not None and context.axis is not None:
        try:
            plt.sca(context.axis)
        except Exception:
            pass

    try:
        handler(context, dict(params))
        context.refresh_axes()
    finally:
        pass

    if plt is not None and context.axes:
        try:
            current_axis = plt.gca()
        except Exception:
            current_axis = None
        if current_axis is not None and getattr(current_axis, "figure", None) is context.figure:
            context.set_active_axis(current_axis)


def invoke_digitize_extension_handler(
    handler: Any,
    figure: Any,
    params: Dict[str, Any],
) -> Any:
    result = handler(figure, dict(params))
    return normalize_line(result)
