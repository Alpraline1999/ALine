from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ChartPageViewState:
    extension_panel_visible: bool = False
    extension_panel_width: int = 360
    chart_left_splitter_user_resized: bool = False
    chart_list_tooltip_visible: bool = False


@dataclass(slots=True)
class AnalysisPageViewState:
    extension_panel_visible: bool = False
    extension_panel_width: int = 360
    input_panel_splitter_user_resized: bool = False


@dataclass(slots=True)
class DigitizePageViewState:
    extension_panel_visible: bool = False
    extension_panel_width: int = 360
    right_splitter_initialized: bool = False
    right_splitter_user_resized: bool = False


@dataclass(slots=True)
class MainWindowViewState:
    tree_panel_user_hidden: bool = False
    tree_panel_width: int = 260
    shared_extension_panel_visible: bool = False


@dataclass(slots=True)
class ProcessPageViewState:
    extension_panel_visible: bool = False
    extension_panel_width: int = 360
    selected_input_splitter_user_resized: bool = False


@dataclass(slots=True)
class SettingsPageViewState:
    extension_height_refresh_pending: bool = False


@dataclass(slots=True)
class DataPageViewState:
    pending_import_states: dict[str, Any] = field(default_factory=dict)
    external_browser_dir: str | None = None
    show_hidden_browser_entries: bool = False
    data_file_preview_node_id: str | None = None
    preview_image_path: str | None = None
    current_source_preview_total_rows: int = 0
    fluent_tooltip: Any = None
    fluent_tooltip_views: dict[Any, Any] = field(default_factory=dict)
    shortcut_bindings: Any = None
