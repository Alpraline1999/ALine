from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class ChartWorkspaceState:
    chart_series: list[dict[str, Any]] = field(default_factory=list)
    curve_styles: dict[str, dict[str, Any]] = field(default_factory=dict)
    style_target: str | None = None
    figure_state: Any = None
    plot_style_refs: list[Optional[str]] = field(default_factory=lambda: [None])
    applied_plot_style_ref: str | None = None
    active_template_node_id: str | None = None
    curve_style_template_ids: list[Optional[str]] = field(default_factory=lambda: [None])
    active_curve_style_ref: str | None = None
    active_curve_style_template_id: str | None = None
    current_plot_theme_id: str | None = None
    plot_extension_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    applied_plot_extensions: list[dict[str, Any]] = field(default_factory=list)
    plot_extension_instance_seed: int = 0
    style_change_sequence: int = 0
    figure_state_change_versions: dict[str, int] = field(default_factory=dict)
    plot_style_extra_versions: dict[tuple[str, ...], int] = field(default_factory=dict)
    curve_style_change_versions: dict[str, dict[str, int]] = field(default_factory=dict)
    plot_style_extras: dict[str, Any] = field(default_factory=dict)
    legend_anchor_x_draft: str = ""
    legend_anchor_y_draft: str = ""
    preserve_partial_legend_anchor_draft: bool = False
    display_dpi: float = 100.0
    display_canvas_size: tuple[int, int] | None = None
    selected_tree_kind: str | None = None
    selected_tree_id: str | None = None


class ChartWorkspaceController:
    def __init__(self, state: ChartWorkspaceState) -> None:
        self.state = state

    def handle_tree_selected(self, kind: str, node_id: str) -> None:
        self.state.selected_tree_kind = kind
        self.state.selected_tree_id = node_id

    def clear_series_selection(self) -> None:
        self.state.style_target = None
