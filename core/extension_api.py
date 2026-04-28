from __future__ import annotations

from dataclasses import dataclass, field
from importlib import util as importlib_util
import inspect
import copy
from pathlib import Path
import re
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, cast
import hashlib

from extensions.processing.extension_tools import normalize_line, series_payloads_to_lines


XY = Tuple[List[float], List[float]]
DEFAULT_EXTENSION_VERSION = "1.0.0"
_EXTENSION_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")

_EXTENSION_CATEGORY_LABELS = {
    "processing": "处理扩展",
    "analysis": "分析扩展",
    "plot": "绘图扩展",
    "digitize": "数字化扩展",
}

_EXTENSION_SOURCE_LABELS = {
    "base": "基础",
    "builtin": "内置",
    "external": "外部",
}

_EXTENSION_ORIGIN_LABELS = {
    "base": "基础",
    "builtin": "内置",
    "external": "外部",
}

_EXTENSION_SOURCE_HINTS = {
    "processing": ("register_processing", "ProcessingExtension"),
    "analysis": ("register_analysis", "AnalysisExtension"),
    "plot": ("register_plot", "PlotExtension"),
    "digitize": ("register_digitize", "DigitizeExtension"),
}

_EXTENSION_TOOL_TIER_LABELS = {
    "tool": "工具",
    "experimental": "实验",
}

_EXTENSION_SOURCE_KINDS = frozenset(_EXTENSION_ORIGIN_LABELS)
_NON_EXTENSION_MODULE_FILENAMES = frozenset({"extension_tools.py"})


def normalize_extension_field_type(
    field_type: Any,
    *,
    key: Any = None,
    choices: Optional[Iterable[Any]] = None,
) -> str:
    explicit = str(field_type or "string").strip().lower()
    field_key = str(key or "").strip().casefold()
    has_choices = bool(list(choices or []))

    if explicit == "lines":
        return "lines"
    if explicit == "line":
        return "line"
    if explicit == "shot":
        return "shot"
    if explicit in {"pickcolor", "pick_colour", "pick_color"}:
        return "pickcolor"
    if explicit in {"bool", "boolean", "checkbox"}:
        return "boolean"
    if explicit in {"int", "integer", "spinbox"}:
        return "integer"
    if explicit in {"float", "double", "number"}:
        return "number"
    if explicit in {"choice", "select", "selective", "enum", "combobox"}:
        return "selective"
    if explicit in {"colour", "color", "colourpicker", "colorpicker"}:
        return "color"
    if explicit in {"slider", "range", "limited"}:
        return "limited"
    if explicit in {"image", "file", "path", "figure"}:
        return "figure"
    if has_choices:
        return "selective"
    if explicit == "string" and "color" in field_key:
        return "color"
    return "string"


def _extension_name_key(name: str) -> str:
    return str(name or "").strip().casefold()


def normalize_extension_version(version: str | None, *, default: str = DEFAULT_EXTENSION_VERSION) -> str:
    clean = str(version or "").strip() or default
    if not _EXTENSION_VERSION_PATTERN.fullmatch(clean):
        raise ValueError("扩展 version 必须是 x.x.x 格式")
    return clean


def normalize_extension_source_kind(kind: str | None, *, default: str = "builtin") -> str:
    clean = str(kind or "").strip().lower() or default
    if clean in _EXTENSION_SOURCE_KINDS:
        return clean
    return "external"


def normalize_extension_tool_tier(tier: str | None, *, default: str = "tool") -> str:
    clean = str(tier or "").strip().lower() or default
    if clean in _EXTENSION_TOOL_TIER_LABELS:
        return clean
    raise ValueError("tool_tier 仅允许 tool 或 experimental")


def parse_extension_version(version: str | None) -> Tuple[int, int, int]:
    normalized = normalize_extension_version(version)
    major, minor, patch = normalized.split(".")
    return int(major), int(minor), int(patch)


def compare_extension_versions(left: str | None, right: str | None) -> int:
    left_parts = parse_extension_version(left)
    right_parts = parse_extension_version(right)
    if left_parts < right_parts:
        return -1
    if left_parts > right_parts:
        return 1
    return 0


def _merge_nested_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_nested_dict(result[key], value)
            continue
        result[key] = copy.deepcopy(value)
    return result


