from __future__ import annotations

"""扩展注册表 — 管理所有注册的四类扩展（processing / analysis / plot / digitize）。

提供注册、查询、迭代、加载和冲突检测功能。
同一个 type 在相同 source_kind 下可被后注册覆盖，异源保留先注册者。
"""

import copy
import hashlib
from importlib import util as importlib_util
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from core.extension_definition import (
    AnalysisExtension,
    DEFAULT_EXTENSION_VERSION,
    DigitizeExtension,
    PlotExtension,
    ProcessingExtension,
    _EXTENSION_CATEGORY_LABELS,
    _EXTENSION_ORIGIN_LABELS,
    _EXTENSION_SOURCE_HINTS,
    _EXTENSION_SOURCE_LABELS,
    _EXTENSION_TOOL_TIER_LABELS,
    _NON_EXTENSION_MODULE_FILENAMES,
    _extension_name_key,
    normalize_extension_lines_number,
    normalize_extension_tool_tier,
    normalize_extension_version,
)


# ---------------------------------------------------------------------------
#  Helper functions (extracted from extension_api.py)
# ---------------------------------------------------------------------------

def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def default_extensions_directory(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    return Path(__file__).resolve().parent.parent / "extensions"


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


def _extension_python_files(directory: str | Path) -> List[Path]:
    target = Path(directory)
    if not target.exists() or not target.is_dir():
        return []
    return [
        path for path in sorted(target.rglob("*.py"))
        if not path.name.startswith("_")
        and path.name not in _NON_EXTENSION_MODULE_FILENAMES
    ]


# ---------------------------------------------------------------------------
#  ExtensionRegistry
# ---------------------------------------------------------------------------

class ExtensionRegistry:
    """扩展注册表。

    按四类扩展分四本字典存储，支持按 type 查询、列表迭代和按目录/文件加载。
    同一个 type 在相同 source_kind 下可被后注册的扩展覆盖；
    不同 source_kind 的 type 冲突保留先注册的扩展。
    """

    def __init__(self) -> None:
        self._processing: Dict[str, ProcessingExtension] = {}
        self._analysis: Dict[str, AnalysisExtension] = {}
        self._plot: Dict[str, PlotExtension] = {}
        self._digitize: Dict[str, DigitizeExtension] = {}
        self._last_load_report: Dict[str, List[str]] = {"loaded": [], "errors": []}
        self._last_load_details: Dict[str, List[Dict[str, Any]]] = {"loaded": [], "errors": []}

    # -- lifecycle ---------------------------------------------------------

    def clear(self) -> None:
        self._processing.clear()
        self._analysis.clear()
        self._plot.clear()
        self._digitize.clear()
        self._last_load_report = {"loaded": [], "errors": []}
        self._last_load_details = {"loaded": [], "errors": []}

    def get_last_load_report(self) -> Dict[str, List[str]]:
        return {
            "loaded": list(self._last_load_report.get("loaded", [])),
            "errors": list(self._last_load_report.get("errors", [])),
        }

    def get_last_load_details(self) -> Dict[str, List[Dict[str, Any]]]:
        return copy.deepcopy(self._last_load_details)

    def _registry_state(self) -> Dict[str, Dict[str, Any]]:
        return {
            "processing": dict(self._processing),
            "analysis": dict(self._analysis),
            "plot": dict(self._plot),
            "digitize": dict(self._digitize),
        }

    def _restore_registry_state(self, state: Dict[str, Dict[str, Any]]) -> None:
        self._processing = dict(state.get("processing", {}))
        self._analysis = dict(state.get("analysis", {}))
        self._plot = dict(state.get("plot", {}))
        self._digitize = dict(state.get("digitize", {}))

    # -- registration ------------------------------------------------------

    @staticmethod
    def _ensure_unique_identity(category: str, mapping: Dict[str, Any], extension: Any) -> None:
        from core.extension_validator import _validate_extension_contract

        type_id = str(getattr(extension, "type", "") or "").strip()
        if not type_id:
            raise ValueError(f"{category} extension type is required")
        name = str(getattr(extension, "name", "") or "").strip()
        if not name:
            raise ValueError(f"{category} extension name is required")
        normalize_extension_version(
            getattr(extension, "version", DEFAULT_EXTENSION_VERSION)
        )
        if type_id in mapping:
            raise ValueError(f"重复的 {category} 扩展 type: {type_id}")
        duplicate_name = next(
            (
                item
                for item in mapping.values()
                if _extension_name_key(getattr(item, "name", ""))
                == _extension_name_key(name)
            ),
            None,
        )
        if duplicate_name is not None:
            raise ValueError(f"重复的 {category} 扩展 name: {name}")
        _validate_extension_contract(category, extension)

    def register_processing(self, extension: ProcessingExtension) -> None:
        self._ensure_unique_identity("processing", self._processing, extension)
        self._processing[extension.type.strip()] = extension

    def register_analysis(self, extension: AnalysisExtension) -> None:
        self._ensure_unique_identity("analysis", self._analysis, extension)
        self._analysis[extension.type.strip()] = extension

    def register_plot(self, extension: PlotExtension) -> None:
        self._ensure_unique_identity("plot", self._plot, extension)
        self._plot[extension.type.strip()] = extension

    def register_digitize(self, extension: DigitizeExtension) -> None:
        self._ensure_unique_identity("digitize", self._digitize, extension)
        self._digitize[extension.type.strip()] = extension

    # -- unregistration ----------------------------------------------------

    def unregister_processing(self, type_id: str) -> None:
        self._processing.pop(type_id, None)

    def unregister_analysis(self, type_id: str) -> None:
        self._analysis.pop(type_id, None)

    def unregister_plot(self, type_id: str) -> None:
        self._plot.pop(type_id, None)

    def unregister_digitize(self, type_id: str) -> None:
        self._digitize.pop(type_id, None)

    # -- query -------------------------------------------------------------

    def get_processing(self, type_id: str) -> Optional[ProcessingExtension]:
        return self._processing.get(type_id)

    def get_analysis(self, type_id: str) -> Optional[AnalysisExtension]:
        return self._analysis.get(type_id)

    def get_plot(self, type_id: str) -> Optional[PlotExtension]:
        return self._plot.get(type_id)

    def get_digitize(self, type_id: str) -> Optional[DigitizeExtension]:
        return self._digitize.get(type_id)

    def list_processing(self) -> List[ProcessingExtension]:
        return list(self._processing.values())

    def list_analysis(self) -> List[AnalysisExtension]:
        return list(self._analysis.values())

    def list_plot(self) -> List[PlotExtension]:
        return list(self._plot.values())

    def list_digitize(self) -> List[DigitizeExtension]:
        return list(self._digitize.values())

    # -- snapshot helpers for load scanning --------------------------------

    def _registry_snapshot(self) -> Dict[str, set[str]]:
        return {
            "processing": {ext.type for ext in self.list_processing()},
            "analysis": {ext.type for ext in self.list_analysis()},
            "plot": {ext.type for ext in self.list_plot()},
            "digitize": {ext.type for ext in self.list_digitize()},
        }

    @staticmethod
    def _diff_registry_snapshot(
        before: Dict[str, set[str]],
        after: Dict[str, set[str]],
    ) -> Dict[str, List[str]]:
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

    # -- file / directory scanning -----------------------------------------

    def _scan_directory(
        self,
        directory: str | Path,
        *,
        source_kind: Optional[str] = None,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[Dict[str, Any]]]]:
        target = Path(directory)
        if not target.exists() or not target.is_dir():
            return {"loaded": [], "errors": []}, {"loaded": [], "errors": []}
        return self._scan_paths(
            _extension_python_files(target),
            source_directory=target,
            source_kind=source_kind,
        )

    def _scan_paths(
        self,
        paths: Iterable[str | Path],
        *,
        source_directory: str | Path | None = None,
        source_kind: Optional[str] = None,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[Dict[str, Any]]]]:
        report: Dict[str, List[str]] = {"loaded": [], "errors": []}
        detail_report: Dict[str, List[Dict[str, Any]]] = {"loaded": [], "errors": []}
        for raw_path in paths:
            path = Path(raw_path)
            if path.name.startswith("_") or path.name in _NON_EXTENSION_MODULE_FILENAMES:
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

    # -- bulk load ---------------------------------------------------------

    def load_from_directory(
        self,
        directory: str | Path,
        *,
        source_kind: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        report, detail_report = self._scan_directory(directory, source_kind=source_kind)
        self._last_load_report = {
            "loaded": list(report["loaded"]),
            "errors": list(report["errors"]),
        }
        self._last_load_details = detail_report
        return report

    def load_from_files(
        self,
        file_paths: Iterable[str | Path],
        *,
        source_kind: Optional[str] = None,
    ) -> Dict[str, List[str]]:
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
        report: Dict[str, List[str]] = {"loaded": [], "errors": []}
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
            directory_report, directory_detail = self._scan_directory(
                target, source_kind=directory_source_kind,
            )
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
        before_state = self._registry_state()
        try:
            spec.loader.exec_module(module)
            register = getattr(module, "register_extensions", None)
            if not callable(register):
                raise ValueError(f"扩展文件缺少 register_extensions(registry) 入口: {path}")
            register(self)
        except Exception:
            self._restore_registry_state(before_state)
            raise
        return module

    @staticmethod
    def _module_name_for_path(path: Path) -> str:
        digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
        return f"aline_extension_{path.stem}_{digest}"

    # -- introspection helpers (new) ---------------------------------------

    def detect_conflicts(self) -> List[str]:
        """检测 type 冲突，返回冲突描述列表。

        当同一个 type 出现在多个扩展类别中（如相同 type_id 被同时注册为
        processing 和 analysis），或者同类别下不同 source_kind 之间产生
        覆盖关系时视为冲突。
        """
        conflicts: List[str] = []

        # 跨类别 type 冲突
        all_types: Dict[str, List[str]] = {}
        for category, mapping in (
            ("processing", self._processing),
            ("analysis", self._analysis),
            ("plot", self._plot),
            ("digitize", self._digitize),
        ):
            for type_id in mapping:
                all_types.setdefault(type_id, []).append(category)

        for type_id, categories in all_types.items():
            if len(categories) > 1:
                conflicts.append(
                    f"扩展 type '{type_id}' 同时注册在: {', '.join(categories)}"
                )

        return conflicts

    def get_categories(self) -> Dict[str, list]:
        """返回四类扩展的字典映射。"""
        return {
            "processing": list(self._processing.values()),
            "analysis": list(self._analysis.values()),
            "plot": list(self._plot.values()),
            "digitize": list(self._digitize.values()),
        }

    def iter_extensions(self) -> Iterator[Any]:
        """遍历所有已注册扩展。"""
        for ext in self._processing.values():
            yield ext
        for ext in self._analysis.values():
            yield ext
        for ext in self._plot.values():
            yield ext
        for ext in self._digitize.values():
            yield ext

    def get_total_count(self) -> int:
        return (
            len(self._processing)
            + len(self._analysis)
            + len(self._plot)
            + len(self._digitize)
        )

    def get_processing_types(self) -> List[str]:
        return list(self._processing.keys())

    def get_analysis_types(self) -> List[str]:
        return list(self._analysis.keys())

    def get_plot_types(self) -> List[str]:
        return list(self._plot.keys())

    def get_digitize_types(self) -> List[str]:
        return list(self._digitize.keys())


# 全局单例
extension_registry = ExtensionRegistry()


# ---------------------------------------------------------------------------
#  Registry helper functions migrated from extension_api.py
# ---------------------------------------------------------------------------


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


def _builtin_extension_id(path: str | Path) -> str:
    return Path(path).stem.strip()


def _extension_file_id(path: str | Path) -> str:
    return Path(path).stem.strip()


def _extension_disabled_markers(disabled_extension_ids: Iterable[str] | None) -> set[str]:
    markers: set[str] = set()
    for item in disabled_extension_ids or []:
        clean = str(item or "").strip()
        if not clean:
            continue
        markers.add(clean)
        markers.add(Path(clean).name)
        markers.add(Path(clean).stem)
    return markers


def _builtin_extension_disabled_markers(disabled_extension_ids: Iterable[str] | None) -> set[str]:
    return _extension_disabled_markers(disabled_extension_ids)


def _extension_entries_by_category(registry: ExtensionRegistry) -> Dict[str, List[Dict[str, str]]]:
    return {
        "processing": [
            {"type": item.type, "name": item.name, "tool_tier": item.tool_tier}
            for item in registry.list_processing()
        ],
        "analysis": [
            {"type": item.type, "name": item.name, "tool_tier": item.tool_tier}
            for item in registry.list_analysis()
        ],
        "plot": [
            {"type": item.type, "name": item.name, "tool_tier": item.tool_tier}
            for item in registry.list_plot()
        ],
        "digitize": [
            {"type": item.type, "name": item.name, "tool_tier": item.tool_tier}
            for item in registry.list_digitize()
        ],
    }


def _inspect_extension_file(path: str | Path) -> Dict[str, List[Dict[str, str]]]:
    registry = ExtensionRegistry()
    registry.load_from_file(path)
    return _extension_entries_by_category(registry)


def builtin_extension_files(base_dir: str | Path | None = None) -> List[Path]:
    directory = default_extensions_directory(base_dir)
    return [
        path
        for path in _extension_python_files(directory)
        if not path.name.endswith("_demo.py")
    ]


def _normalize_external_directory_inputs(
    directory: str | Path | Iterable[str | Path] | None,
) -> List[Path]:
    from core.extension_settings import get_external_extensions_directories

    if directory is None:
        candidates = get_external_extensions_directories()
    elif isinstance(directory, (str, Path)):
        candidates = [Path(directory)]
    else:
        candidates = [Path(item) for item in directory]

    resolved: List[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        target = Path(candidate).expanduser().resolve(strict=False)
        marker = str(target)
        if marker in seen:
            continue
        seen.add(marker)
        resolved.append(target)
    return resolved


def external_extension_files(
    directory: str | Path | Iterable[str | Path] | None = None,
) -> List[Path]:
    files: List[Path] = []
    seen: set[str] = set()
    for target in _normalize_external_directory_inputs(directory):
        for path in _extension_python_files(target):
            marker = str(path.expanduser().resolve(strict=False))
            if marker in seen:
                continue
            seen.add(marker)
            files.append(path)
    return files


def configured_builtin_extension_files(
    base_dir: str | Path | None = None,
    *,
    load_builtin: Optional[bool] = None,
    disabled_extension_ids: Optional[Iterable[str]] = None,
) -> List[Path]:
    from core.extension_settings import get_builtin_extension_settings

    settings_load_builtin, settings_disabled_ids = get_builtin_extension_settings()
    effective_load_builtin = (
        settings_load_builtin if load_builtin is None else bool(load_builtin)
    )
    effective_disabled_ids = (
        settings_disabled_ids if disabled_extension_ids is None else list(disabled_extension_ids)
    )
    if not effective_load_builtin:
        return []

    disabled_markers = _builtin_extension_disabled_markers(effective_disabled_ids)
    return [
        path
        for path in builtin_extension_files(base_dir)
        if _builtin_extension_id(path) not in disabled_markers
        and path.name not in disabled_markers
    ]


def configured_external_extension_files(
    directory: str | Path | Iterable[str | Path] | None = None,
    *,
    load_external: Optional[bool] = None,
    disabled_extension_ids: Optional[Iterable[str]] = None,
) -> List[Path]:
    from core.extension_settings import get_external_extension_settings

    settings_load_external, settings_disabled_ids = get_external_extension_settings()
    effective_load_external = (
        settings_load_external if load_external is None else bool(load_external)
    )
    effective_disabled_ids = (
        settings_disabled_ids if disabled_extension_ids is None else list(disabled_extension_ids)
    )
    if not effective_load_external:
        return []

    disabled_markers = _extension_disabled_markers(effective_disabled_ids)
    return [
        path
        for path in external_extension_files(directory)
        if _extension_file_id(path) not in disabled_markers
        and path.name not in disabled_markers
    ]


def _build_extension_specs(
    file_paths: Iterable[Path],
    *,
    source_kind: str,
    enabled_markers: set[str],
    load_enabled: bool,
) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for path in file_paths:
        categories: List[str] = []
        entries_by_category: Dict[str, List[Dict[str, str]]] = {}
        load_error = ""
        try:
            entries_by_category = _inspect_extension_file(path)
            categories = [
                category for category, entries in entries_by_category.items() if entries
            ]
        except Exception as exc:
            load_error = str(exc)
            categories = ExtensionRegistry._infer_categories_from_source(Path(path))

        names_by_category = {
            category: [entry["name"] for entry in entries if entry.get("name")]
            for category, entries in entries_by_category.items()
        }
        type_ids_by_category = {
            category: [entry["type"] for entry in entries if entry.get("type")]
            for category, entries in entries_by_category.items()
        }
        discovered_entries = [
            entry for entries in entries_by_category.values() for entry in entries
        ]
        names = [entry["name"] for entry in discovered_entries if entry.get("name")]
        type_ids = [entry["type"] for entry in discovered_entries if entry.get("type")]
        tool_tiers = sorted(
            {
                str(entry.get("tool_tier") or "tool")
                for entry in discovered_entries
                if entry.get("tool_tier")
            }
        )
        spec_id = _extension_file_id(path)
        specs.append(
            {
                "id": spec_id,
                "source": source_kind,
                "source_label": _EXTENSION_SOURCE_LABELS.get(source_kind, source_kind),
                "file_name": Path(path).name,
                "name": " / ".join(names) if names else spec_id,
                "categories": categories,
                "category_labels": [
                    _EXTENSION_CATEGORY_LABELS.get(category, category)
                    for category in categories
                ],
                "type_ids": type_ids,
                "tool_tiers": tool_tiers,
                "tool_tier_labels": [
                    _EXTENSION_TOOL_TIER_LABELS.get(tier, tier) for tier in tool_tiers
                ],
                "entries_by_category": entries_by_category,
                "names_by_category": names_by_category,
                "type_ids_by_category": type_ids_by_category,
                "path": str(path),
                "enabled": bool(load_enabled)
                and spec_id not in enabled_markers
                and Path(path).name not in enabled_markers,
                "load_error": load_error,
            }
        )
    return specs


def list_builtin_extension_specs(
    base_dir: str | Path | None = None,
) -> List[Dict[str, Any]]:
    from core.extension_settings import get_builtin_extension_settings

    load_builtin, disabled_extension_ids = get_builtin_extension_settings()
    disabled_markers = _builtin_extension_disabled_markers(disabled_extension_ids)
    return _build_extension_specs(
        builtin_extension_files(base_dir),
        source_kind="builtin",
        enabled_markers=disabled_markers,
        load_enabled=load_builtin,
    )


def list_external_extension_specs(
    directory: str | Path | Iterable[str | Path] | None = None,
) -> List[Dict[str, Any]]:
    from core.extension_settings import get_external_extension_settings

    load_external, disabled_extension_ids = get_external_extension_settings()
    disabled_markers = _extension_disabled_markers(disabled_extension_ids)
    return _build_extension_specs(
        external_extension_files(directory),
        source_kind="external",
        enabled_markers=disabled_markers,
        load_enabled=load_external,
    )


def configured_extension_directories(
    base_dir: str | Path | None = None,
    external_dir: str | Path | Iterable[str | Path] | None = None,
) -> List[Path]:
    from core.extension_settings import get_builtin_extension_settings
    from core.extension_settings import get_external_extension_settings

    load_builtin, _disabled_extension_ids = get_builtin_extension_settings()
    load_external, _disabled_external_ids = get_external_extension_settings()
    directories: List[Path] = []
    if load_builtin:
        directories.append(default_extensions_directory(base_dir))
    if load_external:
        directories.extend(_normalize_external_directory_inputs(external_dir))

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
