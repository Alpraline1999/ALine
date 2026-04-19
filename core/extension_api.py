from __future__ import annotations

from dataclasses import dataclass, field
from importlib import util as importlib_util
import inspect
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Tuple
import hashlib


XY = Tuple[List[float], List[float]]


@dataclass(frozen=True)
class ExtensionConfigField:
    key: str
    label: str = ""
    description: str = ""
    field_type: str = "string"
    required: bool = False
    default: Any = None
    choices: Tuple[Any, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "field_type": self.field_type,
            "required": self.required,
            "default": self.default,
            "choices": list(self.choices),
        }


@dataclass(frozen=True)
class ProcessingExtension:
    type: str
    name: str
    handler: Callable[[List[float], List[float], Dict[str, Any]], XY]
    description: str = ""
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)


@dataclass(frozen=True)
class AnalysisExtension:
    type: str
    name: str
    handler: Callable[[List[Dict[str, Any]], Dict[str, Any]], Dict[str, Any]]
    description: str = ""
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)


@dataclass(frozen=True)
class PlotExtension:
    type: str
    name: str
    handler: Callable[..., None]
    description: str = ""
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)


@dataclass
class PlotExtensionContext:
    figure: Any
    canvas: Any
    axis: Any
    axes: List[Any]
    visible_series: List[Dict[str, Any]]
    plotted_series: List[Dict[str, Any]]
    figure_state: Dict[str, Any]
    plot_style_extras: Dict[str, Any]
    theme_colors: Dict[str, Any]
    phase: str = "before_plot"
    skip_default_plot: bool = False
    skip_default_formatting: bool = False
    skip_default_layout: bool = False

    def refresh_axes(self) -> List[Any]:
        self.axes = list(getattr(self.figure, "axes", []) or [])
        if self.axes:
            if self.axis not in self.axes:
                self.axis = self.axes[0]
        else:
            self.axis = None
        return list(self.axes)

    def set_active_axis(self, axis: Any) -> Any:
        self.axis = axis
        if axis is not None and axis not in self.axes:
            self.axes.append(axis)
        return axis


@dataclass(frozen=True)
class PlotStyleExtension:
    type: str
    name: str
    handler: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    description: str = ""
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)


@dataclass(frozen=True)
class CurveStyleExtension:
    type: str
    name: str
    handler: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    description: str = ""
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)


