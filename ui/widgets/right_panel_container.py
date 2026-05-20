from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from ui.widgets.ai_assistant_panel import AIAssistantPanel
from ui.widgets.extension_panel import ExtensionConfigPanel
from ui.widgets.navigation_stack import SegmentedStackWidget


class RightPanelContainer(QWidget):
    """右侧面板容器：用 SegmentedStackWidget 在"扩展"和"AI"之间切换。

    替换各工作台页面中直接添加的 ExtensionConfigPanel，将扩展面板和 AI 面板
    放在同一位置通过 tab 切换。保持与 ExtensionPanelShellMixin 的兼容性。
    """

    panel_toggled = Signal(bool)       # visible → signal(True)

    def __init__(
        self,
        page_name: str,
        extension_title: str = "",
        action_text: str = "应用扩展",
        parent: QWidget | None = None,
        *,
        mode: str = "help_only",
        framed: bool = True,
    ):
        super().__init__(parent)
        self._page_name = page_name
        self.setMinimumWidth(360)
        self.setMaximumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # SegmentedStackWidget: tab bar + stacked widget
        self._tabs = SegmentedStackWidget(self, fill_width=True)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Tab 0: 扩展面板
        self.extension_panel = ExtensionConfigPanel(
            extension_title or "扩展",
            action_text,
            self,
            mode=mode,
            framed=framed,
        )
        self._tabs.addTab(self.extension_panel, "扩展")

        # Tab 1: AI 面板
        self.ai_panel = AIAssistantPanel(page_name, self)
        self._tabs.addTab(self.ai_panel, "AI")

        layout.addWidget(self._tabs, 1)

    def _on_tab_changed(self, index: int) -> None:
        """切换 tab 时同步 AI 面板的上下文。"""
        if index == 1:
            self.ai_panel.refresh_context()

    def current_index(self) -> int:
        return self._tabs.currentIndex()

    def set_current_index(self, index: int) -> None:
        self._tabs.setCurrentIndex(index)

    def set_context(self, *args: Any, **kwargs: Any) -> None:
        """委托给扩展面板（兼容 ExtensionPanelShellMixin）"""
        self.extension_panel.set_context(*args, **kwargs)

    def set_status_context(self, *args: Any, **kwargs: Any) -> None:
        """委托给扩展面板（兼容 ExtensionPanelShellMixin）"""
        self.extension_panel.set_status_context(*args, **kwargs)
