"""
ALineAgent — 自然语言 → 命令执行 → 回复 的主循环

使用 OpenAI function calling 模式，每轮循环：
  1. 获取项目摘要作为系统上下文
  2. 调用 AI（携带 tools schema）
  3. AI 返回 tool_calls → 执行命令 → 结果追加到 messages
  4. 重复直到 AI 不再调用工具
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Optional

from core.ai_client import AIClient
from ai.command_layer import CommandDispatcher


@dataclass
class AgentEvent:
    type: Literal["thinking", "tool_call", "tool_result", "message", "error"]
    content: Any


class ALineAgent:
    """ALine AI 助手主循环。"""

    MAX_ROUNDS = 10  # 防止无限循环

    def __init__(
        self,
        client: Optional[AIClient] = None,
        dispatcher: Optional[CommandDispatcher] = None,
    ):
        self._client = client or AIClient()
        self._dispatcher = dispatcher or CommandDispatcher()

    async def run(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """流式执行，生成 AgentEvent 序列。"""
        # 1. 构建系统提示（含项目摘要）
        system_prompt = self._build_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ]
        tools = self._dispatcher.get_tools_schema()

        yield AgentEvent(type="thinking", content="正在分析请求…")

        for _round in range(self.MAX_ROUNDS):
            # 部分 Ollama 模型不支持 function calling，带 tools 会返回 400
            active_tools = tools if _round == 0 else None
            resp = await self._client.chat(messages, tools=active_tools)

            if resp.error:
                if active_tools and ("400" in resp.error or "Bad Request" in resp.error):
                    # 回退：不带 tools 重试
                    resp = await self._client.chat(messages, tools=None)
                if resp.error:
                    yield AgentEvent(type="error", content=resp.error)
                    return

            if not resp.tool_calls:
                # AI 直接回复，无工具调用
                yield AgentEvent(type="message", content=resp.content)
                return

            # 2. 有 tool_calls → 执行每个命令
            # 先把 assistant 消息追加到 messages
            messages.append({
                "role": "assistant",
                "content": resp.content or "",
                "tool_calls": resp.tool_calls,
            })

            for tc in resp.tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    func_args = {}

                yield AgentEvent(type="tool_call", content={
                    "name": func_name,
                    "args": func_args,
                })

                result = self._dispatcher.execute({
                    "action": func_name,
                    "params": func_args,
                })

                yield AgentEvent(type="tool_result", content={
                    "name": func_name,
                    "result": result.to_dict(),
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result.to_dict(), ensure_ascii=False),
                })

        yield AgentEvent(type="error", content="达到最大轮次限制，请重新提问")

    def _build_system_prompt(self) -> str:
        from ai.command_registry import cmd_get_project_summary
        result = cmd_get_project_summary({})
        project_info = json.dumps(result.data or {}, ensure_ascii=False, indent=2)
        return (
            "你是 ALine 科研数据管理平台的 AI 助手。\n"
            "你能够帮助用户管理数据、运行分析、创建可视化和处理数据。\n"
            "当前项目信息：\n"
            f"{project_info}\n\n"
            "你可以使用以下工具来操作项目数据。"
            "在调用工具之前，先向用户解释你打算做什么。"
        )
