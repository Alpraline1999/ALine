from __future__ import annotations

import asyncio
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CardWidget, ComboBox, PlainTextEdit, PrimaryPushButton, PushButton


class AIAssistantPanel(QWidget):
    """右侧 AI 助手栏，展示页面/节点上下文并发送对话请求。"""

    response_ready = Signal(str)
    request_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)
        self._current_page = "未选择页面"
        self._current_node = "未选择节点"
        self._current_context = "暂无上下文"
        self._tool_entries: list[dict] = []
        self._tool_runner = None
        self._request_runner = None
        self._setup_ui()
        self.response_ready.connect(self._on_response_ready)
        self.request_state_changed.connect(self._set_busy)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = BodyLabel("AI 助手", card)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self._page_label = BodyLabel("当前页面: 未选择页面", card)
        self._page_label.setWordWrap(True)
        layout.addWidget(self._page_label)

        self._node_label = BodyLabel("当前节点: 未选择节点", card)
        self._node_label.setWordWrap(True)
        layout.addWidget(self._node_label)

        context_title = BodyLabel("上下文", card)
        context_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(context_title)

        self._context_view = PlainTextEdit(card)
        self._context_view.setReadOnly(True)
        self._context_view.setPlainText(self._current_context)
        layout.addWidget(self._context_view, 1)

        chat_title = BodyLabel("对话", card)
        chat_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(chat_title)

        self._conversation_view = PlainTextEdit(card)
        self._conversation_view.setReadOnly(True)
        layout.addWidget(self._conversation_view, 1)

        tool_row = QHBoxLayout()
        self._tool_combo = ComboBox(card)
        tool_row.addWidget(self._tool_combo, 1)
        self._run_tool_btn = PushButton("执行工具", card)
        self._run_tool_btn.clicked.connect(self._run_selected_tool)
        tool_row.addWidget(self._run_tool_btn)
        layout.addLayout(tool_row)

        self._input_edit = PlainTextEdit(card)
        self._input_edit.setPlaceholderText("输入问题，助手会自动带上当前页面和节点上下文…")
        self._input_edit.setFixedHeight(90)
        layout.addWidget(self._input_edit)

        btn_row = QHBoxLayout()
        self._send_btn = PrimaryPushButton("发送", card)
        self._send_btn.clicked.connect(self._send_prompt)
        btn_row.addWidget(self._send_btn)
        clear_btn = PushButton("清空对话", card)
        clear_btn.clicked.connect(self._conversation_view.clear)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        root.addWidget(card)

    def set_current_page(self, page_name: str) -> None:
        self._current_page = page_name or "未选择页面"
        self._page_label.setText(f"当前页面: {self._current_page}")

    def set_selected_node(self, label: str) -> None:
        self._current_node = label or "未选择节点"
        self._node_label.setText(f"当前节点: {self._current_node}")

    def set_context_text(self, context_text: str) -> None:
        self._current_context = context_text or "暂无上下文"
        self._context_view.setPlainText(self._current_context)

    def set_request_runner(self, runner) -> None:
        self._request_runner = runner

    def set_tool_runner(self, runner, tool_names: list[dict] | list[str]) -> None:
        self._tool_runner = runner
        self._tool_entries = []
        self._tool_combo.clear()
        for item in tool_names:
            if isinstance(item, dict):
                entry = dict(item)
            else:
                entry = {"name": str(item), "label": str(item)}
            self._tool_entries.append(entry)
            self._tool_combo.addItem(entry.get("label", entry["name"]))

    def _compose_system_prompt(self) -> str:
        return (
            "你是 ALine 桌面应用内的 AI 助手。"
            "请优先基于当前页面、当前节点和页面工作集回答。"
            f"\n\n当前页面: {self._current_page}"
            f"\n当前节点: {self._current_node}"
            f"\n\n页面上下文:\n{self._current_context}"
        )

    def _send_prompt(self) -> None:
        prompt = self._input_edit.toPlainText().strip()
        if not prompt:
            return
        self._conversation_view.appendPlainText(f"用户:\n{prompt}\n")
        self._input_edit.clear()
        self.request_state_changed.emit(True)
        worker = threading.Thread(target=self._run_request, args=(prompt,), daemon=True)
        worker.start()

    def _run_selected_tool(self) -> None:
        if self._tool_runner is None:
            return
        idx = self._tool_combo.currentIndex()
        if idx < 0 or idx >= len(self._tool_entries):
            return
        tool_name = self._tool_entries[idx]["name"]
        result = self._tool_runner(tool_name)
        self._conversation_view.appendPlainText(f"工具 {tool_name}:\n{result}\n")

    def _run_request(self, prompt: str) -> None:
        try:
            if self._request_runner is not None:
                text = self._request_runner(prompt)
            else:
                from core.ai_client import AIClient

                messages = [
                    {"role": "system", "content": self._compose_system_prompt()},
                    {"role": "user", "content": prompt},
                ]
                response = asyncio.run(AIClient().chat(messages))
                if response.error:
                    text = f"请求失败: {response.error}"
                else:
                    text = response.content or "（模型未返回文本内容）"
        except Exception as exc:
            text = f"请求失败: {exc}"
        self.response_ready.emit(text)

    def _on_response_ready(self, text: str) -> None:
        self._conversation_view.appendPlainText(f"助手:\n{text}\n")
        self.request_state_changed.emit(False)

    def _set_busy(self, busy: bool) -> None:
        self._send_btn.setEnabled(not busy)