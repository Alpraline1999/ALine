from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QFrame,
    QApplication,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    ScrollArea,
    SearchLineEdit,
    SubtitleLabel,
    ToolButton,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    SmoothScrollArea,
    ToolTipFilter,
    ToolTipPosition,
    PlainTextEdit,
)

from core.ai.context import AIAssistantContext
from core.ai.agent_runner import AgentBridge
from core.ai.context_collector import collect_context
from ui.theme import (
    secondary_color,
    placeholder_color,
    accent_color,
    make_hsep,
    install_fluent_tooltip,
)


_CONVERSATIONS_DIR = Path.home() / ".config" / "aline" / "conversations"


class MessageBubble(QFrame):
    """单条对话气泡，支持文本选择和扩展代码保存。"""

    save_requested = Signal(str)  # 发送 (code_text) 用于保存扩展

    def __init__(self, role: str, content: str, parent=None):
        super().__init__(parent)
        self._role = role
        self._content = content

        self.setObjectName("message_bubble")
        self.setProperty("role", role)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        role_label = BodyLabel("你" if role == "user" else "AI", self)
        role_label.setStyleSheet(f"color: {accent_color()}; font-weight: bold; font-size: 12px;")
        layout.addWidget(role_label)

        # BodyLabel 开启文本选择，保持轻量和一致样式
        content_label = BodyLabel(content, self)
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_label.setStyleSheet(
            "font-size: 13px; line-height: 1.5;"
            if role == "user"
            else "font-size: 13px; line-height: 1.5; color: #333;"
        )
        layout.addWidget(content_label)

        # 如果 AI 回复包含代码块，添加"保存为扩展"按钮
        self._save_btn = None
        if role == "assistant":
            code = self._extract_code_block(content)
            if code:
                self._save_btn = PushButton("保存为扩展", self)
                self._save_btn.setFixedWidth(120)
                self._save_btn.clicked.connect(lambda: self.save_requested.emit(code))
                layout.addWidget(self._save_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.setStyleSheet(
            """
            MessageBubble[role="user"] {
                background: #E8F0FE;
                border-radius: 8px;
                margin: 4px 0px;
            }
            MessageBubble[role="assistant"] {
                background: #F5F5F5;
                border-radius: 8px;
                margin: 4px 0px;
            }
            """
        )

    @staticmethod
    def _extract_code_block(text: str) -> str:
        """从 AI 回复中提取第一个 python 代码块。"""
        import re
        match = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)
        return match.group(1).strip() if match else ""


class Conversation:
    """单个对话的数据模型。"""

    def __init__(self, conv_id: str | None = None, title: str = "新对话"):
        self.id = conv_id or f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.title = title
        self.page: str = ""
        self.messages: List[Dict[str, str]] = []
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
        self.updated_at = datetime.now().isoformat()
        # Auto-title from first user message
        if role == "user" and self.title == "新对话":
            self.title = content[:40] + ("..." if len(content) > 40 else "")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "page": self.page,
            "messages": self.messages,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        conv = cls(conv_id=data.get("id"), title=data.get("title", "对话"))
        conv.page = data.get("page", "")
        conv.messages = data.get("messages", [])
        conv.created_at = data.get("created_at", conv.created_at)
        conv.updated_at = data.get("updated_at", conv.updated_at)
        return conv


