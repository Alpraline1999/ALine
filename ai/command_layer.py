"""
AI 命令层 — COMMANDS 注册表 + CommandDispatcher

每个 command handler 接收 params: dict，返回 CommandResult。
CommandDispatcher.get_tools_schema() 返回 OpenAI function calling 格式。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ai import command_registry
from ai.command_series_lookup import resolve_series
from core.global_assets import global_assets
from ai.skill_runner import skill_runner
from core.ai_client import AIClient
from core.project_manager import project_manager


@dataclass
class CommandResult:
    success: bool = True
    data: Any = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        if not self.success:
            return {"success": False, "error": self.error}
        return {"success": True, "data": self.data}


@dataclass
class CommandDef:
    handler: Callable[[dict], CommandResult]
    desc: str
    params_schema: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# Command handlers & COMMANDS — 从 command_registry 导入唯一源
# ─────────────────────────────────────────────────────────────

from ai.command_registry import (
    cmd_get_project_summary,
    cmd_list_data_files,
    cmd_create_folder,
    cmd_apply_pipeline,
    cmd_save_pipeline,
    cmd_fit_curve,
    cmd_detect_peaks,
    cmd_compute_statistics,
    cmd_compute_correlation,
    cmd_list_saved_pipelines,
    cmd_import_data_file,
    cmd_export_series,
    cmd_apply_pipeline_persist,
    cmd_generate_report,
    cmd_list_image_works,
    cmd_list_report_templates,
    cmd_save_figure_template,
    cmd_manage_ai_tool,
    COMMANDS,
)

# ─────────────────────────────────────────────────────────────
# CommandDispatcher
# ─────────────────────────────────────────────────────────────# ─────────────────────────────────────────────────────────────

COMMANDS: Dict[str, CommandDef] = {
    "get_project_summary": CommandDef(
        handler=cmd_get_project_summary,
        desc="获取当前项目的数据摘要（数据文件数、图像数、分析数等）",
        params_schema={},
    ),
    "list_data_files": CommandDef(
        handler=cmd_list_data_files,
        desc="列出当前项目所有数据文件和系列",
        params_schema={},
    ),
    "create_folder": CommandDef(
        handler=cmd_create_folder,
        desc="在项目树的指定位置创建文件夹",
        params_schema={
            "name": {"type": "string", "description": "文件夹名称"},
            "parent_id": {"type": "string", "description": "父节点 ID（可选，为空时创建在根目录）"},
        },
    ),
    "apply_pipeline": CommandDef(
        handler=cmd_apply_pipeline,
        desc="对指定数据系列执行操作管道并返回前10个点的预览",
        params_schema={
            "series_id": {"type": "string", "description": "DataSeries 的 ID"},
            "ops": {"type": "array", "description": "操作列表，每项格式：{type, params}"},
        },
    ),
    "save_pipeline": CommandDef(
        handler=cmd_save_pipeline,
        desc="将一组操作保存为可复用的 Pipeline",
        params_schema={
            "name": {"type": "string", "description": "Pipeline 名称"},
            "ops": {"type": "array", "description": "操作列表"},
            "description": {"type": "string", "description": "描述（可选）"},
        },
    ),
    "list_saved_pipelines": CommandDef(
        handler=cmd_list_saved_pipelines,
        desc="列出当前项目所有已保存的 Pipeline",
        params_schema={},
    ),
    "fit_curve": CommandDef(
        handler=cmd_fit_curve,
        desc="对指定系列进行曲线拟合，返回拟合参数和 R²",
        params_schema={
            "series_id": {"type": "string", "description": "DataSeries 的 ID"},
            "model": {"type": "string", "description": "拟合模型：linear/power/exponential/gaussian/poly2/poly3"},
        },
    ),
    "detect_peaks": CommandDef(
        handler=cmd_detect_peaks,
        desc="检测指定系列的峰值",
        params_schema={
            "series_id": {"type": "string", "description": "DataSeries 的 ID"},
            "min_height": {"type": "number", "description": "最小峰高（可选）"},
            "min_distance": {"type": "integer", "description": "最小峰间距（采样点数）"},
            "min_distance_x": {"type": "number", "description": "最小峰间距（按 x 值）"},
            "prominence": {"type": "number", "description": "最小突出度（可选）"},
        },
    ),
    "compute_statistics": CommandDef(
        handler=cmd_compute_statistics,
        desc="计算指定系列的基础统计量（均值、标准差、四分位数等）",
        params_schema={
            "series_id": {"type": "string", "description": "DataSeries 的 ID"},
        },
    ),
    "compute_correlation": CommandDef(
        handler=cmd_compute_correlation,
        desc="计算两个系列之间的相关系数",
        params_schema={
            "series_id1": {"type": "string", "description": "第一个 DataSeries 的 ID"},
            "series_id2": {"type": "string", "description": "第二个 DataSeries 的 ID"},
            "method": {"type": "string", "description": "相关系数类型：pearson 或 spearman"},
        },
    ),
    "import_data_file": CommandDef(
        handler=cmd_import_data_file,
        desc="从磁盘导入数据文件（CSV/Excel/JSON/NumPy）到项目",
        params_schema={
            "file_path": {"type": "string", "description": "要导入的文件路径"},
            "parent_id": {"type": "string", "description": "挂载的父节点 ID（可选）", "default": None},
        },
    ),
    "export_series": CommandDef(
        handler=cmd_export_series,
        desc="将指定数据系列导出为 CSV 文件",
        params_schema={
            "series_id": {"type": "string", "description": "DataSeries 的 ID"},
            "output_path": {"type": "string", "description": "导出文件路径（含文件名）"},
        },
    ),
    "apply_pipeline_persist": CommandDef(
        handler=cmd_apply_pipeline_persist,
        desc="对系列执行已保存的 Pipeline，并将结果保存为新 DataSeries",
        params_schema={
            "series_id": {"type": "string", "description": "源 DataSeries 的 ID"},
            "pipeline_id": {"type": "string", "description": "已保存 Pipeline 的 ID"},
            "new_name": {"type": "string", "description": "新系列名称（可选）", "default": ""},
        },
    ),
    "generate_report": CommandDef(
        handler=cmd_generate_report,
        desc="使用报告模板渲染分析报告，返回 Markdown 字符串",
        params_schema={
            "analysis_id": {"type": "string", "description": "AnalysisResult 的 ID（可选）", "default": ""},
            "template_id": {"type": "string", "description": "ReportTemplate 的 ID（留空使用默认）", "default": ""},
        },
    ),
    "list_image_works": CommandDef(
        handler=cmd_list_image_works,
        desc="列出项目中所有图像工作项及其曲线数量",
        params_schema={},
    ),
    "list_report_templates": CommandDef(
        handler=cmd_list_report_templates,
        desc="列出项目中所有报告模板",
        params_schema={},
    ),
    "save_figure_template": CommandDef(
        handler=cmd_save_figure_template,
        desc="将当前绘图配置保存为模板",
        params_schema={
            "name": {"type": "string", "description": "模板名称"},
            "theme": {"type": "string", "description": "主题名称（可选）", "default": "默认"},
            "x_label": {"type": "string", "description": "X 轴标签（可选）", "default": "X"},
            "y_label": {"type": "string", "description": "Y 轴标签（可选）", "default": "Y"},
        },
    ),
    "manage_ai_tool": CommandDef(
        handler=cmd_manage_ai_tool,
        desc="创建或删除 AI 工具（prompt/skill/agent）",
        params_schema={
            "action": {"type": "string", "description": "操作类型：create 或 delete"},
            "tool_type": {"type": "string", "description": "工具类型：prompt/skill/agent"},
            "tool_id": {"type": "string", "description": "工具 ID（delete 时必填）", "default": ""},
            "name": {"type": "string", "description": "工具名称（create 时必填）", "default": ""},
            "content": {"type": "string", "description": "工具内容（create 时必填）", "default": ""},
            "description": {"type": "string", "description": "描述（可选）", "default": ""},
        },
    ),
}


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
