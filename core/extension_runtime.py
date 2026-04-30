from __future__ import annotations

"""扩展运行时契约层。

该模块为 Phase 10 提供运行时请求/结果对象，以及一个可逐步替换
core.extension_api 直接调用的轻量 façade。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from core.curve_data import CurveBuffer, series_payloads_to_curve_batch


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
        from core.extension_api import invoke_processing_extension_handler

        return invoke_processing_extension_handler(handler, inputs, params)

    def invoke_analysis(self, handler: Any, inputs: List[Dict[str, Any]], params: Dict[str, Any]) -> Any:
        from core.extension_api import invoke_analysis_extension_handler

        return invoke_analysis_extension_handler(handler, inputs, params)

    def invoke_plot(self, extension_or_handler: Any, context: Any, params: Dict[str, Any]) -> None:
        from core.extension_api import invoke_plot_extension_handler

        return invoke_plot_extension_handler(extension_or_handler, context, params)

    def invoke_digitize(self, handler: Any, figure: Any, params: Dict[str, Any]) -> Any:
        from core.extension_api import invoke_digitize_extension_handler

        return invoke_digitize_extension_handler(handler, figure, params)


DEFAULT_EXTENSION_RUNTIME = ExtensionRuntime()