class AIAssistantPanel(QWidget):
    """AI 助手面板：对话界面，支持多对话管理。

    与右侧面板中的 ExtensionConfigPanel 通过 SegmentedStackWidget 切换。
    """

    def __init__(self, page_name: str = "", parent=None):
        super().__init__(parent)
        self._page_name = page_name
        self._conversations: List[Conversation] = []
        self._current_conv_index: int = -1
        self._context = AIAssistantContext()

        # 确保对话目录存在
        _CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

        # AI Agent 桥接器
        self._agent_bridge = AgentBridge(self)
        self._agent_bridge.thinking.connect(self._on_agent_thinking)
        self._agent_bridge.message.connect(self._on_agent_message)
        self._agent_bridge.error.connect(self._on_agent_error)
        self._agent_bridge.finished.connect(self._on_agent_finished)

        self._setup_ui()
        self._load_conversations()
        self._new_conversation()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── 标题栏 ──
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        title_label = SubtitleLabel("AI 助手", header)
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        self._new_btn = ToolButton(FIF.ADD, header)
        self._new_btn.setToolTip("新建对话")
        self._new_btn.clicked.connect(self._new_conversation)
        header_layout.addWidget(self._new_btn)

        self._history_btn = ToolButton(FIF.HISTORY, header)
        self._history_btn.setToolTip("对话历史")
        self._history_btn.clicked.connect(self._show_history_menu)
        header_layout.addWidget(self._history_btn)

        layout.addWidget(header)
        layout.addWidget(make_hsep())

        # ── 对话导航 ──
        nav = QWidget(self)
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(12, 4, 12, 4)

        self._prev_btn = PushButton("< 上一个", nav)
        self._prev_btn.setFixedWidth(80)
        self._prev_btn.setToolTip("上一个对话")
        self._prev_btn.clicked.connect(self._prev_conversation)
        nav_layout.addWidget(self._prev_btn)

        self._conv_label = CaptionLabel("对话 0/0", nav)
        self._conv_label.setStyleSheet(f"color: {secondary_color()};")
        nav_layout.addWidget(self._conv_label)

        self._next_btn = PushButton("下一个 >", nav)
        self._next_btn.setFixedWidth(80)
        self._next_btn.setToolTip("下一个对话")
        self._next_btn.clicked.connect(self._next_conversation)
        nav_layout.addWidget(self._next_btn)

        nav_layout.addStretch()

        self._delete_btn = ToolButton(FIF.DELETE, nav)
        self._delete_btn.setToolTip("删除当前对话")
        self._delete_btn.clicked.connect(self._delete_conversation)
        nav_layout.addWidget(self._delete_btn)

        layout.addWidget(nav)

        # ── 上下文摘要 ──
        self._context_label = CaptionLabel("", self)
        self._context_label.setContentsMargins(12, 4, 12, 4)
        self._context_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        self._context_label.setWordWrap(True)
        layout.addWidget(self._context_label)

        # ── 对话消息区域 ──
        self._scroll = SmoothScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._messages_widget = QWidget(self._scroll)
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setContentsMargins(12, 8, 12, 8)
        self._messages_layout.setSpacing(8)
        self._messages_layout.addStretch()
        self._scroll.setWidget(self._messages_widget)

        layout.addWidget(self._scroll, 1)

        # ── 输入区 ──
        input_widget = QWidget(self)
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(12, 8, 12, 8)

        self._input_edit = SearchLineEdit(input_widget)
        self._input_edit.setPlaceholderText("输入 /help 查看命令，或直接提问...")
        self._input_edit.setFixedHeight(36)
        self._input_edit.setClearButtonEnabled(True)
        input_layout.addWidget(self._input_edit, 1)

        self._send_btn = PrimaryPushButton("发送", input_widget)
        self._send_btn.setFixedWidth(80)
        self._send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self._send_btn)

        layout.addWidget(input_widget)

    # ── 对话管理 ──

    def _new_conversation(self) -> None:
        conv = Conversation()
        conv.page = self._page_name
        self._conversations.append(conv)
        self._current_conv_index = len(self._conversations) - 1
        self._refresh_ui()
        self._save_conversations()

    def _prev_conversation(self) -> None:
        if self._current_conv_index > 0:
            self._current_conv_index -= 1
            self._refresh_ui()

    def _next_conversation(self) -> None:
        if self._current_conv_index < len(self._conversations) - 1:
            self._current_conv_index += 1
            self._refresh_ui()

    def _delete_conversation(self) -> None:
        if not self._conversations or self._current_conv_index < 0:
            return
        conv = self._conversations[self._current_conv_index]
        self._conversations.pop(self._current_conv_index)
        self._delete_conversation_file(conv.id)
        if not self._conversations:
            self._new_conversation()
        elif self._current_conv_index >= len(self._conversations):
            self._current_conv_index = len(self._conversations) - 1
        self._refresh_ui()

    def _show_history_menu(self) -> None:
        """显示对话历史列表，支持切换活动/归档、删除。"""
        if not self._conversations:
            InfoBar.info("无历史对话", "暂无保存的对话记录。", parent=self, position=InfoBarPosition.TOP)
            return
        from qfluentwidgets import MessageBoxBase, ListWidget, PushButton
        from PySide6.QtWidgets import QHBoxLayout

        active_convs = [c for c in self._conversations if not getattr(c, "_archived", False)]
        archived_convs = [c for c in self._conversations if getattr(c, "_archived", False)]

        class _HistoryDialog(MessageBoxBase):
            def __init__(self, active, archived, parent=None):
                super().__init__(parent)
                self.selected_id = None
                self._delete_id = None
                self._active = list(active)
                self._archived = list(archived)
                self._show_archived = False
                self.viewLayout.addWidget(SubtitleLabel("对话历史", self.widget))

                self._tab_btn = PushButton("活动对话", self.widget)
                self._tab_btn.clicked.connect(self._toggle_tab)
                self.viewLayout.addWidget(self._tab_btn)

                self._list = ListWidget(self.widget)
                self._refresh_list()
                self._list.itemDoubleClicked.connect(lambda item: self._pick())
                self.viewLayout.addWidget(self._list, 1)

                btn_row = QHBoxLayout()
                self._action_btn = PushButton("归档", self.widget)
                self._action_btn.clicked.connect(self._toggle_archive)
                btn_row.addWidget(self._action_btn)
                self._del_btn = PushButton("删除", self.widget)
                self._del_btn.clicked.connect(self._do_delete)
                btn_row.addWidget(self._del_btn)
                self.viewLayout.addLayout(btn_row)
                self.yeshidden = False

            def _toggle_tab(self):
                self._show_archived = not self._show_archived
                self._tab_btn.setText("归档对话" if not self._show_archived else "活动对话")
                self._action_btn.setText("取消归档" if self._show_archived else "归档")
                self._refresh_list()

            def _current_convs(self):
                return self._archived if self._show_archived else self._active

            def _refresh_list(self):
                self._list.clear()
                for c in self._current_convs():
                    self._list.addItem(f"{c.title}  ({c.id})")
                if self._list.count():
                    self._list.setCurrentRow(0)

            def _pick(self):
                convs = self._current_convs()
                row = self._list.currentRow()
                if 0 <= row < len(convs):
                    self.selected_id = convs[row].id
                self.accept()

            def _toggle_archive(self):
                convs = self._current_convs()
                row = self._list.currentRow()
                if row < 0 or row >= len(convs):
                    return
                convs[row]._archived = not getattr(convs[row], "_archived", False)
                convs.pop(row)
                self._refresh_list()

            def _do_delete(self):
                convs = self._current_convs()
                row = self._list.currentRow()
                if row < 0 or row >= len(convs):
                    return
                self._delete_id = convs[row].id
                convs.pop(row)
                self._refresh_list()

        dialog = _HistoryDialog(active_convs, archived_convs, self)
        if dialog.exec():
            if dialog._delete_id:
                self._delete_conversation_file(dialog._delete_id)
                self._conversations = [c for c in self._conversations if c.id != dialog._delete_id]
            if dialog.selected_id:
                for i, c in enumerate(self._conversations):
                    if c.id == dialog.selected_id:
                        self._current_conv_index = i
                        self._refresh_ui()
                        break

    # ── 消息 ──

    def _send_message(self) -> None:
        text = self._input_edit.text().strip()
        if not text:
            return
        self._input_edit.clear()

        conv = self._current_conversation()
        if conv is None:
            return

        conv.add_message("user", text)
        self._append_bubble("user", text)
        self._save_conversations()

        # 检测是否为命令
        from ui.widgets.ai_command_handler import detect_command, execute_command
        cmd = detect_command(text)
        if cmd:
            cmd_name, cmd_label, cmd_args = cmd
            system_extra, extra_msgs = execute_command(cmd_name, cmd_args)
            if cmd_name == "help":
                # /help 直接显示，无需调用 AI
                self._hide_thinking()
                conv.add_message("assistant", system_extra)
                self._append_bubble("assistant", system_extra)
                self._save_conversations()
                return
            self._show_thinking()
            self._agent_bridge.start(cmd_args if cmd_args else text, extra_system_prompt=system_extra)
            return

        self.refresh_context()
        self._show_thinking()
        self._agent_bridge.start(text)

    def _on_agent_thinking(self, content: str) -> None:
        """Agent 思考过程中更新 thinking 提示。"""
        if hasattr(self, "_thinking_label") and self._thinking_label is not None:
            self._thinking_label.setText(f"AI 思考中: {content[:60]}...")

    def _on_agent_message(self, content: str) -> None:
        """收到 AI 的最终回复消息。"""
        self._hide_thinking()
        conv = self._current_conversation()
        if conv is None:
            return
        conv.add_message("assistant", content)
        self._append_bubble("assistant", content)
        self._save_conversations()

    def _on_agent_error(self, error: str) -> None:
        """Agent 出错。"""
        self._hide_thinking()
        conv = self._current_conversation()
        if conv is None:
            return
        msg = f"（错误: {error}）"
        conv.add_message("assistant", msg)
        self._append_bubble("assistant", msg)

    def _on_agent_finished(self) -> None:
        """Agent 完成。"""
        self._hide_thinking()

    def _show_thinking(self) -> None:
        self._thinking_label = CaptionLabel("AI 正在思考...", self._messages_widget)
        self._thinking_label.setStyleSheet(f"color: {placeholder_color()}; padding: 8px 12px;")
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, self._thinking_label)
        self._scroll.verticalScrollBar().setValue(self._scroll.verticalScrollBar().maximum())

    def _hide_thinking(self) -> None:
        if hasattr(self, "_thinking_label") and self._thinking_label is not None:
            self._thinking_label.deleteLater()
            self._thinking_label = None

    def _append_bubble(self, role: str, content: str) -> None:
        bubble = MessageBubble(role, content, self._messages_widget)
        bubble.save_requested.connect(self._on_save_extension)
        self._messages_layout.insertWidget(self._messages_layout.count() - 1, bubble)
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _on_save_extension(self, code: str) -> None:
        """保存 AI 生成的扩展代码到外部扩展目录。"""
        from core.ai.extension_writer import parse_extension_code, save_extension

        ext_type, category, err = parse_extension_code(code)
        if not ext_type or not category:
            InfoBar.error("保存失败", err or "无法解析扩展代码", parent=self, position=InfoBarPosition.TOP)
            return

        ok, msg = save_extension(code, category, ext_type)
        if ok:
            InfoBar.success("已保存", f"扩展已保存到 {msg}", parent=self, position=InfoBarPosition.TOP)
            # 重载扩展
            try:
                from core.extension_api import reload_configured_extensions
                reload_configured_extensions()
                InfoBar.success("已重载", "扩展已重新加载", parent=self, position=InfoBarPosition.TOP)
            except Exception as e:
                InfoBar.warning("扩展已保存", f"重载失败，请手动重载: {e}", parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.error("保存失败", msg, parent=self, position=InfoBarPosition.TOP)

    # ── 上下文 ──

    def refresh_context(self) -> None:
        """当页面切换或用户切换到 AI tab 时刷新上下文。"""
        summary = f"📌 当前: {self._page_name or '未知'}"
        self._context_label.setText(summary)

    # ── 持久化 ──

    def _conversation_path(self, conv_id: str) -> Path:
        return _CONVERSATIONS_DIR / f"{conv_id}.json"

    def _save_conversations(self) -> None:
        for conv in self._conversations:
            path = self._conversation_path(conv.id)
            path.write_text(json.dumps(conv.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_conversations(self) -> None:
        if not _CONVERSATIONS_DIR.exists():
            return
        for path in sorted(_CONVERSATIONS_DIR.glob("conv_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                conv = Conversation.from_dict(data)
                self._conversations.append(conv)
            except Exception:
                continue

    def _delete_conversation_file(self, conv_id: str) -> None:
        path = self._conversation_path(conv_id)
        if path.exists():
            path.unlink()

    # ── 内部辅助 ──

    def _current_conversation(self) -> Conversation | None:
        if 0 <= self._current_conv_index < len(self._conversations):
            return self._conversations[self._current_conv_index]
        return None

    def _refresh_ui(self) -> None:
        # 清除消息
        while self._messages_layout.count() > 1:
            item = self._messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        conv = self._current_conversation()
        if conv:
            self._conv_label.setText(f"对话 {self._current_conv_index + 1}/{len(self._conversations)}")
            for msg in conv.messages:
                self._append_bubble(msg["role"], msg["content"])
        else:
            self._conv_label.setText("对话 0/0")

        self._prev_btn.setEnabled(self._current_conv_index > 0)
        self._next_btn.setEnabled(self._current_conv_index < len(self._conversations) - 1)
        self.refresh_context()
