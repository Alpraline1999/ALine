from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast, Dict, Iterable, List, Optional

from core.extension_registry import (
    _format_source_split,
    _normalize_external_directory_inputs,
    configured_builtin_extension_files,
    configured_external_extension_files,
    extension_registry,
)
from core.extension_registry import _annotate_extension_detail
from core.extension_registry import _summarize_extension_sources
from core.extension_validator import ExtensionValidator
from core import ALINE_VERSION


class LoadReport:
    def __init__(self) -> None:
        self.success: List[Dict[str, Any]] = []
        self.errors: List[str] = []

    @property
    def total_loaded(self) -> int:
        return len(self.success)

    @property
    def total_failed(self) -> int:
        return len(self.errors)


def scan_directory(directory: str) -> List[str]:
    target = Path(directory).expanduser().resolve(strict=False)
    if not target.exists() or not target.is_dir():
        return []

    from core.extension_definition import _NON_EXTENSION_MODULE_FILENAMES
    files: List[str] = []
    for path in sorted(target.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        if path.name in _NON_EXTENSION_MODULE_FILENAMES:
            continue
        files.append(str(path))
    return files


def _import_extension_module(filepath: str) -> Optional[ModuleType]:
    module_name = Path(filepath).stem
    if module_name in sys.modules:
        del sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _call_register_function(module: ModuleType, registry: Any) -> List[str]:
    errors: List[str] = []
    if not hasattr(module, "register_extensions"):
        errors.append("module missing register_extensions(registry)")
        return errors
    try:
        module.register_extensions(registry)
    except Exception as e:
        errors.append(f"register_extensions failed: {e}")
    return errors


def _load_file(filepath: str, source_kind: str, report: LoadReport) -> None:
    try:
        before = extension_registry._registry_snapshot()
        extension_registry.load_from_file(filepath)
        after = extension_registry._registry_snapshot()
        registered = extension_registry._diff_registry_snapshot(before, after)
        report.success.append({
            "file": filepath,
            "module": Path(filepath).stem,
            "source_kind": source_kind,
            "extensions": registered,
        })
    except Exception as exc:
        report.errors.append(f"{filepath}: {exc}")


def _build_detail_report(report: LoadReport, default_dir: str) -> Dict[str, List[Dict[str, Any]]]:
    from core.extension_registry import ExtensionRegistry

    details: Dict[str, List[Dict[str, Any]]] = {"loaded": [], "errors": []}
    for item in report.success:
        details["loaded"].append({
            "path": item["file"],
            "directory": str(Path(item["file"]).parent),
            "source": item.get("source_kind", "builtin"),
            "categories": sorted(item.get("extensions", {}).keys()),
            "extensions": item.get("extensions", {}),
        })
    for err in report.errors:
        path_part = err.split(":")[0] if ":" in err else err
        categories: List[str] = []
        candidate_path = Path(path_part)
        if candidate_path.exists():
            categories = ExtensionRegistry._infer_categories_from_source(candidate_path)
        details["errors"].append({
            "path": path_part if candidate_path.exists() else default_dir,
            "directory": str(candidate_path.parent) if candidate_path.exists() else default_dir,
            "source": "builtin",
            "message": err,
            "categories": categories,
        })
    return details


def _load_report_to_dict(report: LoadReport) -> Dict[str, List[str]]:
    return {"loaded": [item["file"] for item in report.success], "errors": list(report.errors)}


def _wrap_external_extensions_with_sandbox() -> None:
    from core.extension_definition import normalize_extension_source_kind
    from core.extension_sandbox import SandboxedExtensionRunner
    from core.extension_settings import get_external_extension_sandbox_enabled

    if not get_external_extension_sandbox_enabled():
        return

    categories: dict[Any, str] = {
        extension_registry._processing: "processing",
        extension_registry._analysis: "analysis",
        extension_registry._digitize: "digitize",
    }
    for store, _category in categories.items():
        store_dict = cast(dict[str, Any], store)
        for type_id, ext in list(store_dict.items()):
            if normalize_extension_source_kind(getattr(ext, "source_kind", "builtin")) != "external":
                continue
            original_handler = ext.handler

            def _make_wrapper(handler: Any) -> Any:
                def sandbox_wrapper(lines: Any, params: Any) -> Any:
                    return SandboxedExtensionRunner.run(handler, lines, params)
                return sandbox_wrapper

            object.__setattr__(ext, "handler", _make_wrapper(original_handler))


def _check_extension_compatibility(report: LoadReport) -> None:
    categories: dict[str, Any] = {
        "processing": extension_registry._processing,
        "analysis": extension_registry._analysis,
        "plot": extension_registry._plot,
        "digitize": extension_registry._digitize,
    }
    for category, store in categories.items():
        store_dict = cast(dict[str, Any], store)
        for type_id, ext in list(store_dict.items()):
            api_version = getattr(ext, "aline_api_version", "")
            result = ExtensionValidator.check_compatibility(api_version, ALINE_VERSION)
            if result == "incompatible":
                report.errors.append(
                    f"扩展 '{ext.name}' ({category}) 需要 ALine {api_version}，"
                    f"当前版本 {ALINE_VERSION}，已禁用"
                )
                store_dict.pop(type_id, None)
            elif result == "warning":
                report.errors.append(
                    f"扩展 '{ext.name}' ({category}) 版本声明解析失败: {api_version}"
                )


def _load_from_files(builtin_files: Iterable[str], external_files: Iterable[str]) -> LoadReport:
    report = LoadReport()
    for path in builtin_files:
        _load_file(str(path), source_kind="builtin", report=report)
    for path in external_files:
        _load_file(str(path), source_kind="external", report=report)
    _wrap_external_extensions_with_sandbox()
    _check_extension_compatibility(report)
    extension_registry._last_load_report = _load_report_to_dict(report)
    default_dir = (
        str(Path(list(builtin_files)[0]).parent) if builtin_files
        else str(Path(list(external_files)[0]).parent) if external_files
        else ""
    )
    extension_registry._last_load_details = _build_detail_report(report, default_dir)
    return report


def load_configured_extensions(
    base_dir: str | Path | None = None,
    external_dir: str | Path | Iterable[str | Path] | None = None,
) -> Dict[str, List[str]]:
    builtin_files = [str(p) for p in configured_builtin_extension_files(base_dir)]
    external_dirs = _normalize_external_directory_inputs(external_dir)
    external_files_list: List[str] = []
    for d in external_dirs:
        external_files_list.extend([str(p) for p in configured_external_extension_files(d)])
    return _load_report_to_dict(_load_from_files(builtin_files, external_files_list))


def reload_extensions(
    base_dir: str | Path | None = None,
    external_dir: str | Path | None = None,
) -> Dict[str, List[str]]:
    extension_registry._processing.clear()
    extension_registry._analysis.clear()
    extension_registry._plot.clear()
    extension_registry._digitize.clear()
    return load_configured_extensions(base_dir, external_dir)


def load_builtin_extensions(directory: str | Path | None = None) -> Dict[str, List[str]]:
    from core.extension_registry import default_extensions_directory
    builtin_dir = str(default_extensions_directory(directory))
    report = LoadReport()
    for filepath in scan_directory(builtin_dir):
        _load_file(filepath, source_kind="builtin", report=report)
    extension_registry._last_load_report = _load_report_to_dict(report)
    extension_registry._last_load_details = _build_detail_report(report, builtin_dir)
    return _load_report_to_dict(report)


def reload_builtin_extensions(directory: str | Path | None = None) -> Dict[str, List[str]]:
    extension_registry._processing.clear()
    extension_registry._analysis.clear()
    extension_registry._plot.clear()
    extension_registry._digitize.clear()
    return load_builtin_extensions(directory)


def ensure_configured_extensions_loaded(
    base_dir: str | Path | None = None,
    external_dir: str | Path | Iterable[str | Path] | None = None,
) -> Dict[str, List[str]]:
    if any((
        extension_registry.list_processing(),
        extension_registry.list_analysis(),
        extension_registry.list_plot(),
        extension_registry.list_digitize(),
    )):
        return extension_registry.get_last_load_report()
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
            _annotate_extension_detail(item)
            for item in details.get("loaded", [])
            if normalized in item.get("categories", [])
        ],
        "errors": [
            _annotate_extension_detail(item)
            for item in details.get("errors", [])
            if normalized in item.get("categories", [])
        ],
    }


