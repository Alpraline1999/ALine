from __future__ import annotations

"""扩展类型定义 — 所有扩展 Dataclass、标签字典、类型 normalize 函数。

该模块不依赖 extension_registry / extension_loader / extension_settings，
仅依赖 stdlib 和 core.extension_types（轻量原语）。
"""

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Protocol, Tuple, TypedDict, runtime_checkable
import re

from core.i18n import _
from core.extension_types import (
    PlotExtensionContext,
    merge_nested_dict,
    normalize_plot_extension_phases,
)

# ---------------------------------------------------------------------------
# Protocol 类型 — 扩展 handler 签名约束
# ---------------------------------------------------------------------------

Point = Tuple[float, float]
"""曲线点类型 (x, y)"""

Line = List[Point]
"""曲线类型 — point 列表 [[x1,y1], [x2,y2], ...]"""


@runtime_checkable
class ProcessingHandler(Protocol):
    """处理扩展 handler 签名: (lines, params) -> line"""
    def __call__(self, lines: List[Line], params: Dict[str, Any]) -> Line: ...


@runtime_checkable
class AnalysisHandler(Protocol):
    """分析扩展 handler 签名: (lines, params) -> dict"""
    def __call__(self, lines: List[Line], params: Dict[str, Any]) -> Dict[str, Any]: ...


@runtime_checkable
class PlotHandler(Protocol):
    """绘图扩展 handler 签名: (plot_context, params) -> None"""
    def __call__(self, plot_context: "PlotExtensionContext", params: Dict[str, Any]) -> None: ...


@runtime_checkable
class DigitizeHandler(Protocol):
    """数字化扩展 handler 签名: (figure, params) -> line"""
    def __call__(self, figure: Any, params: Dict[str, Any]) -> Line: ...


DEFAULT_EXTENSION_VERSION = "1.0.0"
_EXTENSION_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


_EXTENSION_CATEGORY_LABELS = {
    "processing": _("处理扩展"),
    "analysis": _("分析扩展"),
    "plot": _("绘图扩展"),
    "digitize": _("数字化扩展"),
}

_EXTENSION_SOURCE_LABELS = {
    "base": _("基础"),
    "builtin": _("内置"),
    "external": _("外部"),
}

_EXTENSION_ORIGIN_LABELS = {
    "base": _("基础"),
    "builtin": _("内置"),
    "external": _("外部"),
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


class ExtensionParams(TypedDict, total=False):
    lines_list: List[int]



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
    handler: ProcessingHandler
    description: str = ""
    version: str = DEFAULT_EXTENSION_VERSION
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)
    lines_number: Optional[Tuple[int, int] | List[int]] = None
    settings: bool = False
    source_kind: str = "builtin"
    tool_tier: str = "tool"
    hidden: bool = False
    capabilities: set[str] = field(default_factory=set)
    api_version: str = ""
    aline_api_version: str = ""
    supports_progress: bool = False
    supports_cancel: bool = False
    min_app_version: str = ""
    tested_app_range: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines_number", normalize_extension_lines_number(self.lines_number))
        object.__setattr__(self, "tool_tier", normalize_extension_tool_tier(self.tool_tier))

    @property
    def id(self) -> str:
        return self.type

    @property
    def handle(self) -> "ProcessingHandler":
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
    handler: AnalysisHandler
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
    capabilities: set[str] = field(default_factory=set)
    api_version: str = ""
    aline_api_version: str = ""
    supports_progress: bool = False
    supports_cancel: bool = False
    min_app_version: str = ""
    tested_app_range: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines_number", normalize_extension_lines_number(self.lines_number))
        object.__setattr__(self, "tool_tier", normalize_extension_tool_tier(self.tool_tier))

    @property
    def id(self) -> str:
        return self.type

    @property
    def handle(self) -> "AnalysisHandler":
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
    handler: PlotHandler
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
    capabilities: set[str] = field(default_factory=set)
    api_version: str = ""
    aline_api_version: str = ""
    supports_progress: bool = False
    supports_cancel: bool = False
    min_app_version: str = ""
    tested_app_range: list[str] = field(default_factory=list)
    style_authority: str = "advisory"
    authoritative_fields: set[str] = field(default_factory=set)
    post_render_mutation: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines_number", normalize_extension_lines_number(self.lines_number))
        object.__setattr__(self, "phases", normalize_plot_extension_phases(self.phases))
        object.__setattr__(self, "tool_tier", normalize_extension_tool_tier(self.tool_tier))

    @property
    def id(self) -> str:
        return self.type

    @property
    def handle(self) -> "PlotHandler":
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
    handler: DigitizeHandler
    description: str = ""
    version: str = DEFAULT_EXTENSION_VERSION
    default_options: Dict[str, Any] = field(default_factory=dict)
    config_fields: List[ExtensionConfigField] = field(default_factory=list)
    settings: bool = False
    source_kind: str = "builtin"
    tool_tier: str = "tool"
    hidden: bool = False
    capabilities: set[str] = field(default_factory=set)
    api_version: str = ""
    aline_api_version: str = ""
    supports_progress: bool = False
    supports_cancel: bool = False
    min_app_version: str = ""
    tested_app_range: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_tier", normalize_extension_tool_tier(self.tool_tier))

    @property
    def id(self) -> str:
        return self.type

    @property
    def handle(self) -> "DigitizeHandler":
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