def normalize_extension_lines_number(raw: Any) -> Optional[Tuple[int, int]]:
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return (1, 1)
    if isinstance(raw, (list, tuple)) and len(raw) == 0:
        return (1, 1)
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError("lines_number 必须是包含上下限的 [min, max] 列表或元组")

    try:
        lower = int(raw[0])
        upper = int(raw[1])
    except (TypeError, ValueError) as exc:
        raise ValueError("lines_number 的上下限必须是整数") from exc

    if lower < 0:
        raise ValueError("lines_number 下限不能小于 0")
    if upper < -1:
        raise ValueError("lines_number 上限只能是 -1 或非负整数")
    if upper != -1 and lower > upper:
        raise ValueError("lines_number 下限不能大于上限")
    return (lower, upper)


def normalize_plot_extension_phases(raw: Any) -> Tuple[str, ...]:
    if raw in (None, "", [], ()): 
        return ("before_plot", "after_plot")
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        raise ValueError("phases 必须是字符串或字符串列表")

    allowed = {"before_plot", "after_plot"}
    normalized: List[str] = []
    for item in values:
        phase = str(item or "").strip().lower()
        if phase not in allowed:
            raise ValueError("phases 仅允许 before_plot 或 after_plot")
        if phase not in normalized:
            normalized.append(phase)
    if not normalized:
        raise ValueError("phases 不能为空")
    return tuple(normalized)


def extension_lines_number(extension: Any) -> Optional[Tuple[int, int]]:
    return normalize_extension_lines_number(getattr(extension, "lines_number", None))


def extension_lines_support_text(lines_number: Optional[Tuple[int, int]]) -> str:
    if lines_number is None:
        return ""
    lower, upper = lines_number
    if lower == upper:
        return f"{lower} 条"
    if upper == -1:
        return f"{lower} 条及以上"
    if lower == 0:
        return f"0 到 {upper} 条"
    return f"{lower} 到 {upper} 条"


def extension_lines_picker_visible(lines_number: Optional[Tuple[int, int]]) -> bool:
    if lines_number is None:
        return False
    _lower, upper = lines_number
    return upper == -1 or upper > 1


def normalize_extension_lines_list(raw: Any) -> List[int]:
    if isinstance(raw, dict):
        raw = raw.get("lines_list")
    if raw in (None, "", False):
        return []

    items: List[Any]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if text.lower() in {"all", ":", "*", "selected"}:
            raise ValueError('lines_list 不再支持 "all" / ":" / "*" / "selected" 哨兵值，请显式提供曲线下标列表')
        items = [piece.strip() for piece in text.replace(";", ",").split(",") if piece.strip()]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = [raw]

    normalized: List[int] = []
    for item in items:
        try:
            index = int(item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"lines_list 包含无效曲线下标: {item!r}") from exc
        if index <= 0:
            raise ValueError("lines_list 中的曲线下标必须从 1 开始")
        if index not in normalized:
            normalized.append(index)
    return normalized


def validate_extension_lines_list(
    value: Any,
    lines_number: Optional[Tuple[int, int]],
    *,
    present: bool,
) -> List[int]:
    normalized = normalize_extension_lines_list(value)
    if lines_number is None:
        if present and normalized:
            raise ValueError("当前扩展未声明 lines_number，不支持 lines_list 参数")
        return normalized

    lower, upper = lines_number
    if not present:
        return normalized

    count = len(normalized)
    if count < lower:
        raise ValueError(f"lines_list 需要至少 {lower} 条曲线，当前为 {count} 条")
    if upper != -1 and count > upper:
        raise ValueError(f"lines_list 最多支持 {upper} 条曲线，当前为 {count} 条")
    return normalized


def normalize_extension_lines_config(raw: Any, *, preserve_legacy_all: bool = False) -> Dict[str, Any]:
    del preserve_legacy_all
    config = dict(raw or {}) if isinstance(raw, dict) else {}
    number = config.get("number")
    if "lines_number" in config:
        number = config.get("lines_number")
    try:
        normalized_number = normalize_extension_lines_number(number)
    except ValueError:
        normalized_number = None
    lines_list = config.get("lines_list")
    try:
        normalized_lines = normalize_extension_lines_list(lines_list)
    except ValueError:
        normalized_lines = []
    return {
        "number": normalized_number[1] if normalized_number is not None and normalized_number[0] == normalized_number[1] else (normalized_number[1] if normalized_number is not None and normalized_number[1] == -1 else (normalized_number[0] if normalized_number is not None else 0)),
        "lines_list": normalized_lines,
    }


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
    min_value: Any = None
    max_value: Any = None
    step: Any = None
    placeholder: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "field_type": self.field_type,
            "required": self.required,
            "default": self.default,
            "choices": list(self.choices),
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step": self.step,
            "placeholder": self.placeholder,
        }
        if self.extra:
            payload["extra"] = dict(self.extra)
        return payload


