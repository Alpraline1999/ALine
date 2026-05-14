from __future__ import annotations

from typing import Optional, Protocol

from PySide6.QtCore import QModelIndex, QItemSelectionModel, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QTreeView, QWidget

from .project_tree_model import ProjectTreeItem, ProjectTreeModel


class ProjectTreeViewOwner(Protocol):
    def _remember_drag_source_items(self, items) -> None: ...
    def _drag_source_items_for_drop(self, current_item): ...
    def _perform_batch_drop_move(self, source_items, target_item, *, defer_view_refresh: bool) -> bool: ...
    def _perform_drop_move(self, source_item, target_item, *, defer_view_refresh: bool) -> bool: ...
    def _clear_drag_source_item(self) -> None: ...
    def can_rename_selected_item(self) -> bool: ...
    def rename_selected_item(self) -> None: ...


class ProjectTreeView(QTreeView):
    itemClicked = Signal(object, int)
    itemActivated = Signal(object, int)
    itemExpanded = Signal(object)
    itemCollapsed = Signal(object)
    itemChanged = Signal(object, int)

    def __init__(self, owner: ProjectTreeViewOwner, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._owner = owner
        self._model = ProjectTreeModel(self)
        self._item_cache: dict[int, ProjectTreeItem] = {}
        self.setModel(self._model)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setUniformRowHeights(False)
        self.setItemsExpandable(True)
        self.setRootIsDecorated(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.clicked.connect(self._emit_item_clicked)
        self.doubleClicked.connect(self._emit_item_activated)
        self.expanded.connect(self._emit_item_expanded)
        self.collapsed.connect(self._emit_item_collapsed)
        self._model.itemChanged.connect(self._emit_item_changed)

    def create_item(self, text: str = "") -> ProjectTreeItem:
        item = self._model.create_item(text, view=self)
        self._item_cache[id(item.qitem)] = item
        return item

    def _wrap_qitem(self, qitem) -> ProjectTreeItem:
        if qitem is None:
            return None
        cache_key = id(qitem)
        item = self._item_cache.get(cache_key)
        if item is None:
            item = ProjectTreeItem(qitem, view=self)
            self._item_cache[cache_key] = item
        else:
            item.bind_view(self)
        return item

    def wrap_item(self, qitem) -> ProjectTreeItem:
        return self._wrap_qitem(qitem)

    def _index_to_item(self, index: QModelIndex) -> Optional[ProjectTreeItem]:
        if not index.isValid():
            return None
        return self._wrap_qitem(self._model.itemFromIndex(index))

    def _item_to_index(self, item: Optional[ProjectTreeItem], column: int = 0) -> QModelIndex:
        if item is None:
            return QModelIndex()
        if isinstance(item, ProjectTreeItem):
            return item.qitem.index()
        return QModelIndex()

    def clear(self) -> None:
        self._item_cache.clear()
        self._model.clear()
        self._model.setColumnCount(1)

    def addTopLevelItem(self, item: ProjectTreeItem) -> None:
        if item is None:
            return
        item.bind_view(self)
        self._model.invisibleRootItem().appendRow(item.qitem)

    def topLevelItemCount(self) -> int:
        return self._model.rowCount()

    def topLevelItem(self, index: int) -> Optional[ProjectTreeItem]:
        if index < 0 or index >= self.topLevelItemCount():
            return None
        return self._wrap_qitem(self._model.item(index))

    def invisibleRootItem(self) -> ProjectTreeItem:
        return self._wrap_qitem(self._model.invisibleRootItem())

    def currentItem(self) -> Optional[ProjectTreeItem]:
        return self._index_to_item(self.currentIndex())

    def setCurrentItem(self, item: Optional[ProjectTreeItem], column: int = 0, selection_flag: Optional[QItemSelectionModel.SelectionFlag] = None) -> None:
        index = self._item_to_index(item, column)
        if not index.isValid():
            return
        selection_model = self.selectionModel()
        if selection_model is not None:
            if selection_flag is None:
                selection_model.select(index, QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows)
                self.setCurrentIndex(index)
                return
            selection_model.setCurrentIndex(index, selection_flag)

    def selectedItems(self):
        selected = []
        seen: set[int] = set()
        selection_model = self.selectionModel()
        if selection_model is None:
            return selected
        for index in selection_model.selectedRows(0):
            item = self._index_to_item(index)
            if item is None:
                continue
            cache_key = id(item.qitem)
            if cache_key in seen:
                continue
            seen.add(cache_key)
            selected.append(item)
        return selected

    def clearSelection(self) -> None:
        selection_model = self.selectionModel()
        if selection_model is not None:
            selection_model.clearSelection()

    def itemAt(self, pos):
        return self._index_to_item(self.indexAt(pos))

    def indexFromItem(self, item: Optional[ProjectTreeItem], column: int = 0) -> QModelIndex:
        return self._item_to_index(item, column)

    def itemFromIndex(self, index: QModelIndex) -> Optional[ProjectTreeItem]:
        return self._index_to_item(index)

    def scrollToItem(self, item: Optional[ProjectTreeItem], hint: QAbstractItemView.ScrollHint = QAbstractItemView.ScrollHint.EnsureVisible) -> None:
        index = self._item_to_index(item)
        if index.isValid():
            self.scrollTo(index, hint)

    def visualItemRect(self, item: Optional[ProjectTreeItem]):
        index = self._item_to_index(item)
        return self.visualRect(index)

    def expandItem(self, item: Optional[ProjectTreeItem]) -> None:
        index = self._item_to_index(item)
        if index.isValid():
            self.expand(index)

    def collapseItem(self, item: Optional[ProjectTreeItem]) -> None:
        index = self._item_to_index(item)
        if index.isValid():
            self.collapse(index)

    def _emit_item_clicked(self, index: QModelIndex) -> None:
        item = self._index_to_item(index)
        if item is not None:
            self.itemClicked.emit(item, 0)

    def _emit_item_activated(self, index: QModelIndex) -> None:
        item = self._index_to_item(index)
        if item is not None:
            self.itemActivated.emit(item, 0)

    def _emit_item_expanded(self, index: QModelIndex) -> None:
        item = self._index_to_item(index)
        if item is not None:
            self.itemExpanded.emit(item)

    def _emit_item_collapsed(self, index: QModelIndex) -> None:
        item = self._index_to_item(index)
        if item is not None:
            self.itemCollapsed.emit(item)

    def _emit_item_changed(self, qitem) -> None:
        item = self._wrap_qitem(qitem)
        if item is not None:
            self.itemChanged.emit(item, 0)

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
