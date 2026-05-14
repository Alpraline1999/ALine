from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from PySide6.QtCore import QItemSelectionModel, QModelIndex, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel

if TYPE_CHECKING:
    from ui.widgets.project_tree_view import ProjectTreeView


class ProjectTreeItem:
    """项目树节点的轻量适配器。

    底层使用 ``QStandardItem``，但向上层暴露接近 ``QTreeWidgetItem`` 的接口，
    方便现有树逻辑逐步迁移到 model/view 架构。
    """

    def __init__(self, item: QStandardItem, view: Optional["ProjectTreeView"] = None):
        self._item = item
        self._view = view
        self._expanded = False

    @property
    def qitem(self) -> QStandardItem:
        return self._item

    def bind_view(self, view: "ProjectTreeView") -> None:
        self._view = view
        for index in range(self.childCount()):
            child = self.child(index)
            if child is not None:
                child.bind_view(view)

    def _index(self, column: int = 0) -> QModelIndex:
        if self._view is None or column != 0:
            return QModelIndex()
        return self._item.index()

    def _parent_index(self) -> QModelIndex:
        parent = self.parent()
        if parent is None:
            return QModelIndex()
        return parent.qitem.index() if self._view is not None else QModelIndex()

    def text(self, column: int = 0) -> str:
        return self._item.text() if column == 0 else ""

    def setText(self, column: int, text: str) -> None:
        if column == 0:
            self._item.setText(text)

    def data(self, column_or_role, role: Optional[int] = None):
        if role is None:
            role = int(column_or_role)
        return self._item.data(role)

    def setData(self, column_or_role, role=None, value=None) -> None:
        if value is None and role is not None:
            value = role
            role = int(column_or_role)
        elif value is None:
            raise TypeError("setData requires a value")
        self._item.setData(value, int(role))

    def icon(self, column: int = 0):
        return self._item.icon() if column == 0 else self._item.icon()

    def setIcon(self, column: int, icon) -> None:
        if column == 0:
            self._item.setIcon(icon)

    def toolTip(self, column: int = 0) -> str:
        return self._item.toolTip() if column == 0 else ""

    def setToolTip(self, column: int, text: str) -> None:
        if column == 0:
            self._item.setToolTip(text)

    def font(self, column: int = 0):
        return self._item.font() if column == 0 else self._item.font()

    def setFont(self, column: int, font) -> None:
        if column == 0:
            self._item.setFont(font)

    def sizeHint(self, column: int = 0):
        return self._item.sizeHint() if column == 0 else self._item.sizeHint()

    def setSizeHint(self, column: int, size) -> None:
        if column == 0:
            self._item.setSizeHint(size)

    def flags(self):
        return self._item.flags()

    def setFlags(self, flags) -> None:
        self._item.setFlags(flags)

    def row(self) -> int:
        return self._item.row()

    def childCount(self) -> int:
        return self._item.rowCount()

    def child(self, index: int) -> Optional["ProjectTreeItem"]:
        if index < 0 or index >= self.childCount():
            return None
        if self._view is None:
            return ProjectTreeItem(self._item.child(index))
        return self._view.wrap_item(self._item.child(index))

    def parent(self) -> Optional["ProjectTreeItem"]:
        parent_item = self._item.parent()
        if parent_item is None:
            return None
        if self._view is None:
            return ProjectTreeItem(parent_item)
        return self._view.wrap_item(parent_item)

    def addChild(self, child: "ProjectTreeItem") -> None:
        child_item = child.qitem if isinstance(child, ProjectTreeItem) else child
        self._item.appendRow(child_item)
        if self._view is not None and isinstance(child, ProjectTreeItem):
            child.bind_view(self._view)

    def removeChild(self, child: "ProjectTreeItem") -> None:
        if child is None:
            return
        child_item = child.qitem if isinstance(child, ProjectTreeItem) else child
        row = child_item.row()
        if row >= 0:
            self._item.removeRow(row)

    def takeChildren(self):
        children = []
        while self.childCount() > 0:
            children.append(self.child(0))
            self._item.removeRow(0)
        return children

    def isExpanded(self) -> bool:
        if self._view is None:
            return self._expanded
        index = self._index()
        return bool(index.isValid() and self._view.isExpanded(index))

    def setExpanded(self, expanded: bool) -> None:
        self._expanded = bool(expanded)
        if self._view is None:
            return
        index = self._index()
        if index.isValid():
            if expanded:
                self._view.expand(index)
            else:
                self._view.collapse(index)

    def isHidden(self) -> bool:
        if self._view is None:
            return False
        index = self._index()
        if not index.isValid():
            return False
        parent_index = self._parent_index()
        return bool(self._view.isRowHidden(self.row(), parent_index))

    def setHidden(self, hidden: bool) -> None:
        if self._view is None:
            return
        index = self._index()
        if index.isValid():
            self._view.setRowHidden(self.row(), self._parent_index(), bool(hidden))

    def isSelected(self) -> bool:
        if self._view is None or self._view.selectionModel() is None:
            return False
        index = self._index()
        return bool(index.isValid() and self._view.selectionModel().isSelected(index))

    def setSelected(self, selected: bool) -> None:
        if self._view is None:
            return
        index = self._index()
        if not index.isValid() or self._view.selectionModel() is None:
            return
        flags = QItemSelectionModel.SelectionFlag.Select if selected else QItemSelectionModel.SelectionFlag.Deselect
        self._view.selectionModel().select(index, flags)
        if selected:
            self._view.setCurrentIndex(index)


class ProjectTreeModel(QStandardItemModel):
    def __init__(self, parent=None):
        super().__init__(0, 1, parent)
        self.setColumnCount(1)

    def create_item(self, text: str = "", *, view: Optional["ProjectTreeView"] = None) -> ProjectTreeItem:
        item = QStandardItem(text)
        item.setEditable(False)
        return ProjectTreeItem(item, view=view)
