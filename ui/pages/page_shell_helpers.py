from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QSplitter, QWidget


def sync_vertical_splitter_sizes(
    splitter: QSplitter | None,
    *,
    user_resized: bool,
    upper_ratio: float,
) -> None:
    """按比例复位纵向 splitter 的大小。"""
    if splitter is None or user_resized:
        return
    try:
        total_height = splitter.height()
    except RuntimeError:
        return
    if total_height <= 0:
        return
    upper = max(1, int(total_height * upper_ratio))
    lower = max(1, total_height - upper)
    try:
        with QSignalBlocker(splitter):
            splitter.setSizes([upper, lower])
    except RuntimeError:
        return


def apply_splitter_panel_visibility(
    splitter: QSplitter | None,
    panel: QWidget | None,
    visible: bool,
    *,
    visible_sizes: Sequence[int],
    hidden_sizes: Sequence[int],
) -> None:
    """统一处理 splitter 里扩展面板的显隐与尺寸同步。"""
    if splitter is None or panel is None:
        return
    try:
        if visible:
            panel.show()
            splitter.setSizes(list(visible_sizes))
            return
        panel.hide()
        splitter.setSizes(list(hidden_sizes))
    except RuntimeError:
        return


class ExtensionPanelShellMixin:
    """为带扩展面板的页面提供统一的壳层接口。"""

    def supports_extension_panel_toggle(self) -> bool:
        return True

    def is_extension_panel_visible(self) -> bool:
        view_state = getattr(self, "_view_state", None)
        return bool(getattr(view_state, "extension_panel_visible", False))

    def set_extension_panel_visible(self, visible: bool) -> None:
        view_state = getattr(self, "_view_state", None)
        if view_state is not None:
            view_state.extension_panel_visible = bool(visible)
        splitter = self._extension_panel_splitter()
        panel = getattr(self, "_extension_panel", None)
        if splitter is None or panel is None or view_state is None:
            return
        apply_splitter_panel_visibility(
            splitter,
            panel,
            view_state.extension_panel_visible,
            visible_sizes=self._extension_panel_visible_sizes(),
            hidden_sizes=self._extension_panel_hidden_sizes(),
        )

    def _extension_panel_splitter(self) -> QSplitter | None:
        raise NotImplementedError

    def _extension_panel_visible_sizes(self) -> Sequence[int]:
        raise NotImplementedError

    def _extension_panel_hidden_sizes(self) -> Sequence[int]:
        raise NotImplementedError
