from __future__ import annotations

from typing import Type

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import Pivot, SegmentedWidget


class _NavigationTabBarAdapter:
    def __init__(self, parent: QWidget):
        self.addButton = QWidget(parent)
        self.addButton.hide()
        self.closeButtonDisplayMode = None

    def setAddButtonVisible(self, visible: bool) -> None:
        self.addButton.setVisible(bool(visible))

    def setCloseButtonDisplayMode(self, mode) -> None:
        self.closeButtonDisplayMode = mode


class _BaseNavigationStack(QWidget):
    currentChanged = Signal(int)

    def __init__(self, navigation_cls: Type[QWidget], parent=None, *, fill_width: bool = False):
        super().__init__(parent)
        self._fill_width = bool(fill_width)
        self.navigationWidget = navigation_cls(self)
        if self._fill_width:
            self.navigationWidget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.navigationWidget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.stackedWidget = QStackedWidget(self)
        self.tabBar = _NavigationTabBarAdapter(self)
        self._route_keys: list[str] = []
        self._labels: list[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        if self._fill_width:
            layout.addWidget(self.navigationWidget)
        else:
            layout.addWidget(self.navigationWidget, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.stackedWidget, 1)

        self.stackedWidget.currentChanged.connect(self._on_stack_changed)

    def addTab(self, widget: QWidget, text: str, route_key: str | None = None):
        index = self.stackedWidget.addWidget(widget)
        key = route_key or f"tab_{index}"
        self._route_keys.append(key)
        self._labels.append(text)
        self.navigationWidget.addItem(key, text, onClick=lambda checked=False, i=index: self.setCurrentIndex(i))
        self._sync_navigation_width()
        if self.count() == 1:
            self.setCurrentIndex(0)
        return index

    def _sync_navigation_width(self) -> None:
        if self._fill_width:
            self.navigationWidget.setMinimumWidth(0)
            self.navigationWidget.setMaximumWidth(16777215)
            return
        self.navigationWidget.adjustSize()
        hint_width = max(self.navigationWidget.sizeHint().width(), self.navigationWidget.minimumSizeHint().width())
        if hint_width <= 0:
            return
        self.navigationWidget.setFixedWidth(min(hint_width + 4, 420))

    def count(self) -> int:
        return self.stackedWidget.count()

    def widget(self, index: int) -> QWidget:
        return self.stackedWidget.widget(index)

    def tabText(self, index: int) -> str:
        return self._labels[index]

    def currentIndex(self) -> int:
        return self.stackedWidget.currentIndex()

    def currentWidget(self) -> QWidget:
        return self.stackedWidget.currentWidget()

    def setCurrentIndex(self, index: int) -> None:
        if index < 0 or index >= self.count():
            return
        self.stackedWidget.setCurrentIndex(index)
        self.navigationWidget.setCurrentItem(self._route_keys[index])

    def _on_stack_changed(self, index: int) -> None:
        if 0 <= index < len(self._route_keys):
            route_key = self._route_keys[index]
            if self.navigationWidget.currentRouteKey() != route_key:
                self.navigationWidget.setCurrentItem(route_key)
        self.currentChanged.emit(index)


class PivotStackWidget(_BaseNavigationStack):
    def __init__(self, parent=None, *, fill_width: bool = False):
        super().__init__(Pivot, parent, fill_width=fill_width)


class SegmentedStackWidget(_BaseNavigationStack):
    def __init__(self, parent=None, *, fill_width: bool = False):
        super().__init__(SegmentedWidget, parent, fill_width=fill_width)