@dataclass(frozen=True)
class ProcessingExtension:
    type: str
    name: str
    handler: Callable[..., Any]
    description: str = ""
    version: str = DEFAULT_EXTENSION_VERSION
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)
    lines_number: Optional[Tuple[int, int] | List[int]] = None
    settings: bool = False
    source_kind: str = "builtin"
    tool_tier: str = "tool"
    hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines_number", normalize_extension_lines_number(self.lines_number))
        object.__setattr__(self, "tool_tier", normalize_extension_tool_tier(self.tool_tier))

    @property
    def id(self) -> str:
        return self.type

    @property
    def handle(self) -> Callable[..., Any]:
        return self.handler

    @property
    def function_category(self) -> str:
        return "processing"

    @property
    def listed(self) -> bool:
        return not self.hidden and normalize_extension_source_kind(self.source_kind) != "base"

    @property
    def closable(self) -> bool:
        return normalize_extension_source_kind(self.source_kind) != "base"

    @property
    def resolved_default_options(self) -> Dict[str, Any]:
        return extension_resolved_default_options(self)


@dataclass(frozen=True)
class AnalysisExtension:
    type: str
    name: str
    handler: Callable[..., Any]
    description: str = ""
    version: str = DEFAULT_EXTENSION_VERSION
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)
    lines_number: Optional[Tuple[int, int] | List[int]] = None
    report_placeholders: List[Dict[str, Any]] = field(default_factory=list)
    settings: bool = False
    source_kind: str = "builtin"
    tool_tier: str = "tool"
    hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines_number", normalize_extension_lines_number(self.lines_number))
        object.__setattr__(self, "tool_tier", normalize_extension_tool_tier(self.tool_tier))

    @property
    def id(self) -> str:
        return self.type

    @property
    def handle(self) -> Callable[..., Any]:
        return self.handler

    @property
    def function_category(self) -> str:
        return "analysis"

    @property
    def listed(self) -> bool:
        return not self.hidden and normalize_extension_source_kind(self.source_kind) != "base"

    @property
    def closable(self) -> bool:
        return normalize_extension_source_kind(self.source_kind) != "base"

    @property
    def resolved_default_options(self) -> Dict[str, Any]:
        return extension_resolved_default_options(self)


@dataclass(frozen=True)
class PlotExtension:
    type: str
    name: str
    handler: Callable[..., None]
    description: str = ""
    version: str = DEFAULT_EXTENSION_VERSION
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)
    lines_number: Optional[Tuple[int, int] | List[int]] = None
    phases: Tuple[str, ...] = field(default_factory=lambda: ("before_plot", "after_plot"))
    settings: bool = False
    source_kind: str = "builtin"
    tool_tier: str = "tool"
    hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines_number", normalize_extension_lines_number(self.lines_number))
        object.__setattr__(self, "phases", normalize_plot_extension_phases(self.phases))
        object.__setattr__(self, "tool_tier", normalize_extension_tool_tier(self.tool_tier))

    @property
    def id(self) -> str:
        return self.type

    @property
    def handle(self) -> Callable[..., None]:
        return self.handler

    @property
    def function_category(self) -> str:
        return "plot"

    @property
    def listed(self) -> bool:
        return not self.hidden and normalize_extension_source_kind(self.source_kind) != "base"

    @property
    def closable(self) -> bool:
        return normalize_extension_source_kind(self.source_kind) != "base"

    @property
    def resolved_default_options(self) -> Dict[str, Any]:
        return extension_resolved_default_options(self)


@dataclass(frozen=True)
class DigitizeExtension:
    type: str
    name: str
    handler: Callable[..., Any]
    description: str = ""
    version: str = DEFAULT_EXTENSION_VERSION
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)
    settings: bool = False
    source_kind: str = "builtin"
    tool_tier: str = "tool"
    hidden: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_tier", normalize_extension_tool_tier(self.tool_tier))

    @property
    def id(self) -> str:
        return self.type

    @property
    def handle(self) -> Callable[..., Any]:
        return self.handler

    @property
    def function_category(self) -> str:
        return "digitize"

    @property
    def listed(self) -> bool:
        return not self.hidden and normalize_extension_source_kind(self.source_kind) != "base"

    @property
    def closable(self) -> bool:
        return normalize_extension_source_kind(self.source_kind) != "base"

    @property
    def resolved_default_options(self) -> Dict[str, Any]:
        return extension_resolved_default_options(self)


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


