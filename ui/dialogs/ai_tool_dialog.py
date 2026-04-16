"""AI 工具管理对话框 — 新建/编辑 AIPrompt / AISkill / AIAgent"""
from __future__ import annotations

from typing import Literal, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon as FIF,
    InfoBar, InfoBarPosition,
    PlainTextEdit, PrimaryPushButton, PushButton,
    SubtitleLabel, LineEdit,
)

from core.project_manager import project_manager

_TOOL_TYPES = ["prompt", "skill", "agent"]
_TOOL_LABELS = ["Prompt（提示词）", "Skill（代码技能）", "Agent（自定义代理）"]


class AIToolDialog(QDialog):
    """新建或编辑 AI 工具（prompt / skill / agent）。

    用法：
        dlg = AIToolDialog(parent, tool_type="skill", tool_id=existing_id)
        if dlg.exec() == QDialog.Accepted:
            # 已保存
    """

    def __init__(
        self,
        parent=None,
        tool_type: Literal["prompt", "skill", "agent"] = "prompt",
        tool_id: Optional[str] = None,
    ):
        super().__init__(parent)
        self._tool_type = tool_type
        self._tool_id = tool_id       # None = 新建
        self._is_edit = tool_id is not None
        self.setWindowTitle("编辑 AI 工具" if self._is_edit else "新建 AI 工具")
        self.setMinimumSize(640, 500)
        self._setup_ui()
        if self._is_edit:
            self._load_existing()

    # ─────────────────────────────────────────────────────────────
    # UI 构建
    # ─────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 12)
        root.setSpacing(10)

        # 类型选择（新建时可改；编辑时锁定）
        type_row = QHBoxLayout()
        type_row.addWidget(BodyLabel("工具类型:"))
        self._type_combo = ComboBox(self)
        self._type_combo.addItems(_TOOL_LABELS)
        if self._tool_type in _TOOL_TYPES:
            self._type_combo.setCurrentIndex(_TOOL_TYPES.index(self._tool_type))
        self._type_combo.setEnabled(not self._is_edit)
        type_row.addWidget(self._type_combo, 1)
        root.addLayout(type_row)

        # 名称
        name_row = QHBoxLayout()
        name_row.addWidget(BodyLabel("名称:"))
        self._name_edit = LineEdit(self)
        self._name_edit.setPlaceholderText("工具名称（必填）")
        name_row.addWidget(self._name_edit, 1)
        root.addLayout(name_row)

        # 描述
        desc_row = QHBoxLayout()
        desc_row.addWidget(BodyLabel("描述:"))
        self._desc_edit = LineEdit(self)
        self._desc_edit.setPlaceholderText("简短描述（可选）")
        desc_row.addWidget(self._desc_edit, 1)
        root.addLayout(desc_row)

        # 内容编辑区
        root.addWidget(SubtitleLabel("内容"))
        self._content_edit = PlainTextEdit(self)
        self._content_edit.setPlaceholderText(self._content_hint())
        root.addWidget(self._content_edit, 1)

        # 测试运行区（仅 skill）
        self._test_widget = QWidget(self)
        test_vl = QVBoxLayout(self._test_widget)
        test_vl.setContentsMargins(0, 0, 0, 0)
        test_vl.setSpacing(4)
        test_row = QHBoxLayout()
        test_run_btn = PushButton(FIF.PLAY, "测试运行", self._test_widget)
        test_run_btn.clicked.connect(self._run_skill_test)
        test_row.addWidget(test_run_btn)
        test_row.addStretch()
        test_vl.addLayout(test_row)
        self._test_output = PlainTextEdit(self._test_widget)
        self._test_output.setReadOnly(True)
        self._test_output.setMaximumHeight(120)
        self._test_output.setPlaceholderText("执行输出将显示在此处…")
        test_vl.addWidget(self._test_output)
        root.addWidget(self._test_widget)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = PrimaryPushButton(FIF.SAVE, "保存", self)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        # 初始化类型相关 UI
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed(self._type_combo.currentIndex())

    def _content_hint(self) -> str:
        t = _TOOL_TYPES[self._type_combo.currentIndex() if hasattr(self, "_type_combo") else 0]
        hints = {
            "prompt": "在此输入提示词模板…\n可使用 {series_name}、{equation} 等占位符",
            "skill": (
                "# Python 代码片段，可访问：project_manager, np, fit_curve 等\n"
                "# 将结果赋值给 result 变量\n"
                "# 示例：\n"
                "# p = project_manager.current_project\n"
                "# result = len(p.data_files) if p else 0\n"
            ),
            "agent": "在此描述代理的行为规则和专属指令…",
        }
        return hints.get(t, "")

    def _on_type_changed(self, idx: int):
        t = _TOOL_TYPES[idx]
        self._test_widget.setVisible(t == "skill")
        self._content_edit.setPlaceholderText(self._content_hint())

    # ─────────────────────────────────────────────────────────────
    # 数据加载
    # ─────────────────────────────────────────────────────────────

    def _load_existing(self):
        p = project_manager.current_project
        if p is None or self._tool_id is None:
            return
        if self._tool_type == "prompt":
            obj = next((x for x in p.ai_prompts if x.id == self._tool_id), None)
        elif self._tool_type == "skill":
            obj = next((x for x in p.ai_skills if x.id == self._tool_id), None)
        elif self._tool_type == "agent":
            obj = next((x for x in p.ai_agents if x.id == self._tool_id), None)
        else:
            obj = None
        if obj:
            self._name_edit.setText(obj.name)
            self._desc_edit.setText(getattr(obj, "description", ""))
            self._content_edit.setPlainText(obj.content)

    # ─────────────────────────────────────────────────────────────
    # 保存
    # ─────────────────────────────────────────────────────────────

    def _on_save(self):
        name = self._name_edit.text().strip()
        if not name:
            InfoBar.warning("提示", "名称不能为空", parent=self,
                            position=InfoBarPosition.TOP, duration=2000)
            return
        content = self._content_edit.toPlainText()
        desc = self._desc_edit.text().strip()
        t = _TOOL_TYPES[self._type_combo.currentIndex()]

        if self._is_edit:
            self._do_update(t, name, content, desc)
        else:
            self._do_create(t, name, content, desc)

    def _do_create(self, t, name, content, desc):
        if t == "prompt":
            obj = project_manager.add_ai_prompt(name, content, desc)
        elif t == "skill":
            obj = project_manager.add_ai_skill(name, content, desc)
        else:
            obj = project_manager.add_ai_agent(name, content, desc)
        if obj is None:
            InfoBar.error("失败", "保存失败", parent=self, position=InfoBarPosition.TOP)
            return
        self.accept()

    def _do_update(self, t, name, content, desc):
        p = project_manager.current_project
        if p is None or self._tool_id is None:
            return
        if t == "prompt":
            objs = p.ai_prompts
        elif t == "skill":
            objs = p.ai_skills
        else:
            objs = p.ai_agents
        obj = next((x for x in objs if x.id == self._tool_id), None)
        if obj is None:
            InfoBar.error("失败", "找不到原始工具", parent=self, position=InfoBarPosition.TOP)
            return
        obj.name = name
        obj.content = content
        if hasattr(obj, "description"):
            obj.description = desc
        p.is_modified = True
        self.accept()

    # ─────────────────────────────────────────────────────────────
    # Skill 测试运行
    # ─────────────────────────────────────────────────────────────

    def _run_skill_test(self):
        code = self._content_edit.toPlainText()
        if not code.strip():
            self._test_output.setPlainText("（代码为空）")
            return
        try:
            from ai.skill_runner import skill_runner
            r = skill_runner.run(code)
            lines = []
            if r.stdout:
                lines.append("=== stdout ===")
                lines.append(r.stdout.rstrip())
            if r.success:
                lines.append(f"result = {r.output!r}")
            else:
                lines.append("=== error ===")
                lines.append(r.error)
            self._test_output.setPlainText("\n".join(lines))
        except Exception as e:
            self._test_output.setPlainText(f"运行器错误: {e}")
