from __future__ import annotations

from pathlib import Path
from typing import Any

from ui.page_view_state import DataPageViewState


class DataPageStateBridge:
    def __init__(self, state: DataPageViewState | None = None) -> None:
        self.state = state or DataPageViewState()

    @property
    def pending_import_states(self) -> dict[str, Any]:
        return self.state.pending_import_states

    @pending_import_states.setter
    def pending_import_states(self, value: dict[str, Any]) -> None:
        self.state.pending_import_states = value

    @property
    def external_browser_dir(self) -> Path | None:
        raw = self.state.external_browser_dir
        return Path(raw) if raw else None

    @external_browser_dir.setter
    def external_browser_dir(self, value: Path | str | None) -> None:
        self.state.external_browser_dir = str(value) if value is not None else None

    @property
    def show_hidden_browser_entries(self) -> bool:
        return self.state.show_hidden_browser_entries

    @show_hidden_browser_entries.setter
    def show_hidden_browser_entries(self, value: bool) -> None:
        self.state.show_hidden_browser_entries = bool(value)

    @property
    def data_file_preview_node_id(self) -> str | None:
        return self.state.data_file_preview_node_id

    @data_file_preview_node_id.setter
    def data_file_preview_node_id(self, value: str | None) -> None:
        self.state.data_file_preview_node_id = value

    @property
    def preview_image_path(self) -> str | None:
        return self.state.preview_image_path

    @preview_image_path.setter
    def preview_image_path(self, value: str | None) -> None:
        self.state.preview_image_path = value

    @property
    def current_source_preview_total_rows(self) -> int:
        return self.state.current_source_preview_total_rows

    @current_source_preview_total_rows.setter
    def current_source_preview_total_rows(self, value: int) -> None:
        self.state.current_source_preview_total_rows = max(0, int(value))

    @property
    def fluent_tooltip(self) -> Any:
        return self.state.fluent_tooltip

    @fluent_tooltip.setter
    def fluent_tooltip(self, value: Any) -> None:
        self.state.fluent_tooltip = value

    @property
    def fluent_tooltip_views(self) -> dict[Any, Any]:
        return self.state.fluent_tooltip_views

    @fluent_tooltip_views.setter
    def fluent_tooltip_views(self, value: dict[Any, Any]) -> None:
        self.state.fluent_tooltip_views = value

    @property
    def shortcut_bindings(self) -> Any:
        return self.state.shortcut_bindings

    @shortcut_bindings.setter
    def shortcut_bindings(self, value: Any) -> None:
        self.state.shortcut_bindings = value
