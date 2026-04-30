from __future__ import annotations

from dataclasses import dataclass


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