class ExtensionRegistry:
    def __init__(self) -> None:
        self._processing: Dict[str, ProcessingExtension] = {}
        self._analysis: Dict[str, AnalysisExtension] = {}
        self._plot: Dict[str, PlotExtension] = {}
        self._plot_style: Dict[str, PlotStyleExtension] = {}
        self._curve_style: Dict[str, CurveStyleExtension] = {}

    def clear(self) -> None:
        self._processing.clear()
        self._analysis.clear()
        self._plot.clear()
        self._plot_style.clear()
        self._curve_style.clear()

    def register_processing(self, extension: ProcessingExtension) -> None:
        if not extension.type.strip():
            raise ValueError("processing extension type is required")
        self._processing[extension.type.strip()] = extension

    def register_analysis(self, extension: AnalysisExtension) -> None:
        if not extension.type.strip():
            raise ValueError("analysis extension type is required")
        self._analysis[extension.type.strip()] = extension

    def register_plot(self, extension: PlotExtension) -> None:
        if not extension.type.strip():
            raise ValueError("plot extension type is required")
        self._plot[extension.type.strip()] = extension

    def register_plot_style(self, extension: PlotStyleExtension) -> None:
        if not extension.type.strip():
            raise ValueError("plot style extension type is required")
        self._plot_style[extension.type.strip()] = extension

    def register_curve_style(self, extension: CurveStyleExtension) -> None:
        if not extension.type.strip():
            raise ValueError("curve style extension type is required")
        self._curve_style[extension.type.strip()] = extension

    def unregister_processing(self, type_id: str) -> None:
        self._processing.pop(type_id, None)

    def unregister_analysis(self, type_id: str) -> None:
        self._analysis.pop(type_id, None)

    def unregister_plot(self, type_id: str) -> None:
        self._plot.pop(type_id, None)

    def unregister_plot_style(self, type_id: str) -> None:
        self._plot_style.pop(type_id, None)

    def unregister_curve_style(self, type_id: str) -> None:
        self._curve_style.pop(type_id, None)

    def get_processing(self, type_id: str) -> Optional[ProcessingExtension]:
        return self._processing.get(type_id)

    def get_analysis(self, type_id: str) -> Optional[AnalysisExtension]:
        return self._analysis.get(type_id)

    def get_plot(self, type_id: str) -> Optional[PlotExtension]:
        return self._plot.get(type_id)

    def get_plot_style(self, type_id: str) -> Optional[PlotStyleExtension]:
        return self._plot_style.get(type_id)

    def get_curve_style(self, type_id: str) -> Optional[CurveStyleExtension]:
        return self._curve_style.get(type_id)

    def list_processing(self) -> List[ProcessingExtension]:
        return list(self._processing.values())

    def list_analysis(self) -> List[AnalysisExtension]:
        return list(self._analysis.values())

    def list_plot(self) -> List[PlotExtension]:
        return list(self._plot.values())

    def list_plot_style(self) -> List[PlotStyleExtension]:
        return list(self._plot_style.values())

    def list_curve_style(self) -> List[CurveStyleExtension]:
        return list(self._curve_style.values())

    def load_from_directory(self, directory: str | Path) -> Dict[str, List[str]]:
        target = Path(directory)
        report = {"loaded": [], "errors": []}
        if not target.exists() or not target.is_dir():
            return report
        for path in sorted(target.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                self.load_from_file(path)
                report["loaded"].append(str(path))
            except Exception as exc:
                report["errors"].append(f"{path}: {exc}")
        return report

    def load_from_file(self, file_path: str | Path) -> ModuleType:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(path)
        module_name = self._module_name_for_path(path)
        spec = importlib_util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载扩展文件: {path}")
        module = importlib_util.module_from_spec(spec)
        spec.loader.exec_module(module)
        register = getattr(module, "register_extensions", None)
        if not callable(register):
            raise ValueError(f"扩展文件缺少 register_extensions(registry) 入口: {path}")
        register(self)
        return module

    @staticmethod
    def _module_name_for_path(path: Path) -> str:
        digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
        return f"aline_extension_{path.stem}_{digest}"


extension_registry = ExtensionRegistry()


def build_extension_entry(extension: Any) -> Dict[str, Any]:
    config_fields = []
    for field_item in getattr(extension, "config_fields", []) or []:
        if hasattr(field_item, "to_dict"):
            config_fields.append(field_item.to_dict())
        elif isinstance(field_item, dict):
            config_fields.append(dict(field_item))
    return {
        "type": extension.type,
        "name": extension.name,
        "label": extension.name,
        "description": extension.description,
        "default_options": dict(getattr(extension, "default_options", {}) or {}),
        "config_fields": config_fields,
    }


def plot_extension_uses_context_api(handler: Callable[..., Any]) -> bool:
    try:
        parameters = [
            item
            for item in inspect.signature(handler).parameters.values()
            if item.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
    except (TypeError, ValueError):
        return False
    return len(parameters) <= 2


def invoke_plot_extension_handler(
    handler: Callable[..., Any],
    context: PlotExtensionContext,
    options: Dict[str, Any],
) -> None:
    if plot_extension_uses_context_api(handler):
        handler(context, dict(options))
        return
    if context.phase != "after_plot" or context.axis is None:
        return
    handler(context.axis, context.plotted_series, dict(options))


def default_extensions_directory(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    return Path(__file__).resolve().parent.parent / "extensions"


def load_builtin_extensions(directory: str | Path | None = None) -> Dict[str, List[str]]:
    return extension_registry.load_from_directory(default_extensions_directory(directory))


def reload_builtin_extensions(directory: str | Path | None = None) -> Dict[str, List[str]]:
    extension_registry.clear()
    return load_builtin_extensions(directory)


def register_processing_extension(extension: ProcessingExtension) -> None:
    extension_registry.register_processing(extension)


def register_analysis_extension(extension: AnalysisExtension) -> None:
    extension_registry.register_analysis(extension)


def register_plot_extension(extension: PlotExtension) -> None:
    extension_registry.register_plot(extension)


def register_plot_style_extension(extension: PlotStyleExtension) -> None:
    extension_registry.register_plot_style(extension)


def register_curve_style_extension(extension: CurveStyleExtension) -> None:
    extension_registry.register_curve_style(extension)