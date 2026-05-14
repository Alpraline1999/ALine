from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class AnalysisWorkspaceState:
    selected_inputs: list[dict[str, Any]] = field(default_factory=list)
    current_report_template_id: str | None = None
    current_report_template_name: str = "默认模板"
    report_template_ids: list[str | None] = field(default_factory=lambda: [None])
    selected_tree_kind: str | None = None
    selected_tree_node_id: str | None = None


class AnalysisWorkspaceController:
    def __init__(self, state: AnalysisWorkspaceState) -> None:
        self.state = state

    def handle_tree_selected(self, kind: str, node_id: str) -> None:
        self.state.selected_tree_kind = kind
        self.state.selected_tree_node_id = node_id

    def handle_tree_activated(self, kind: str, node_id: str) -> tuple[str, str] | None:
        if kind.endswith("_to_analysis"):
            kind = kind[:-12]
        return kind, node_id

    def resolve_target_folder(self, project_manager, default_type: str = "datasets") -> Optional[str]:
        return project_manager.get_analysis_result_target_folder_id(self.state.selected_tree_node_id)