# ---------------------------------------------------------------------------
#  Functions migrated from extension_api.py
# ---------------------------------------------------------------------------


def extension_function_category(extension: Any) -> str:
    """Return the standard function category for a given extension object."""
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
        raise ValueError(
            "lines_number 与 lines_list 已改为扩展内置参数，不能再通过 ExtensionConfigField 注册"
        )
    return normalized


def extension_config_fields(
    extension: Any, *, include_implicit_lines: bool = False
) -> List[Dict[str, Any]]:
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
        raise ValueError(
            "lines 内嵌协议已废弃，请改用扩展注册参数 lines_number 与顶层 lines_list"
        )
    lines_number = extension_lines_number(extension)
    if "lines_list" in legacy_defaults:
        legacy_defaults["lines_list"] = validate_extension_lines_list(
            legacy_defaults.get("lines_list"),
            lines_number,
            present=True,
        )
    if not legacy_defaults:
        return defaults
    return merge_nested_dict(defaults, legacy_defaults)


def build_extension_entry(extension: Any) -> Dict[str, Any]:
    function_category = extension_function_category(extension)
    source_kind = normalize_extension_source_kind(getattr(extension, "source_kind", "builtin"))
    config_fields = extension_config_fields(extension)
    normalized_config_fields = extension_config_fields(extension, include_implicit_lines=True)
    legacy_default_options = dict(getattr(extension, "default_options", {}) or {})
    if "lines" in legacy_default_options:
        raise ValueError(
            "lines 内嵌协议已废弃，请改用扩展注册参数 lines_number 与顶层 lines_list"
        )
    if "lines_list" in legacy_default_options:
        legacy_default_options["lines_list"] = normalize_extension_lines_list(
            legacy_default_options.get("lines_list")
        )
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
        "version": normalize_extension_version(
            getattr(extension, "version", DEFAULT_EXTENSION_VERSION)
        ),
        "settings": bool(getattr(extension, "settings", False)),
        "source_kind": source_kind,
        "source_label": _EXTENSION_SOURCE_LABELS.get(source_kind, source_kind),
        "tool_tier": tool_tier,
        "tool_tier_label": _EXTENSION_TOOL_TIER_LABELS.get(tool_tier, tool_tier),
        "origin_kind": source_kind,
        "origin_label": _EXTENSION_ORIGIN_LABELS.get(source_kind, source_kind),
        "function_category": function_category,
        "function_label": _EXTENSION_CATEGORY_LABELS.get(function_category, function_category),
        "phases": (
            list(normalize_plot_extension_phases(getattr(extension, "phases", None)))
            if function_category == "plot"
            else []
        ),
        "hidden": hidden,
        "listed": listed,
        "closable": closable,
        "resolved_options": resolved_default_options,
        "legacy_default_options": legacy_default_options,
        "config_fields": config_fields,
        "normalized_config_fields": normalized_config_fields,
        "lines_number": list(lines_number) if lines_number is not None else None,
        "report_placeholders": [
            dict(item)
            for item in getattr(extension, "report_placeholders", []) or []
            if isinstance(item, dict)
        ],
        "capabilities": set(
            str(c) for c in getattr(extension, "capabilities", set()) or set()
        ),
        "api_version": str(getattr(extension, "api_version", "") or ""),
        "supports_progress": bool(getattr(extension, "supports_progress", False)),
        "supports_cancel": bool(getattr(extension, "supports_cancel", False)),
        "min_app_version": str(getattr(extension, "min_app_version", "") or ""),
        "tested_app_range": list(
            str(v) for v in getattr(extension, "tested_app_range", []) or []
        ),
        "style_authority": str(getattr(extension, "style_authority", "advisory")),
        "authoritative_fields": set(
            str(f)
            for f in getattr(extension, "authoritative_fields", set()) or set()
        ),
        "post_render_mutation": bool(getattr(extension, "post_render_mutation", False)),
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

    resolved_category = str(
        category_label or entry.get("function_label") or _("扩展")
    ).strip() or _("扩展")
    name = str(entry.get("name") or entry.get("label") or entry.get("type") or _("扩展")).strip() or _(
        "扩展"
    )
    source_label = str(
        entry.get("source_label") or entry.get("origin_label") or ""
    ).strip()
    version = str(entry.get("version") or "").strip()
    version_label = (
        f"v{version}" if version and not version.startswith(("v", "V")) else version
    )
    type_id = str(entry.get("type") or "").strip()
    description = str(entry.get("description") or "").strip()

    panel_title_parts = [name]
    if source_label:
        panel_title_parts.append(source_label)
    if version_label:
        panel_title_parts.append(version_label)

    # 能力/兼容性摘要
    caps_parts = []
    if entry.get("supports_progress"):
        caps_parts.append("进度")
    if entry.get("supports_cancel"):
        caps_parts.append("取消")
    if entry.get("post_render_mutation"):
        caps_parts.append("后处理")
    capabilities_label = "、".join(caps_parts) if caps_parts else ""
    api_ver = str(entry.get("api_version") or "").strip()
    min_ver = str(entry.get("min_app_version") or "").strip()
    tested = list(entry.get("tested_app_range") or [])
    authority = str(entry.get("style_authority") or "advisory")
    authority_label = "强制接管" if authority == "authoritative" else ""
    authoritative_fields = set(
        str(f) for f in entry.get("authoritative_fields", set()) or set()
    )
    auth_fields_label = (
        f"接管字段: {', '.join(sorted(authoritative_fields))}" if authoritative_fields else ""
    )

    return {
        "category_label": resolved_category,
        "name": name,
        "source_label": source_label,
        "version_label": version_label,
        "type_id": type_id,
        "description": description,
        "panel_title": "·".join(panel_title_parts),
        "data_title": f"{resolved_category}·{name}",
        "capabilities_label": capabilities_label,
        "api_version_label": f"API v{api_ver}" if api_ver else "",
        "min_app_version_label": f"最低 App v{min_ver}" if min_ver else "",
        "tested_range_label": f"验证版本: {', '.join(tested)}" if tested else "",
        "authority_label": authority_label,
        "auth_fields_label": auth_fields_label,
    }


def extension_entry_parameter_help_text(entry: Optional[Dict[str, Any]]) -> str:
    if not isinstance(entry, dict):
        return ""

    fields = [
        dict(item)
        for item in (
            entry.get("normalized_config_fields") or entry.get("config_fields") or []
        )
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
                extra = (
                    dict(field.get("extra") or {})
                    if isinstance(field.get("extra"), dict)
                    else {}
                )
                lines_number = normalize_extension_lines_number(extra.get("lines_number"))
                description = (
                    f"本扩展支持的曲线数量为 {extension_lines_support_text(lines_number)}。"
                    if lines_number
                    else "本扩展支持曲线输入。"
                )
            lines.append(f"- lines: {description}")
            continue
        if field_type.lower() == "line":
            description = (
                str(field.get("description") or "").strip()
                or "从当前数据集中选择 1 条曲线作为内部参数。"
            )
            default = field.get("default")
            parts = [
                f"{str(field.get('label') or key).strip() or key}（line，可选）",
                description,
            ]
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