def extension_function_category(extension: Any) -> str:
    explicit = str(getattr(extension, "function_category", "") or "").strip().lower()
    if explicit in _EXTENSION_CATEGORY_LABELS:
        return explicit
    if isinstance(extension, ProcessingExtension):
        return "processing"
    if isinstance(extension, AnalysisExtension):
        return "analysis"
    if isinstance(extension, PlotExtension):
        return "plot"
    if isinstance(extension, DigitizeExtension):
        return "digitize"
    return ""


def _coerce_config_field(field_item: Any) -> Dict[str, Any]:
    if hasattr(field_item, "to_dict"):
        normalized = dict(field_item.to_dict())
    elif isinstance(field_item, dict):
        normalized = dict(field_item)
    else:
        raise TypeError(f"不支持的扩展字段定义: {field_item!r}")

    normalized["field_type"] = normalize_extension_field_type(
        normalized.get("field_type"),
        key=normalized.get("key"),
        choices=normalized.get("choices"),
    )
    field_key = str(normalized.get("key") or "").strip().casefold()
    if field_key in {"lines", "lines_list", "lines_number"} or normalized.get("field_type") == "lines":
        raise ValueError("lines_number 与 lines_list 已改为扩展内置参数，不能再通过 ExtensionConfigField 注册")
    return normalized


def extension_config_fields(extension: Any, *, include_implicit_lines: bool = False) -> List[Dict[str, Any]]:
    normalized_fields: List[Dict[str, Any]] = []
    for field_item in getattr(extension, "config_fields", []) or []:
        normalized = _coerce_config_field(field_item)
        normalized_fields.append(normalized)

    category = extension_function_category(extension)
    if not include_implicit_lines or category not in {"processing", "analysis", "plot"}:
        return normalized_fields

    lines_number = extension_lines_number(extension)
    if lines_number is None:
        return normalized_fields

    legacy_options = dict(getattr(extension, "default_options", {}) or {})
    default_lines = validate_extension_lines_list(
        legacy_options.get("lines_list"),
        lines_number,
        present="lines_list" in legacy_options,
    )
    normalized_fields.insert(
        0,
        ExtensionConfigField(
            key="lines_list",
            label="lines",
            description=f"本扩展支持的曲线数量为 {extension_lines_support_text(lines_number)}。",
            field_type="lines",
            default=default_lines,
            extra={"lines_number": list(lines_number)},
        ).to_dict(),
    )
    return normalized_fields


def extension_resolved_default_options(extension: Any) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {}
    for field_item in extension_config_fields(extension, include_implicit_lines=True):
        key = str(field_item.get("key") or "").strip()
        if not key:
            continue
        if "default" not in field_item:
            continue
        defaults[key] = copy.deepcopy(field_item.get("default"))

    legacy_defaults = dict(getattr(extension, "default_options", {}) or {})
    if "lines" in legacy_defaults:
        raw_legacy_lines = legacy_defaults.pop("lines")
        legacy_lines = dict(raw_legacy_lines or {}) if isinstance(raw_legacy_lines, dict) else {}
        if "lines_list" not in legacy_defaults and legacy_lines:
            legacy_defaults["lines_list"] = legacy_lines.get("lines_list")
    lines_number = extension_lines_number(extension)
    if "lines_list" in legacy_defaults:
        legacy_defaults["lines_list"] = validate_extension_lines_list(
            legacy_defaults.get("lines_list"),
            lines_number,
            present=True,
        )
    if not legacy_defaults:
        return defaults
    return _merge_nested_dict(defaults, legacy_defaults)


def _validate_extension_contract(category: str, extension: Any) -> None:
    normalize_extension_version(getattr(extension, "version", DEFAULT_EXTENSION_VERSION))
    normalize_extension_tool_tier(getattr(extension, "tool_tier", "tool"))
    if not isinstance(getattr(extension, "settings", False), bool):
        raise ValueError("settings 必须是布尔值")
    if category == "plot":
        normalize_plot_extension_phases(getattr(extension, "phases", None))
    lines_number = extension_lines_number(extension) if category in {"processing", "analysis", "plot"} else None
    extension_config_fields(extension, include_implicit_lines=False)
    legacy_defaults = dict(getattr(extension, "default_options", {}) or {})
    if category in {"processing", "analysis", "plot"}:
        if "lines_number" in legacy_defaults:
            raise ValueError("lines_number 已改为扩展注册参数，不能放在 default_options 中")
        if "lines" in legacy_defaults:
            raise ValueError("lines 内嵌协议已废弃，请改用扩展注册参数 lines_number 与顶层 lines_list")
        if "lines_list" in legacy_defaults:
            validate_extension_lines_list(legacy_defaults.get("lines_list"), lines_number, present=True)
        elif lines_number is not None:
            validate_extension_lines_list([], lines_number, present=False)
    if category == "analysis":
        for item in list(getattr(extension, "report_placeholders", []) or []):
            if not isinstance(item, dict):
                raise ValueError("report_placeholders 必须使用包含 token / label / description 的字典列表")
            token = str(item.get("token") or "").strip()
            label = str(item.get("label") or "").strip()
            description = str(item.get("description") or "").strip()
            if not token.startswith("{{") or not token.endswith("}}"):
                raise ValueError("report_placeholders.token 必须使用 {{token}} 形式")
            if not label or not description:
                raise ValueError("report_placeholders 必须显式提供 label 与 description")


