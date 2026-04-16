from __future__ import annotations

from typing import Any, Dict, List, Optional

from .client import AIClient
from .tool_executor import execute_tool


class AgentRuntime:
    """最小 AI 运行时：封装对话请求与工具执行。"""

    def __init__(self, client: Optional[AIClient] = None):
        self._client = client or AIClient()

    async def run_chat(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        response = await self._client.chat(messages)
        return response.model_dump()

    def run_tool(self, tool_name: str, context: Optional[Dict[str, Any]] = None) -> str:
        return execute_tool(tool_name, context)