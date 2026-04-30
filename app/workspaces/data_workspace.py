from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DataWorkspaceState:
    selected_type: str | None = None
    selected_id: str | None = None
    selected_node_kind: str | None = None
    selected_node_id: str | None = None
    preview_xs: list[float] = field(default_factory=list)
    preview_ys: list[float] = field(default_factory=list)
    preview_name: str = ""
    preview_x_label: str = "X"
    preview_y_label: str = "Y"
    pending_import_paths: list[str] = field(default_factory=list)
    pending_import_names: dict[str, str] = field(default_factory=dict)
    node_preview_states: dict[str, Any] = field(default_factory=dict)
    current_extension_config_id: str | None = None


class DataWorkspaceController:
    def __init__(self, state: DataWorkspaceState) -> None:
        self.state = state

    def handle_tree_selected(self, kind: str, node_id: str) -> None:
        self.state.selected_node_kind = kind
        self.state.selected_node_id = node_id

    def clear_selection(self) -> None:
        self.state.selected_type = None
        self.state.selected_id = None
        self.state.selected_node_kind = None
        self.state.selected_node_id = None