class ExtensionRegistry:
    def __init__(self) -> None:
        self._processing: Dict[str, ProcessingExtension] = {}
        self._analysis: Dict[str, AnalysisExtension] = {}
        self._plot: Dict[str, PlotExtension] = {}
        self._digitize: Dict[str, DigitizeExtension] = {}
        self._last_load_report: Dict[str, List[str]] = {"loaded": [], "errors": []}
        self._last_load_details: Dict[str, List[Dict[str, Any]]] = {"loaded": [], "errors": []}

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

    @staticmethod
    def _ensure_unique_identity(category: str, mapping: Dict[str, Any], extension: Any) -> None:
        type_id = str(getattr(extension, "type", "") or "").strip()
        if not type_id:
            raise ValueError(f"{category} extension type is required")
        name = str(getattr(extension, "name", "") or "").strip()
        if not name:
            raise ValueError(f"{category} extension name is required")
        normalize_extension_version(getattr(extension, "version", DEFAULT_EXTENSION_VERSION))
        if type_id in mapping:
            raise ValueError(f"重复的 {category} 扩展 type: {type_id}")
        duplicate_name = next((item for item in mapping.values() if _extension_name_key(getattr(item, "name", "")) == _extension_name_key(name)), None)
        if duplicate_name is not None:
            raise ValueError(f"重复的 {category} 扩展 name: {name}")

    def register_processing(self, extension: ProcessingExtension) -> None:
        _validate_extension_contract("processing", extension)
        self._ensure_unique_identity("processing", self._processing, extension)
        self._processing[extension.type.strip()] = extension

    def register_analysis(self, extension: AnalysisExtension) -> None:
        _validate_extension_contract("analysis", extension)
        self._ensure_unique_identity("analysis", self._analysis, extension)
        self._analysis[extension.type.strip()] = extension

    def register_plot(self, extension: PlotExtension) -> None:
        _validate_extension_contract("plot", extension)
        self._ensure_unique_identity("plot", self._plot, extension)
        self._plot[extension.type.strip()] = extension

    def register_digitize(self, extension: DigitizeExtension) -> None:
        _validate_extension_contract("digitize", extension)
        self._ensure_unique_identity("digitize", self._digitize, extension)
        self._digitize[extension.type.strip()] = extension

    def unregister_processing(self, type_id: str) -> None:
        self._processing.pop(type_id, None)

    def unregister_analysis(self, type_id: str) -> None:
        self._analysis.pop(type_id, None)

    def unregister_plot(self, type_id: str) -> None:
        self._plot.pop(type_id, None)

    def unregister_digitize(self, type_id: str) -> None:
        self._digitize.pop(type_id, None)

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

    def _registry_snapshot(self) -> Dict[str, set[str]]:
        return {
            "processing": {extension.type for extension in self.list_processing()},
            "analysis": {extension.type for extension in self.list_analysis()},
            "plot": {extension.type for extension in self.list_plot()},
            "digitize": {extension.type for extension in self.list_digitize()},
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
        return self._scan_paths(_extension_python_files(target), source_directory=target, source_kind=source_kind)

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


extension_registry = ExtensionRegistry()


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
        "processing": [{"type": item.type, "name": item.name, "tool_tier": item.tool_tier} for item in registry.list_processing()],
        "analysis": [{"type": item.type, "name": item.name, "tool_tier": item.tool_tier} for item in registry.list_analysis()],
        "plot": [{"type": item.type, "name": item.name, "tool_tier": item.tool_tier} for item in registry.list_plot()],
        "digitize": [{"type": item.type, "name": item.name, "tool_tier": item.tool_tier} for item in registry.list_digitize()],
    }


