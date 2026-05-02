"""
AI 命令层 — COMMANDS 注册表 + CommandDispatcher

每个 command handler 接收 params: dict，返回 CommandResult。
CommandDispatcher.get_tools_schema() 返回 OpenAI function calling 格式。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from ai import command_registry
from ai.command_series_lookup import resolve_series
from core.global_assets import global_assets
from ai.skill_runner import skill_runner
from core.ai_client import AIClient
from core.project_manager import project_manager


# ─────────────────────────────────────────────────────────────
# Command types — 从 command_registry 导入唯一源
# ─────────────────────────────────────────────────────────────

from ai.command_registry import COMMANDS, CommandResult, CommandDef

__all__ = [
    "COMMANDS",
    "CommandResult",
    "CommandDef",
    "CommandDispatcher",
]


def __getattr__(name: str) -> Any:
    """兼容旧导入路径，转发 cmd_* 到 command_registry。"""
    if name.startswith("cmd_") and hasattr(command_registry, name):
        return getattr(command_registry, name)
    if name == "COMMANDS":
        return command_registry.COMMANDS
    raise AttributeError(name)

# ─────────────────────────────────────────────────────────────
# CommandDispatcher
# ─────────────────────────────────────────────────────────────
class CommandDispatcher:
    """执行已注册命令，并提供 OpenAI function calling 格式的 tools schema。"""

    def __init__(self, runtime_context: Optional[dict] = None):
        self._runtime_context = dict(runtime_context or {})

    def set_runtime_context(self, runtime_context: Optional[dict]) -> None:
        self._runtime_context = dict(runtime_context or {})

    @staticmethod
    def _global_tool_name(prefix: str, item_id: str) -> str:
        return f"{prefix}_{item_id.replace('-', '_')}"

    def _builtin_catalog(self) -> List[dict]:
        catalog: List[dict] = []
        for name, cmd in command_registry.COMMANDS.items():
            props = {}
            required = []
            for param_name, param_info in cmd.params_schema.items():
                props[param_name] = {
                    "type": param_info.get("type", "string"),
                    "description": param_info.get("description", ""),
                }
                if "default" not in param_info:
                    required.append(param_name)
            catalog.append({
                "name": name,
                "label": f"内置 · {name}",
                "description": cmd.desc,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
                "kind": "builtin",
                "item_id": None,
            })
        return catalog

    def _dynamic_ai_catalog(self) -> List[dict]:
        catalog: List[dict] = []
        for prompt in global_assets.list_ai_prompts():
            catalog.append({
                "name": self._global_tool_name("global_prompt", prompt.id),
                "label": f"Prompt · {prompt.name}",
                "description": prompt.description or f"读取全局 Prompt「{prompt.name}」的内容。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                "kind": "prompt",
                "item_id": prompt.id,
            })
        for skill in global_assets.list_ai_skills():
            catalog.append({
                "name": self._global_tool_name("global_skill", skill.id),
                "label": f"Skill · {skill.name}",
                "description": skill.description or f"在 ALine 沙箱中执行全局 Skill「{skill.name}」。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "给 Skill 的任务说明，可选。"},
                        "payload": {"type": "object", "description": "传给 Skill 的结构化输入，可选。"},
                    },
                    "required": [],
                },
                "kind": "skill",
                "item_id": skill.id,
            })
        for agent in global_assets.list_ai_agents():
            catalog.append({
                "name": self._global_tool_name("global_agent", agent.id),
                "label": f"Agent · {agent.name}",
                "description": agent.description or f"调用全局 Agent「{agent.name}」处理子任务。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "交给该 Agent 的子任务说明。"},
                    },
                    "required": ["task"],
                },
                "kind": "agent",
                "item_id": agent.id,
            })
        return catalog

    def list_tool_catalog(self) -> List[dict]:
        return self._builtin_catalog() + self._dynamic_ai_catalog()

    def _dynamic_tool_entry(self, action: str) -> Optional[dict]:
        return next((item for item in self._dynamic_ai_catalog() if item["name"] == action), None)

    def _execute_dynamic_tool(self, entry: dict, params: dict) -> CommandResult:
        kind = entry["kind"]
        item_id = entry["item_id"]
        if kind == "prompt":
            prompt = global_assets.get_ai_prompt(item_id)
            if prompt is None:
                return command_registry.CommandResult(success=False, error="找不到指定 Prompt")
            return command_registry.CommandResult(data={
                "type": "prompt",
                "name": prompt.name,
                "description": prompt.description,
                "content": prompt.content,
            })

        if kind == "skill":
            skill = global_assets.get_ai_skill(item_id)
            if skill is None:
                return command_registry.CommandResult(success=False, error="找不到指定 Skill")
            result = skill_runner.run(skill.code, extra_vars={
                "task": params.get("task", ""),
                "payload": params.get("payload"),
                "context": dict(self._runtime_context),
            })
            return command_registry.CommandResult(data={
                "type": "skill",
                "name": skill.name,
                **result.to_dict(),
            })

        if kind == "agent":
            agent = global_assets.get_ai_agent(item_id)
            if agent is None:
                return command_registry.CommandResult(success=False, error="找不到指定 Agent")
            task = str(params.get("task") or "").strip()
            if not task:
                return command_registry.CommandResult(success=False, error="缺少 task 参数")
            context_text = str(self._runtime_context.get("context_text") or "暂无上下文")
            try:
                response = asyncio.run(AIClient().chat([
                    {"role": "system", "content": agent.system_prompt},
                    {"role": "user", "content": f"ALine 当前上下文:\n{context_text}\n\n子任务:\n{task}"},
                ]))
            except Exception as exc:
                return command_registry.CommandResult(success=False, error=str(exc))
            if response.error:
                return command_registry.CommandResult(success=False, error=response.error)
            return command_registry.CommandResult(data={
                "type": "agent",
                "name": agent.name,
                "content": response.content or "",
            })

        return command_registry.CommandResult(success=False, error=f"未知 AI 工具类型: {kind}")

    def execute(self, command: dict) -> command_registry.CommandResult:
        """command = {"action": "cmd_name", "params": {...}}"""
        action = command.get("action", "")
        params = command.get("params", {})
        cmd_def = command_registry.COMMANDS.get(action)
        if cmd_def is not None:
            try:
                return cmd_def.handler(params)
            except Exception as e:
                return command_registry.CommandResult(success=False, error=str(e))

        dynamic_tool = self._dynamic_tool_entry(action)
        if dynamic_tool is not None:
            return self._execute_dynamic_tool(dynamic_tool, params)

        return command_registry.CommandResult(success=False, error=f"未知命令: {action}")

    def get_tools_schema(self) -> List[dict]:
        """返回 OpenAI function calling 格式的 tools 列表。"""
        tools = []
        for entry in self.list_tool_catalog():
            tools.append({
                "type": "function",
                "function": {
                    "name": entry["name"],
                    "description": entry["description"],
                    "parameters": entry["parameters"],
                },
            })
        return tools
