from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, Signal

from ai.agent import ALineAgent
from ai.command_layer import CommandDispatcher
from core.ai_client import AIClient


class AgentBridge(QObject):
    """AI Agent 的 Qt 信号桥接器。

    在后台线程中运行 ALineAgent，通过 Qt 信号将事件传递给 UI 线程。
    """

    thinking = Signal(str)
    message = Signal(str)
    tool_call = Signal(str, str)  # tool_name, args_json
    error = Signal(str)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._agent: Optional[ALineAgent] = None
        self._running = False

    def ensure_agent(self) -> ALineAgent:
        if self._agent is None:
            self._agent = ALineAgent()
        return self._agent

    def start(self, user_message: str, extra_system_prompt: str = "") -> None:
        """在后台线程中启动 agent。extra_system_prompt 追加到系统提示。"""
        if self._running:
            return
        self._running = True
        self._extra_system = extra_system_prompt
        thread = threading.Thread(target=self._run_agent, args=(user_message,), daemon=True)
        thread.start()

    def _run_agent(self, user_message: str) -> None:
        """在后台线程中同步运行 agent。"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            agent = self.ensure_agent()
            extra = getattr(self, "_extra_system", "")
            async_gen = agent.run(user_message, extra_system_prompt=extra)
            while True:
                try:
                    event = loop.run_until_complete(async_gen.__anext__())
                except StopAsyncIteration:
                    break

                if event.type == "thinking":
                    self.thinking.emit(str(event.content))
                elif event.type == "message":
                    self.message.emit(str(event.content))
                elif event.type == "tool_call":
                    name = ""
                    args = "{}"
                    if isinstance(event.content, dict):
                        name = event.content.get("name", "")
                        args = json.dumps(event.content.get("arguments", {}), ensure_ascii=False)
                    elif isinstance(event.content, str):
                        name = event.content
                    self.tool_call.emit(name, args)
                elif event.type == "error":
                    self.error.emit(str(event.content))
            loop.close()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self._running = False
            self.finished.emit()
