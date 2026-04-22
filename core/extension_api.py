from __future__ import annotations

from dataclasses import dataclass, field
from importlib import util as importlib_util
import inspect
import copy
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
import hashlib


XY = Tuple[List[float], List[float]]

_EXTENSION_CATEGORY_LABELS = {
    "processing": "处理扩展",
    "analysis": "分析扩展",
    "plot": "绘图扩展",
}

_EXTENSION_SOURCE_LABELS = {
    "builtin": "内置",
    "external": "外部",
}

_EXTENSION_SOURCE_HINTS = {
    "processing": ("register_processing", "ProcessingExtension"),
    "analysis": ("register_analysis", "AnalysisExtension"),
    "plot": ("register_plot", "PlotExtension"),
}


def _merge_nested_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_nested_dict(result[key], value)
            continue
        result[key] = copy.deepcopy(value)
    return result


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _infer_extension_source_kind(
    path: str | Path,
    source_directory: str | Path | None = None,
) -> str:
    candidate = Path(path).expanduser().resolve(strict=False)
    if source_directory is not None:
        directory = Path(source_directory).expanduser().resolve(strict=False)
        builtin_dir = default_extensions_directory().expanduser().resolve(strict=False)
        if directory == builtin_dir or _path_is_within(directory, builtin_dir):
            return "builtin"
        if _path_is_within(candidate, directory):
            return "external"
    builtin_dir = default_extensions_directory().expanduser().resolve(strict=False)
    if candidate == builtin_dir or _path_is_within(candidate, builtin_dir):
        return "builtin"
    return "external"


def _detail_source_kind(item: Dict[str, Any]) -> str:
    source = str(item.get("source") or "").strip().lower()
    if source in _EXTENSION_SOURCE_LABELS:
        return source
    return _infer_extension_source_kind(item.get("path", ""), item.get("directory"))


def _annotate_extension_detail(item: Dict[str, Any]) -> Dict[str, Any]:
    annotated = copy.deepcopy(item)
    source = _detail_source_kind(annotated)
    annotated["source"] = source
    annotated["source_label"] = _EXTENSION_SOURCE_LABELS.get(source, source)
    return annotated


def _count_extensions_for_detail(item: Dict[str, Any], category: Optional[str] = None) -> int:
    extensions = dict(item.get("extensions") or {})
    if category:
        return len(extensions.get(category, []) or [])
    return sum(len(type_ids or []) for type_ids in extensions.values())


def _summarize_extension_sources(
    details: Dict[str, List[Dict[str, Any]]],
    category: Optional[str] = None,
) -> Dict[str, Dict[str, int]]:
    loaded_extension_counts = {"builtin": 0, "external": 0}
    loaded_file_counts = {"builtin": 0, "external": 0}
    error_file_counts = {"builtin": 0, "external": 0}

    for item in details.get("loaded", []):
        source = _detail_source_kind(item)
        loaded_file_counts[source] = loaded_file_counts.get(source, 0) + 1
        loaded_extension_counts[source] = loaded_extension_counts.get(source, 0) + _count_extensions_for_detail(item, category)

    for item in details.get("errors", []):
        source = _detail_source_kind(item)
        error_file_counts[source] = error_file_counts.get(source, 0) + 1

    return {
        "loaded_extension_counts": loaded_extension_counts,
        "loaded_file_counts": loaded_file_counts,
        "error_file_counts": error_file_counts,
    }


