from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DigitizeWorkspaceState:
    current_image_id: str | None = None
    current_curve_id: str | None = None
    export_target_kind: str | None = None
    export_target_id: str | None = None
    last_export_suggestion: str = ""
    current_curve_points: list[Any] = field(default_factory=list)
    active_tool: str | None = None
    hidden_curves: set[str] = field(default_factory=set)
    undo_stack: list[Any] = field(default_factory=list)
    redo_stack: list[Any] = field(default_factory=list)
    max_history: int = 50
    is_undo_redo: bool = False
    sampled_color: Any = None
    auto_preview_points: list[Any] = field(default_factory=list)
    shape_template: dict[str, Any] | None = None
    auto_mode_type_ids: list[str] = field(default_factory=list)
    pending_digitize_field_key: str | None = None
    pending_digitize_field_type: str | None = None


class DigitizeWorkspaceController:
    def __init__(self, state: DigitizeWorkspaceState) -> None:
        self.state = state

    def set_current_image(self, image_id: str | None) -> None:
        self.state.current_image_id = image_id

    def set_current_curve(self, curve_id: str | None) -> None:
        self.state.current_curve_id = curve_id

    def set_export_target(self, kind: str | None, target_id: str | None) -> None:
        self.state.export_target_kind = kind
        self.state.export_target_id = target_id

    def clear_pending_interaction(self) -> None:
        self.state.pending_digitize_field_key = None
        self.state.pending_digitize_field_type = None

    def set_active_tool(self, tool_name: str | None) -> None:
        self.state.active_tool = tool_name
