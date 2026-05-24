"""AI 工具管理对话框 — 新建/编辑 AIPrompt"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    BodyLabel, FluentIcon as FIF,
    InfoBar, InfoBarPosition,
    LineEdit, MessageBoxBase, PlainTextEdit, PushButton,
    SubtitleLabel,
)

from core.global_assets import global_assets
from ui.widgets.focus_commit import install_click_away_focus_commit


class AIToolDialog(MessageBoxBase):
    """新建或编辑 AI Prompt。

    用法：
        dlg = AIToolDialog(parent, tool_id=existing_id)
        if dlg.exec():
            # 已保存
    """

    def __init__(self, parent=None, tool_id: Optional[str] = None):
        super().__init__(parent)
        self._tool_id = tool_id
        self._is_edit = tool_id is not None
        self.setWindowTitle("编辑 Prompt" if self._is_edit else "新建 Prompt")
        self._setup_ui()
        self._click_away_focus_commit = install_click_away_focus_commit(self.widget)
        if self._is_edit:
            self._load_existing()

    def _setup_ui(self):
        # 名称
        name_row = QHBoxLayout()
        name_row.addWidget(BodyLabel("名称:"))
        self._name_edit = LineEdit(self.widget)
        self._name_edit.setPlaceholderText("Prompt 名称（必填）")
        name_row.addWidget(self._name_edit, 1)
        self.viewLayout.addLayout(name_row)

        # 描述
        desc_row = QHBoxLayout()
        desc_row.addWidget(BodyLabel("描述:"))
        self._desc_edit = LineEdit(self.widget)
        self._desc_edit.setPlaceholderText("简短描述（可选）")
        desc_row.addWidget(self._desc_edit, 1)
        self.viewLayout.addLayout(desc_row)

        # 内容编辑区
        self.viewLayout.addWidget(SubtitleLabel("内容", self.widget))
        self._content_edit = PlainTextEdit(self.widget)
        self._content_edit.setPlaceholderText(
            "在此输入提示词模板…\n可使用 {series_name}、{equation} 等占位符"
        )
        self.viewLayout.addWidget(self._content_edit, 1)

        # 底部按钮
        self.yesButton.setText("保存")
        self.cancelButton.setText("取消")

        self.widget.setMinimumWidth(520)

    def _load_existing(self):
        if self._tool_id is None:
            return
        obj = global_assets.get_ai_prompt(self._tool_id)
        if obj:
            self._name_edit.setText(obj.name)
            self._desc_edit.setText(getattr(obj, "description", ""))
            self._content_edit.setPlainText(obj.content)

    def validate(self) -> bool:
        name = self._name_edit.text().strip()
        if not name:
            InfoBar.warning("提示", "名称不能为空", parent=self,
                            position=InfoBarPosition.TOP, duration=2000)
            return False
        content = self._content_edit.toPlainText()
        desc = self._desc_edit.text().strip()

        if self._is_edit:
            return self._do_update(name, content, desc)
        return self._do_create(name, content, desc)

    def _do_create(self, name, content, desc) -> bool:
        obj = global_assets.add_ai_prompt(name, content, desc)
        return obj is not None

    def _do_update(self, name, content, desc) -> bool:
        if self._tool_id is None:
            return False
        return global_assets.update_ai_prompt(self._tool_id, name=name, content=content, description=desc)