def _format_source_split(counts: Dict[str, int]) -> str:
    builtin_count = int(counts.get("builtin", 0) or 0)
    external_count = int(counts.get("external", 0) or 0)
    if builtin_count + external_count <= 0:
        return ""
    return f"（内置 {builtin_count} / 外部 {external_count}）"


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
    report_placeholders: List[Dict[str, Any]] = field(default_factory=list)


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
    selected_series: Optional[Dict[str, Any]] = None
    selected_series_identity: Optional[str] = None
    phase: str = "before_plot"
    skip_default_plot: bool = False
    skip_default_formatting: bool = False
    skip_default_layout: bool = False
    figure_state_patch: Dict[str, Any] = field(default_factory=dict)
    plot_style_patch: Dict[str, Any] = field(default_factory=dict)
    curve_style_patches: Dict[str, Dict[str, Any]] = field(default_factory=dict)

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

    def patch_figure_state(self, patch: Dict[str, Any]) -> None:
        clean_patch = {str(key): copy.deepcopy(value) for key, value in dict(patch or {}).items()}
        if not clean_patch:
            return
        self.figure_state.update(clean_patch)
        self.figure_state_patch.update(clean_patch)

    def patch_plot_style(self, patch: Dict[str, Any]) -> None:
        clean_patch = copy.deepcopy(dict(patch or {}))
        if not clean_patch:
            return
        self.plot_style_extras = _merge_nested_dict(self.plot_style_extras, clean_patch)
        self.plot_style_patch = _merge_nested_dict(self.plot_style_patch, clean_patch)

    def patch_curve_style(self, curve_identity: Optional[str], patch: Dict[str, Any]) -> None:
        target_identity = str(curve_identity or "").strip()
        clean_patch = copy.deepcopy(dict(patch or {}))
        if not target_identity or not clean_patch:
            return

        existing_patch = self.curve_style_patches.get(target_identity, {})
        self.curve_style_patches[target_identity] = _merge_nested_dict(existing_patch, clean_patch)

        if self.selected_series_identity == target_identity and isinstance(self.selected_series, dict):
            current_style = dict(self.selected_series.get("style") or {})
            current_style = _merge_nested_dict(current_style, clean_patch)
            self.selected_series["style"] = current_style

        for series in self.visible_series:
            identity = str(series.get("curve_identity") or series.get("obj_id") or series.get("name") or "").strip()
            if identity != target_identity:
                continue
            current_style = dict(series.get("style") or {})
            current_style = _merge_nested_dict(current_style, clean_patch)
            series["style"] = current_style

    def patch_selected_curve_style(self, patch: Dict[str, Any]) -> None:
        self.patch_curve_style(self.selected_series_identity, patch)

    def clear_style_patches(self) -> None:
        self.figure_state_patch.clear()
        self.plot_style_patch.clear()
        self.curve_style_patches.clear()


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
        self._last_load_report: Dict[str, List[str]] = {"loaded": [], "errors": []}
        self._last_load_details: Dict[str, List[Dict[str, Any]]] = {"loaded": [], "errors": []}

    def clear(self) -> None:
        self._processing.clear()
        self._analysis.clear()
        self._plot.clear()
        self._last_load_report = {"loaded": [], "errors": []}
        self._last_load_details = {"loaded": [], "errors": []}

    def get_last_load_report(self) -> Dict[str, List[str]]:
        return {
            "loaded": list(self._last_load_report.get("loaded", [])),
            "errors": list(self._last_load_report.get("errors", [])),
        }

    def get_last_load_details(self) -> Dict[str, List[Dict[str, Any]]]:
        return copy.deepcopy(self._last_load_details)

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

    def unregister_processing(self, type_id: str) -> None:
        self._processing.pop(type_id, None)

    def unregister_analysis(self, type_id: str) -> None:
        self._analysis.pop(type_id, None)

    def unregister_plot(self, type_id: str) -> None:
        self._plot.pop(type_id, None)

    def get_processing(self, type_id: str) -> Optional[ProcessingExtension]:
        return self._processing.get(type_id)

    def get_analysis(self, type_id: str) -> Optional[AnalysisExtension]:
        return self._analysis.get(type_id)

    def get_plot(self, type_id: str) -> Optional[PlotExtension]:
        return self._plot.get(type_id)

    def list_processing(self) -> List[ProcessingExtension]:
        return list(self._processing.values())

    def list_analysis(self) -> List[AnalysisExtension]:
        return list(self._analysis.values())

    def list_plot(self) -> List[PlotExtension]:
        return list(self._plot.values())

    def _registry_snapshot(self) -> Dict[str, set[str]]:
        return {
            "processing": {extension.type for extension in self.list_processing()},
            "analysis": {extension.type for extension in self.list_analysis()},
            "plot": {extension.type for extension in self.list_plot()},
        }

    @staticmethod
    def _diff_registry_snapshot(before: Dict[str, set[str]], after: Dict[str, set[str]]) -> Dict[str, List[str]]:
        diff: Dict[str, List[str]] = {}
        for category, previous_types in before.items():
            added = sorted(after.get(category, set()) - previous_types)
            if added:
                diff[category] = added
        return diff

    @staticmethod
    def _infer_categories_from_source(path: Path) -> List[str]:
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source = path.read_text(encoding="latin-1")
        except Exception:
            return []

        categories: List[str] = []
        for category, markers in _EXTENSION_SOURCE_HINTS.items():
            if any(marker in source for marker in markers):
                categories.append(category)
        return categories

    def _scan_directory(
        self,
        directory: str | Path,
        *,
        source_kind: Optional[str] = None,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[Dict[str, Any]]]]:
        target = Path(directory)
        if not target.exists() or not target.is_dir():
            return {"loaded": [], "errors": []}, {"loaded": [], "errors": []}
        return self._scan_paths(sorted(target.glob("*.py")), source_directory=target, source_kind=source_kind)

    def _scan_paths(
        self,
        paths: Iterable[str | Path],
        *,
        source_directory: str | Path | None = None,
        source_kind: Optional[str] = None,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[Dict[str, Any]]]]:
        report = {"loaded": [], "errors": []}
        detail_report: Dict[str, List[Dict[str, Any]]] = {"loaded": [], "errors": []}
        for raw_path in paths:
            path = Path(raw_path)
            if path.name.startswith("_"):
                continue
            detail_source = source_kind or _infer_extension_source_kind(path, source_directory)
            try:
                before = self._registry_snapshot()
                self.load_from_file(path)
                after = self._registry_snapshot()
                registered = self._diff_registry_snapshot(before, after)
                categories = sorted(registered.keys())
                report["loaded"].append(str(path))
                detail_report["loaded"].append({
                    "path": str(path),
                    "directory": str(Path(source_directory) if source_directory is not None else path.parent),
                    "source": detail_source,
                    "categories": categories,
                    "extensions": registered,
                })
            except Exception as exc:
                report["errors"].append(f"{path}: {exc}")
                detail_report["errors"].append({
                    "path": str(path),
                    "directory": str(Path(source_directory) if source_directory is not None else path.parent),
                    "source": detail_source,
                    "message": str(exc),
                    "categories": self._infer_categories_from_source(path),
                })
        return report, detail_report

    def load_from_directory(self, directory: str | Path, *, source_kind: Optional[str] = None) -> Dict[str, List[str]]:
        report, detail_report = self._scan_directory(directory, source_kind=source_kind)
        self._last_load_report = {
            "loaded": list(report["loaded"]),
            "errors": list(report["errors"]),
        }
        self._last_load_details = detail_report
        return report

    def load_from_files(self, file_paths: Iterable[str | Path], *, source_kind: Optional[str] = None) -> Dict[str, List[str]]:
        report, detail_report = self._scan_paths(file_paths, source_kind=source_kind)
        self._last_load_report = {
            "loaded": list(report["loaded"]),
            "errors": list(report["errors"]),
        }
        self._last_load_details = detail_report
        return report

    def load_from_sources(
        self,
        *,
        file_paths: Iterable[str | Path] = (),
        directories: Iterable[str | Path] = (),
        file_source_kind: Optional[str] = None,
        directory_source_kind: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        report = {"loaded": [], "errors": []}
        detail_report: Dict[str, List[Dict[str, Any]]] = {"loaded": [], "errors": []}

        file_report, file_detail = self._scan_paths(file_paths, source_kind=file_source_kind)
        report["loaded"].extend(file_report["loaded"])
        report["errors"].extend(file_report["errors"])
        detail_report["loaded"].extend(file_detail["loaded"])
        detail_report["errors"].extend(file_detail["errors"])

        seen_directories: set[str] = set()
        for directory in directories:
            target = str(Path(directory).expanduser().resolve(strict=False))
            if target in seen_directories:
                continue
            seen_directories.add(target)
            directory_report, directory_detail = self._scan_directory(target, source_kind=directory_source_kind)
            report["loaded"].extend(directory_report["loaded"])
            report["errors"].extend(directory_report["errors"])
            detail_report["loaded"].extend(directory_detail["loaded"])
            detail_report["errors"].extend(directory_detail["errors"])

        self._last_load_report = {
            "loaded": list(report["loaded"]),
            "errors": list(report["errors"]),
        }
        self._last_load_details = detail_report
        return report

    def load_from_directories(self, directories: Iterable[str | Path]) -> Dict[str, List[str]]:
        return self.load_from_sources(directories=directories)

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


def _builtin_extension_id(path: str | Path) -> str:
    return Path(path).stem.strip()


def _builtin_extension_disabled_markers(disabled_extension_ids: Iterable[str] | None) -> set[str]:
    markers: set[str] = set()
    for item in disabled_extension_ids or []:
        clean = str(item or "").strip()
        if not clean:
            continue
        markers.add(clean)
        markers.add(Path(clean).name)
        markers.add(Path(clean).stem)
    return markers


def _extension_entries_by_category(registry: ExtensionRegistry) -> Dict[str, List[Dict[str, str]]]:
    return {
        "processing": [{"type": item.type, "name": item.name} for item in registry.list_processing()],
        "analysis": [{"type": item.type, "name": item.name} for item in registry.list_analysis()],
        "plot": [{"type": item.type, "name": item.name} for item in registry.list_plot()],
    }


def _inspect_extension_file(path: str | Path) -> Dict[str, List[Dict[str, str]]]:
    registry = ExtensionRegistry()
    registry.load_from_file(path)
    return _extension_entries_by_category(registry)


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
        "report_placeholders": [dict(item) for item in getattr(extension, "report_placeholders", []) or [] if isinstance(item, dict)],
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


def builtin_extension_files(base_dir: str | Path | None = None) -> List[Path]:
    directory = default_extensions_directory(base_dir)
    if not directory.exists() or not directory.is_dir():
        return []
    return [path for path in sorted(directory.glob("*.py")) if not path.name.startswith("_")]


def configured_builtin_extension_files(
    base_dir: str | Path | None = None,
    *,
    load_builtin: Optional[bool] = None,
    disabled_extension_ids: Optional[Iterable[str]] = None,
) -> List[Path]:
    from core.extension_settings import get_builtin_extension_settings

    settings_load_builtin, settings_disabled_ids = get_builtin_extension_settings()
    effective_load_builtin = settings_load_builtin if load_builtin is None else bool(load_builtin)
    effective_disabled_ids = settings_disabled_ids if disabled_extension_ids is None else list(disabled_extension_ids)
    if not effective_load_builtin:
        return []

    disabled_markers = _builtin_extension_disabled_markers(effective_disabled_ids)
    return [
        path for path in builtin_extension_files(base_dir)
        if _builtin_extension_id(path) not in disabled_markers and path.name not in disabled_markers
    ]


def list_builtin_extension_specs(base_dir: str | Path | None = None) -> List[Dict[str, Any]]:
    from core.extension_settings import get_builtin_extension_settings

    load_builtin, disabled_extension_ids = get_builtin_extension_settings()
    disabled_markers = _builtin_extension_disabled_markers(disabled_extension_ids)
    specs: List[Dict[str, Any]] = []
    for path in builtin_extension_files(base_dir):
        categories: List[str] = []
        entries_by_category: Dict[str, List[Dict[str, str]]] = {}
        load_error = ""
        try:
            entries_by_category = _inspect_extension_file(path)
            categories = [category for category, entries in entries_by_category.items() if entries]
        except Exception as exc:
            load_error = str(exc)
            categories = ExtensionRegistry._infer_categories_from_source(Path(path))

        discovered_entries = [
            entry
            for category in categories
            for entry in entries_by_category.get(category, [])
        ]
        names = [entry["name"] for entry in discovered_entries if entry.get("name")]
        type_ids = [entry["type"] for entry in discovered_entries if entry.get("type")]
        specs.append({
            "id": _builtin_extension_id(path),
            "file_name": Path(path).name,
            "name": " / ".join(names) if names else _builtin_extension_id(path),
            "categories": categories,
            "category_labels": [_EXTENSION_CATEGORY_LABELS.get(category, category) for category in categories],
            "type_ids": type_ids,
            "path": str(path),
            "enabled": bool(load_builtin) and _builtin_extension_id(path) not in disabled_markers and Path(path).name not in disabled_markers,
            "load_error": load_error,
        })
    return specs


def configured_extension_directories(
    base_dir: str | Path | None = None,
    external_dir: str | Path | None = None,
) -> List[Path]:
    from core.extension_settings import get_builtin_extension_settings, get_external_extensions_directory

    load_builtin, _disabled_extension_ids = get_builtin_extension_settings()
    directories: List[Path] = []
    if load_builtin:
        directories.append(default_extensions_directory(base_dir))
    directories.append(Path(external_dir) if external_dir is not None else get_external_extensions_directory())

    resolved: List[Path] = []
    seen: set[str] = set()
    for directory in directories:
        target = Path(directory).expanduser().resolve(strict=False)
        marker = str(target)
        if marker in seen:
            continue
        seen.add(marker)
        resolved.append(target)
    return resolved


def load_builtin_extensions(directory: str | Path | None = None) -> Dict[str, List[str]]:
    return extension_registry.load_from_directory(default_extensions_directory(directory), source_kind="builtin")


def reload_builtin_extensions(directory: str | Path | None = None) -> Dict[str, List[str]]:
    extension_registry.clear()
    return load_builtin_extensions(directory)


def load_configured_extensions(
    base_dir: str | Path | None = None,
    external_dir: str | Path | None = None,
) -> Dict[str, List[str]]:
    from core.extension_settings import get_external_extensions_directory

    builtin_files = configured_builtin_extension_files(base_dir)
    external_target = Path(external_dir) if external_dir is not None else get_external_extensions_directory()
    return extension_registry.load_from_sources(
        file_paths=builtin_files,
        directories=[external_target],
        file_source_kind="builtin",
        directory_source_kind="external",
    )


def reload_configured_extensions(
    base_dir: str | Path | None = None,
    external_dir: str | Path | None = None,
) -> Dict[str, List[str]]:
    extension_registry.clear()
    return load_configured_extensions(base_dir, external_dir)


def get_last_extension_load_report() -> Dict[str, List[str]]:
    return extension_registry.get_last_load_report()


def get_last_extension_load_details(category: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    details = extension_registry.get_last_load_details()
    if category is None:
        return {
            "loaded": [_annotate_extension_detail(item) for item in details.get("loaded", [])],
            "errors": [_annotate_extension_detail(item) for item in details.get("errors", [])],
        }

    normalized = category.strip().lower()
    return {
        "loaded": [
            _annotate_extension_detail(item) for item in details.get("loaded", [])
            if normalized in item.get("categories", [])
        ],
        "errors": [
            _annotate_extension_detail(item) for item in details.get("errors", [])
            if normalized in item.get("categories", [])
        ],
    }


def get_extension_load_status(category: Optional[str] = None) -> Dict[str, Any]:
    normalized = category.strip().lower() if category else None
    details = get_last_extension_load_details(normalized)
    source_summary = _summarize_extension_sources(details, normalized)

    if normalized == "processing":
        registered_count = len(extension_registry.list_processing())
    elif normalized == "analysis":
        registered_count = len(extension_registry.list_analysis())
    elif normalized == "plot":
        registered_count = len(extension_registry.list_plot())
    else:
        registered_count = sum([
            len(extension_registry.list_processing()),
            len(extension_registry.list_analysis()),
            len(extension_registry.list_plot()),
        ])

    return {
        "category": normalized,
        "label": _EXTENSION_CATEGORY_LABELS.get(normalized, "扩展"),
        "registered_count": registered_count,
        "loaded_file_count": len(details.get("loaded", [])),
        "error_count": len(details.get("errors", [])),
        "source_summary": source_summary,
        "details": details,
    }


def format_extension_load_report(category: Optional[str] = None) -> str:
    status = get_extension_load_status(category)
    details = status["details"]
    source_summary = status.get("source_summary") or {}
    lines = [
        f"{status['label']}状态",
        f"已注册扩展: {status['registered_count']}{_format_source_split(source_summary.get('loaded_extension_counts', {}))}",
        f"成功扫描文件: {status['loaded_file_count']}{_format_source_split(source_summary.get('loaded_file_counts', {}))}",
        f"失败文件: {status['error_count']}{_format_source_split(source_summary.get('error_file_counts', {}))}",
    ]

    if details.get("loaded"):
        lines.append("")
        lines.append("成功扫描文件:")
        for item in details["loaded"]:
            lines.append(f"- {Path(item['path']).name} [{item.get('source_label', '外部')}]")
            extension_parts = []
            for detail_category, type_ids in sorted(item.get("extensions", {}).items()):
                category_label = _EXTENSION_CATEGORY_LABELS.get(detail_category, detail_category)
                extension_parts.append(f"{category_label}: {', '.join(type_ids)}")
            if extension_parts:
                lines.append(f"  {' | '.join(extension_parts)}")

    if details.get("errors"):
        lines.append("")
        lines.append("失败文件:")
        for item in details["errors"]:
            category_text = "、".join(_EXTENSION_CATEGORY_LABELS.get(cat, cat) for cat in item.get("categories", []))
            lines.append(f"- {Path(item['path']).name} [{item.get('source_label', '外部')}]: {item.get('message', '')}")
            if category_text:
                lines.append(f"  推断分类: {category_text}")

    if len(lines) == 4:
        lines.append("")
        lines.append("最近一次扫描没有记录到任何扩展文件。")
    return "\n".join(lines)


def register_processing_extension(extension: ProcessingExtension) -> None:
    extension_registry.register_processing(extension)


def register_analysis_extension(extension: AnalysisExtension) -> None:
    extension_registry.register_analysis(extension)


def register_plot_extension(extension: PlotExtension) -> None:
    extension_registry.register_plot(extension)