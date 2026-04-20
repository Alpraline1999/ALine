from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import BodyLabel, MessageBoxBase, PushButton, SubtitleLabel

from ui.theme import WORKBENCH_BUTTON_MIN_WIDTH, apply_button_metrics
from ui.widgets.project_tree import ProjectTreeWidget


class ProjectTreeManageDialog(MessageBoxBase):
    project_modified = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title_label = SubtitleLabel("项目树管理", self.widget)
        self._selection_label = BodyLabel("未选择节点", self.widget)
        self._selection_label.setWordWrap(True)

        self._tree = ProjectTreeWidget(self.widget)
        self._tree.refresh()

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self._refresh_btn = PushButton("刷新", self.widget)
        self._refresh_btn.clicked.connect(self._refresh_tree)
        button_row.addWidget(self._refresh_btn)

        self._rename_btn = PushButton("重命名", self.widget)
        self._rename_btn.clicked.connect(self._tree.rename_selected_item)
        button_row.addWidget(self._rename_btn)

        self._move_btn = PushButton("移动", self.widget)
        self._move_btn.clicked.connect(self._tree.move_selected_items)
        button_row.addWidget(self._move_btn)

        self._delete_btn = PushButton("删除", self.widget)
        self._delete_btn.clicked.connect(self._tree.delete_selected_items)
        button_row.addWidget(self._delete_btn)

        apply_button_metrics(
            self._refresh_btn,
            self._rename_btn,
            self._move_btn,
            self._delete_btn,
            min_width=WORKBENCH_BUTTON_MIN_WIDTH,
        )

        self.viewLayout.addWidget(self._title_label)
        self.viewLayout.addWidget(self._selection_label)
        self.viewLayout.addLayout(button_row)
        self.viewLayout.addWidget(self._tree)
        self.widget.setMinimumSize(760, 600)

        self.yesButton.setText("关闭")
        self.cancelButton.hide()

        self._tree._tree.itemSelectionChanged.connect(self._update_action_buttons)
        self._tree.project_modified.connect(self._on_tree_modified)
        self._update_action_buttons()

    def _refresh_tree(self) -> None:
        self._tree.refresh()
        self._update_action_buttons()

    def _on_tree_modified(self) -> None:
        self._tree.refresh()
        self._update_action_buttons()
        self.project_modified.emit()

    def _update_action_buttons(self) -> None:
        selected_items = self._tree._selected_items_or_current()
        if not selected_items:
            self._selection_label.setText("未选择节点")
        else:
            self._selection_label.setText(f"已选 {len(selected_items)} 项")
        self._rename_btn.setEnabled(self._tree.can_rename_selected_item())
        self._move_btn.setEnabled(self._tree.can_move_selected_items())
        self._delete_btn.setEnabled(self._tree.can_delete_selected_items())