def get_extension_load_status(category: Optional[str] = None) -> Dict[str, Any]:
    from core.extension_definition import _EXTENSION_CATEGORY_LABELS
    from core.i18n import _

    normalized = category.strip().lower() if category else None
    details = get_last_extension_load_details(normalized)
    source_summary = _summarize_extension_sources(details, normalized)
    scanned_registered_count = sum(source_summary.get("loaded_extension_counts", {}).values())

    def _listed_count(items: List[Any]) -> int:
        return len([item for item in items if bool(getattr(item, "listed", True))])

    if details.get("loaded") or details.get("errors"):
        registered_count = scanned_registered_count
    elif normalized == "processing":
        registered_count = _listed_count(extension_registry.list_processing())
    elif normalized == "analysis":
        registered_count = _listed_count(extension_registry.list_analysis())
    elif normalized == "plot":
        registered_count = _listed_count(extension_registry.list_plot())
    elif normalized == "digitize":
        registered_count = _listed_count(extension_registry.list_digitize())
    else:
        registered_count = sum([
            _listed_count(extension_registry.list_processing()),
            _listed_count(extension_registry.list_analysis()),
            _listed_count(extension_registry.list_plot()),
            _listed_count(extension_registry.list_digitize()),
        ])

    return {
        "category": normalized,
        "label": _EXTENSION_CATEGORY_LABELS.get(normalized, _("扩展")) if normalized else _("扩展"),
        "registered_count": registered_count,
        "loaded_file_count": len(details.get("loaded", [])),
        "error_count": len(details.get("errors", [])),
        "source_summary": source_summary,
        "details": details,
    }