def _inspect_extension_file(path: str | Path) -> Dict[str, List[Dict[str, str]]]:
    registry = ExtensionRegistry()
    registry.load_from_file(path)
    return _extension_entries_by_category(registry)


def build_extension_entry(extension: Any) -> Dict[str, Any]:
    function_category = extension_function_category(extension)
    source_kind = normalize_extension_source_kind(getattr(extension, "source_kind", "builtin"))
    config_fields = extension_config_fields(extension)
    normalized_config_fields = extension_config_fields(extension, include_implicit_lines=True)
    legacy_default_options = dict(getattr(extension, "default_options", {}) or {})
    if "lines" in legacy_default_options:
        raw_legacy_lines = legacy_default_options.pop("lines")
        legacy_lines = dict(raw_legacy_lines or {}) if isinstance(raw_legacy_lines, dict) else {}
        if "lines_list" not in legacy_default_options and legacy_lines:
            legacy_default_options["lines_list"] = legacy_lines.get("lines_list")
    if "lines_list" in legacy_default_options:
        legacy_default_options["lines_list"] = normalize_extension_lines_list(legacy_default_options.get("lines_list"))
    lines_number = extension_lines_number(extension)
    resolved_default_options = extension_resolved_default_options(extension)
    hidden = bool(getattr(extension, "hidden", False))
    listed = bool(getattr(extension, "listed", not hidden and source_kind != "base"))
    closable = bool(getattr(extension, "closable", source_kind != "base"))
    tool_tier = normalize_extension_tool_tier(getattr(extension, "tool_tier", "tool"))
    return {
        "id": extension.id,
        "type": extension.type,
        "name": extension.name,
        "label": extension.name,
        "description": extension.description,
        "version": normalize_extension_version(getattr(extension, "version", DEFAULT_EXTENSION_VERSION)),
        "settings": bool(getattr(extension, "settings", False)),
        "source_kind": source_kind,
        "source_label": _EXTENSION_SOURCE_LABELS.get(source_kind, source_kind),
        "tool_tier": tool_tier,
        "tool_tier_label": _EXTENSION_TOOL_TIER_LABELS.get(tool_tier, tool_tier),
        "origin_kind": source_kind,
        "origin_label": _EXTENSION_ORIGIN_LABELS.get(source_kind, source_kind),
        "function_category": function_category,
        "function_label": _EXTENSION_CATEGORY_LABELS.get(function_category, function_category),
        "phases": list(normalize_plot_extension_phases(getattr(extension, "phases", None))) if function_category == "plot" else [],
        "hidden": hidden,
        "listed": listed,
        "closable": closable,
        "resolved_options": resolved_default_options,
        "legacy_default_options": legacy_default_options,
        "config_fields": config_fields,
        "normalized_config_fields": normalized_config_fields,
        "lines_number": list(lines_number) if lines_number is not None else None,
        "report_placeholders": [dict(item) for item in getattr(extension, "report_placeholders", []) or [] if isinstance(item, dict)],
    }


def extension_entry_display_info(
    entry: Optional[Dict[str, Any]],
    *,
    category_label: Optional[str] = None,
) -> Dict[str, str]:
    if not isinstance(entry, dict):
        return {
            "category_label": "",
            "name": "",
            "source_label": "",
            "version_label": "",
            "type_id": "",
            "description": "",
            "panel_title": "",
            "data_title": "",
        }

    resolved_category = str(category_label or entry.get("function_label") or "扩展").strip() or "扩展"
    name = str(entry.get("name") or entry.get("label") or entry.get("type") or "扩展").strip() or "扩展"
    source_label = str(entry.get("source_label") or entry.get("origin_label") or "").strip()
    version = str(entry.get("version") or "").strip()
    version_label = f"v{version}" if version and not version.startswith(("v", "V")) else version
    type_id = str(entry.get("type") or "").strip()
    description = str(entry.get("description") or "").strip()

    panel_title_parts = [name]
    if source_label:
        panel_title_parts.append(source_label)
    if version_label:
        panel_title_parts.append(version_label)

    return {
        "category_label": resolved_category,
        "name": name,
        "source_label": source_label,
        "version_label": version_label,
        "type_id": type_id,
        "description": description,
        "panel_title": "·".join(panel_title_parts),
        "data_title": f"{resolved_category}·{name}",
    }


