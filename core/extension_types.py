from __future__ import annotations

"""扩展运行时的中性类型与共享帮助函数。"""

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TaskProgress:
    """后台任务进度模型。

    供后续异步执行框架使用；当前仅定义模型不做执行集成。
    """
    task_id: str
    task_type: str = ""
    status: str = "running"  # running / completed / failed / cancelled
    progress_text: str = ""
    progress_percent: float = 0.0
    result: Any = None
    error: Optional[str] = None


class PatchAuthority(Enum):
    """扩展 patch 的决策等级。

    ADVISORY:      建议值。不覆盖用户手动修改的同字段。
    AUTHORITATIVE: 强制值。可覆盖用户手动修改，需 UI 中提示。
    """
    ADVISORY = "advisory"
    AUTHORITATIVE = "authoritative"

__all__ = [
    "TaskProgress",
    "PatchAuthority",
    "merge_nested_dict",
    "normalize_plot_extension_phases",
    "PlotExtensionContext",
]


def merge_nested_dict(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_nested_dict(result[key], value)
            continue
        result[key] = copy.deepcopy(value)
    return result


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
        self.plot_style_extras = merge_nested_dict(self.plot_style_extras, clean_patch)
        self.plot_style_patch = merge_nested_dict(self.plot_style_patch, clean_patch)

    def patch_curve_style(self, curve_identity: Optional[str], patch: Dict[str, Any]) -> None:
        target_identity = str(curve_identity or "").strip()
        clean_patch = copy.deepcopy(dict(patch or {}))
        if not target_identity or not clean_patch:
            return

        existing_patch = self.curve_style_patches.get(target_identity, {})
        self.curve_style_patches[target_identity] = merge_nested_dict(existing_patch, clean_patch)

        if self.selected_series_identity == target_identity and isinstance(self.selected_series, dict):
            current_style = dict(self.selected_series.get("style") or {})
            current_style = merge_nested_dict(current_style, clean_patch)
            self.selected_series["style"] = current_style

        for series in self.visible_series:
            identity = str(series.get("curve_identity") or series.get("obj_id") or series.get("name") or "").strip()
            if identity != target_identity:
                continue
            current_style = dict(series.get("style") or {})
            current_style = merge_nested_dict(current_style, clean_patch)
            series["style"] = current_style

    def patch_selected_curve_style(self, patch: Dict[str, Any]) -> None:
        self.patch_curve_style(self.selected_series_identity, patch)

    def clear_style_patches(self) -> None:
        self.figure_state_patch.clear()
        self.plot_style_patch.clear()
        self.curve_style_patches.clear()