def format_extension_load_report(category: Optional[str] = None) -> str:
    from core.extension_definition import _EXTENSION_CATEGORY_LABELS
    from core.i18n import _

    status = get_extension_load_status(category)
    details = status["details"]
    source_summary = status.get("source_summary") or {}
    lines = [
        _("{}状态").format(status['label']),
        _("已注册扩展: {}").format(status['registered_count']) + _format_source_split(source_summary.get('loaded_extension_counts', {})),
        _("成功扫描文件: {}").format(status['loaded_file_count']) + _format_source_split(source_summary.get('loaded_file_counts', {})),
        _("失败文件: {}").format(status['error_count']) + _format_source_split(source_summary.get('error_file_counts', {})),
    ]

    if details.get("loaded"):
        lines.append("")
        lines.append(_("成功扫描文件:"))
        for item in details["loaded"]:
            source_label = item.get('source_label', _('外部'))
            lines.append(_("- {} [{}]").format(Path(item['path']).name, source_label))
            extension_parts = []
            for detail_category, type_ids in sorted(item.get("extensions", {}).items()):
                category_label = _EXTENSION_CATEGORY_LABELS.get(detail_category, detail_category)
                extension_parts.append(_("{}: {}").format(category_label, ', '.join(type_ids)))
            if extension_parts:
                lines.append(_("  {}").format(' | '.join(extension_parts)))

    if details.get("errors"):
        lines.append("")
        lines.append(_("失败文件:"))
        for item in details["errors"]:
            source_label = item.get('source_label', _('外部'))
            separator = "、"
            category_text = separator.join(
                _EXTENSION_CATEGORY_LABELS.get(str(cat), str(cat))
                for cat in item.get("categories", [])
            )
            lines.append(
                _("- {} [{}]: {}").format(Path(item['path']).name, source_label, item.get('message', ''))
            )
            if category_text:
                lines.append(_("  推断分类: {}").format(category_text))

    if len(lines) == 4:
        lines.append("")
        lines.append(_("最近一次扫描没有记录到任何扩展文件。"))
    return "\n".join(lines)