def extension_entry_parameter_help_text(entry: Optional[Dict[str, Any]]) -> str:
    if not isinstance(entry, dict):
        return ""

    fields = [
        dict(item)
        for item in (entry.get("normalized_config_fields") or entry.get("config_fields") or [])
        if isinstance(item, dict)
    ]
    if not fields:
        return "该扩展未声明额外参数。"

    lines: List[str] = []
    for field in fields:
        key = str(field.get("key") or "option").strip() or "option"
        field_type = str(field.get("field_type") or "string").strip() or "string"
        if field_type.lower() == "lines" or key == "lines_list":
            description = str(field.get("description") or "").strip()
            if not description:
                extra = dict(field.get("extra") or {}) if isinstance(field.get("extra"), dict) else {}
                lines_number = normalize_extension_lines_number(extra.get("lines_number"))
                description = f"本扩展支持的曲线数量为 {extension_lines_support_text(lines_number)}。" if lines_number else "本扩展支持曲线输入。"
            lines.append(f"- lines: {description}")
            continue
        if field_type.lower() == "line":
            description = str(field.get("description") or "").strip() or "从当前数据集中选择 1 条曲线作为内部参数。"
            default = field.get("default")
            parts = [f"{str(field.get('label') or key).strip() or key}（line，可选）", description]
            if default not in (None, "", []):
                parts.append(f"默认值: {default}")
            lines.append("- " + "；".join(parts))
            continue

        label = str(field.get("label") or key).strip() or key
        required = "必填" if field.get("required") else "可选"
        parts = [f"{label}（{field_type}，{required}）"]
        description = str(field.get("description") or "").strip()
        if description:
            parts.append(description)
        choices = [str(item) for item in (field.get("choices") or []) if str(item)]
        if choices:
            parts.append(f"可选值: {', '.join(choices)}")
        default = field.get("default")
        if default not in (None, "", []):
            parts.append(f"默认值: {default}")
        lines.append("- " + "；".join(parts))
    return "\n".join(lines)


def _invoke_handler_with_optional_payload(
    handler: Callable[..., Any],
    base_args: Tuple[Any, ...],
    optional_arg_name: str,
    optional_payload: Any,
) -> Any:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return handler(*base_args)

    parameters = list(signature.parameters.values())
    named_parameter = signature.parameters.get(optional_arg_name)
    accepts_named = (
        (named_parameter is not None and named_parameter.kind != inspect.Parameter.POSITIONAL_ONLY)
        or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters)
    )
    if accepts_named:
        return handler(*base_args, **{optional_arg_name: copy.deepcopy(optional_payload)})

    positional_params = [
        param for param in parameters
        if param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if any(param.kind == inspect.Parameter.VAR_POSITIONAL for param in parameters) or len(positional_params) >= len(base_args) + 1:
        return handler(*base_args, copy.deepcopy(optional_payload))
    return handler(*base_args)


def invoke_processing_extension_handler(
    handler: Callable[..., Any],
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
    handler: Callable[..., Any],
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
    context: PlotExtensionContext,
    params: Dict[str, Any],
) -> None:
    extension = extension_or_handler if isinstance(extension_or_handler, PlotExtension) else None
    handler: Callable[..., Any] = extension.handler if extension is not None else cast(Callable[..., Any], extension_or_handler)
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
    handler: Callable[..., Any],
    figure: Any,
    params: Dict[str, Any],
) -> Any:
    result = handler(figure, dict(params))
    return normalize_line(result)


