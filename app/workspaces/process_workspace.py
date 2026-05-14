from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class ProcessWorkspaceState:
    selected_inputs: list[dict[str, Any]] = field(default_factory=list)
    src_series_batch: list[object] = field(default_factory=list)
    out_series_batch: list[object] = field(default_factory=list)
    pipeline_warnings: list[str] = field(default_factory=list)
    selected_src_id: str | None = None
    selected_source_kind: str | None = None
    selected_source_node_id: str | None = None
    current_pipeline_id: str | None = None
    save_target_ids: list[str | None] = field(default_factory=list)


class ProcessWorkspaceController:
    def __init__(self, state: ProcessWorkspaceState) -> None:
        self.state = state

    def receive_data_request(self, data_type: str, obj_id: str) -> None:
        self.state.selected_source_kind = data_type
        self.state.selected_source_node_id = obj_id

    def handle_tree_activated(self, kind: str, node_id: str) -> tuple[str, str] | None:
        if kind.endswith("_to_process"):
            kind = kind[:-11]
        if kind in ("series", "curve", "data_file", "image_work"):
            self.receive_data_request(kind, node_id)
            return kind, node_id
        return None

    def resolve_target_folder(self, project_manager, default_type: str = "datasets") -> Optional[str]:
        return project_manager.get_source_file_target_folder_id(self.state.selected_source_node_id)
