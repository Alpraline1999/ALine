from __future__ import annotations

from typing import Optional, Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import TreeWidget


class ProjectTreeViewOwner(Protocol):
    def _remember_drag_source_items(self, items) -> None: ...
    def _drag_source_items_for_drop(self, current_item): ...
    def _perform_batch_drop_move(self, source_items, target_item, *, defer_view_refresh: bool) -> bool: ...
    def _perform_drop_move(self, source_item, target_item, *, defer_view_refresh: bool) -> bool: ...
    def _clear_drag_source_item(self) -> None: ...
    def can_rename_selected_item(self) -> bool: ...
    def rename_selected_item(self) -> None: ...


class ProjectTreeView(TreeWidget):
    def __init__(self, owner: ProjectTreeViewOwner, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._owner = owner

    def startDrag(self, supportedActions) -> None:
        selected_items = [item for item in self.selectedItems() if item is not None]
        current_item = self.currentItem()
        if current_item is not None and current_item in selected_items:
            self._owner._remember_drag_source_items(selected_items)
        elif current_item is not None:
            self._owner._remember_drag_source_items([current_item])
        else:
            self._owner._remember_drag_source_items(selected_items)
        super().startDrag(supportedActions)

    def dropEvent(self, event) -> None:
        source_items = self._owner._drag_source_items_for_drop(self.currentItem())
        target_item = self.itemAt(event.position().toPoint())
        try:
            if len(source_items) > 1:
                if self._owner._perform_batch_drop_move(source_items, target_item, defer_view_refresh=True):
                    event.acceptProposedAction()
                    return
                event.ignore()
                return
            source_item = source_items[0] if source_items else None
            if self._owner._perform_drop_move(source_item, target_item, defer_view_refresh=True):
                event.acceptProposedAction()
                return
            event.ignore()
        finally:
            self._owner._clear_drag_source_item()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F2 and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            if self._owner.can_rename_selected_item():
                self._owner.rename_selected_item()
                event.accept()
                return
        super().keyPressEvent(event)