def default_extensions_directory(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        return Path(base_dir)
    return Path(__file__).resolve().parent.parent / "extensions"


def _extension_python_files(directory: str | Path) -> List[Path]:
    target = Path(directory)
    if not target.exists() or not target.is_dir():
        return []
    return [path for path in sorted(target.rglob("*.py")) if not path.name.startswith("_")]


def builtin_extension_files(base_dir: str | Path | None = None) -> List[Path]:
    directory = default_extensions_directory(base_dir)
    return [path for path in _extension_python_files(directory) if not path.name.endswith("_demo.py")]


def _normalize_external_directory_inputs(directory: str | Path | Iterable[str | Path] | None) -> List[Path]:
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


def external_extension_files(directory: str | Path | Iterable[str | Path] | None = None) -> List[Path]:
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
    effective_load_builtin = settings_load_builtin if load_builtin is None else bool(load_builtin)
    effective_disabled_ids = settings_disabled_ids if disabled_extension_ids is None else list(disabled_extension_ids)
    if not effective_load_builtin:
        return []

    disabled_markers = _builtin_extension_disabled_markers(effective_disabled_ids)
    return [
        path for path in builtin_extension_files(base_dir)
        if _builtin_extension_id(path) not in disabled_markers and path.name not in disabled_markers
    ]


def configured_external_extension_files(
    directory: str | Path | Iterable[str | Path] | None = None,
    *,
    load_external: Optional[bool] = None,
    disabled_extension_ids: Optional[Iterable[str]] = None,
) -> List[Path]:
    from core.extension_settings import get_external_extension_settings

    settings_load_external, settings_disabled_ids = get_external_extension_settings()
    effective_load_external = settings_load_external if load_external is None else bool(load_external)
    effective_disabled_ids = settings_disabled_ids if disabled_extension_ids is None else list(disabled_extension_ids)
    if not effective_load_external:
        return []

    disabled_markers = _extension_disabled_markers(effective_disabled_ids)
    return [
        path for path in external_extension_files(directory)
        if _extension_file_id(path) not in disabled_markers and path.name not in disabled_markers
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
            categories = [category for category, entries in entries_by_category.items() if entries]
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
        discovered_entries = [entry for entries in entries_by_category.values() for entry in entries]
        names = [entry["name"] for entry in discovered_entries if entry.get("name")]
        type_ids = [entry["type"] for entry in discovered_entries if entry.get("type")]
        tool_tiers = sorted({str(entry.get("tool_tier") or "tool") for entry in discovered_entries if entry.get("tool_tier")})
        spec_id = _extension_file_id(path)
        specs.append({
            "id": spec_id,
            "source": source_kind,
            "source_label": _EXTENSION_SOURCE_LABELS.get(source_kind, source_kind),
            "file_name": Path(path).name,
            "name": " / ".join(names) if names else spec_id,
            "categories": categories,
            "category_labels": [_EXTENSION_CATEGORY_LABELS.get(category, category) for category in categories],
            "type_ids": type_ids,
            "tool_tiers": tool_tiers,
            "tool_tier_labels": [_EXTENSION_TOOL_TIER_LABELS.get(tier, tier) for tier in tool_tiers],
            "entries_by_category": entries_by_category,
            "names_by_category": names_by_category,
            "type_ids_by_category": type_ids_by_category,
            "path": str(path),
            "enabled": bool(load_enabled) and spec_id not in enabled_markers and Path(path).name not in enabled_markers,
            "load_error": load_error,
        })
    return specs


def list_builtin_extension_specs(base_dir: str | Path | None = None) -> List[Dict[str, Any]]:
    from core.extension_settings import get_builtin_extension_settings

    load_builtin, disabled_extension_ids = get_builtin_extension_settings()
    disabled_markers = _builtin_extension_disabled_markers(disabled_extension_ids)
    return _build_extension_specs(
        builtin_extension_files(base_dir),
        source_kind="builtin",
        enabled_markers=disabled_markers,
        load_enabled=load_builtin,
    )


def list_external_extension_specs(directory: str | Path | Iterable[str | Path] | None = None) -> List[Dict[str, Any]]:
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
    from core.extension_settings import get_builtin_extension_settings, get_external_extension_settings

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


def load_builtin_extensions(directory: str | Path | None = None) -> Dict[str, List[str]]:
    return extension_registry.load_from_directory(default_extensions_directory(directory), source_kind="builtin")


def reload_builtin_extensions(directory: str | Path | None = None) -> Dict[str, List[str]]:
    extension_registry.clear()
    return load_builtin_extensions(directory)


def load_configured_extensions(
    base_dir: str | Path | None = None,
    external_dir: str | Path | Iterable[str | Path] | None = None,
) -> Dict[str, List[str]]:
    builtin_files = configured_builtin_extension_files(base_dir)
    external_files = configured_external_extension_files(external_dir)
    report = {"loaded": [], "errors": []}
    detail_report: Dict[str, List[Dict[str, Any]]] = {"loaded": [], "errors": []}

    for file_group, source_kind in ((builtin_files, "builtin"), (external_files, "external")):
        group_report, group_detail = extension_registry._scan_paths(file_group, source_kind=source_kind)
        report["loaded"].extend(group_report["loaded"])
        report["errors"].extend(group_report["errors"])
        detail_report["loaded"].extend(group_detail["loaded"])
        detail_report["errors"].extend(group_detail["errors"])

    extension_registry._last_load_report = {
        "loaded": list(report["loaded"]),
        "errors": list(report["errors"]),
    }
    extension_registry._last_load_details = detail_report
    return report


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
        "label": _EXTENSION_CATEGORY_LABELS.get(normalized, "扩展") if normalized else "扩展",
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
            category_text = "、".join(_EXTENSION_CATEGORY_LABELS.get(str(cat), str(cat)) for cat in item.get("categories", []))
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


def register_digitize_extension(extension: DigitizeExtension) -> None:
    extension_registry.register_digitize(extension)