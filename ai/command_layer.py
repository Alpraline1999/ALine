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


def _normalize_series_key(value: str) -> str:
    return "".join(ch for ch in value.strip().lower() if not ch.isspace())


def _iter_project_series(project):
    seen_ids = set()
    for dataset in getattr(project, "datasets", []):
        for series in dataset.series:
            if series.id in seen_ids:
                continue
            seen_ids.add(series.id)
            yield series, dataset.name
    for data_file in getattr(project, "data_files", []):
        for series in data_file.series:
            if series.id in seen_ids:
                continue
            seen_ids.add(series.id)
            yield series, data_file.name


def _resolve_series(project, series_key: str):
    clean_key = str(series_key or "").strip()
    if not clean_key:
        return None, "缺少系列标识"

    series = project.find_series(clean_key)
    if series is not None:
        return series, None

    exact_matches = []
    normalized_matches = []
    normalized_key = _normalize_series_key(clean_key)
    for item, owner_name in _iter_project_series(project):
        scoped_name = f"{owner_name} / {item.name}" if owner_name else item.name
        if item.name == clean_key or scoped_name == clean_key:
            exact_matches.append(item)
            continue
        item_name_key = _normalize_series_key(item.name)
        scoped_name_key = _normalize_series_key(scoped_name)
        if normalized_key in {item_name_key, scoped_name_key}:
            normalized_matches.append(item)

    matches = exact_matches or normalized_matches
    unique_matches = []
    seen_ids = set()
    for item in matches:
        if item.id in seen_ids:
            continue
        seen_ids.add(item.id)
        unique_matches.append(item)

    if len(unique_matches) == 1:
        return unique_matches[0], None
    if len(unique_matches) > 1:
        names = "、".join(item.name for item in unique_matches[:5])
        return None, f"系列标识不唯一: {clean_key}，匹配到 {names}"
    return None, f"找不到系列: {clean_key}"


# ─────────────────────────────────────────────────────────────
# Command handlers
# ─────────────────────────────────────────────────────────────

def cmd_get_project_summary(params: dict) -> CommandResult:
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    summary = {
        "name": p.name,
        "images": len(p.images),
        "datasets": len(p.datasets),
        "data_files": len(p.data_files),
        "analyses": len(p.analyses),
        "saved_pipelines": len(global_assets.list_saved_pipelines()),
        "aline_version": p.aline_version,
    }
    return CommandResult(data=summary)


def cmd_list_data_files(params: dict) -> CommandResult:
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    items = []
    for df in p.data_files:
        items.append({
            "id": df.id,
            "name": df.name,
            "series_count": len(df.series),
            "series": [{"id": s.id, "name": s.name, "n": len(s.x)} for s in df.series],
        })
    return CommandResult(data=items)


def cmd_create_folder(params: dict) -> CommandResult:
    name = params.get("name", "新文件夹")
    parent_id = params.get("parent_id")
    node = project_manager.add_folder(name, parent_id)
    if node is None:
        return CommandResult(success=False, error="创建文件夹失败")
    return CommandResult(data={"id": node.id, "name": node.name})


def cmd_apply_pipeline(params: dict) -> CommandResult:
    series_id = params.get("series_id", "")
    ops = params.get("ops", [])
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    series, error = _resolve_series(p, series_id)
    if series is None:
        return CommandResult(success=False, error=error or f"找不到系列: {series_id}")
    from processing.data_engine import apply_pipeline
    xs, ys = apply_pipeline(list(series.x), list(series.y), ops)
    return CommandResult(data={"xs": xs[:10], "ys": ys[:10], "n": len(xs)})


def cmd_save_pipeline(params: dict) -> CommandResult:
    name = params.get("name", "pipeline")
    ops = params.get("ops", [])
    description = params.get("description", "")
    sp = project_manager.add_saved_pipeline(name, ops, description)
    if sp is None:
        return CommandResult(success=False, error="保存 Pipeline 失败")
    return CommandResult(data={"id": sp.id, "name": sp.name})


def cmd_fit_curve(params: dict) -> CommandResult:
    series_id = params.get("series_id", "")
    model = params.get("model", "linear")
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    series, error = _resolve_series(p, series_id)
    if series is None:
        return CommandResult(success=False, error=error or f"找不到系列: {series_id}")
    try:
        from core.analysis_engine import fit_curve
        r = fit_curve(list(series.x), list(series.y), model)
        return CommandResult(data={
            "model": r["model"],
            "equation": r["equation"],
            "r2": r["r2"],
            "params": r["params"],
            "param_names": r["param_names"],
        })
    except Exception as e:
        return CommandResult(success=False, error=str(e))


def cmd_detect_peaks(params: dict) -> CommandResult:
    series_id = params.get("series_id", "")
    min_height = params.get("min_height")
    min_distance = params.get("min_distance", 1)
    min_distance_x = params.get("min_distance_x")
    prominence = params.get("prominence")
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    series, error = _resolve_series(p, series_id)
    if series is None:
        return CommandResult(success=False, error=error or f"找不到系列: {series_id}")
    try:
        from core.analysis_engine import detect_peaks
        r = detect_peaks(
            list(series.x),
            list(series.y),
            min_height=min_height,
            min_distance=min_distance,
            min_distance_x=min_distance_x,
            prominence=prominence,
        )
        return CommandResult(data=r)
    except Exception as e:
        return CommandResult(success=False, error=str(e))


def cmd_compute_statistics(params: dict) -> CommandResult:
    series_id = params.get("series_id", "")
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    series, error = _resolve_series(p, series_id)
    if series is None:
        return CommandResult(success=False, error=error or f"找不到系列: {series_id}")
    from core.analysis_engine import compute_statistics
    r = compute_statistics(list(series.x), list(series.y))
    return CommandResult(data=r)


def cmd_compute_correlation(params: dict) -> CommandResult:
    series_id1 = params.get("series_id1", "")
    series_id2 = params.get("series_id2", "")
    method = params.get("method", "pearson")
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    s1, error1 = _resolve_series(p, series_id1)
    s2, error2 = _resolve_series(p, series_id2)
    if s1 is None or s2 is None:
        return CommandResult(success=False, error=error1 or error2 or "找不到指定系列")
    try:
        from core.analysis_engine import compute_correlation
        r = compute_correlation(list(s1.y), list(s2.y), method)
        return CommandResult(data=r)
    except Exception as e:
        return CommandResult(success=False, error=str(e))


def cmd_list_saved_pipelines(params: dict) -> CommandResult:
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    return CommandResult(data=[
        {"id": sp.id, "name": sp.name, "description": sp.description, "ops_count": len(sp.ops)}
        for sp in global_assets.list_saved_pipelines()
    ])


# ─── 8 条新命令（v0.3）──────────────────────────────────────────────────

def cmd_import_data_file(params: dict) -> CommandResult:
    """导入数据文件并添加到项目。"""
    file_path = params.get("file_path", "")
    parent_id = params.get("parent_id")
    if not file_path:
        return CommandResult(success=False, error="缺少 file_path 参数")
    try:
        from core.data_operations import import_file
        from models.schemas import DataFile
        import os
        series_list = import_file(file_path)
        df = DataFile(
            name=os.path.basename(file_path),
            source_path=file_path,
            series=series_list,
        )
        node = project_manager.add_data_file(df, parent_id)
        return CommandResult(data={
            "data_file_id": df.id,
            "name": df.name,
            "series_count": len(df.series),
            "node_id": node.id if node else None,
        })
    except Exception as e:
        return CommandResult(success=False, error=str(e))


def cmd_export_series(params: dict) -> CommandResult:
    """将指定数据系列导出为 CSV 文件。"""
    series_id = params.get("series_id", "")
    output_path = params.get("output_path", "")
    if not series_id or not output_path:
        return CommandResult(success=False, error="缺少 series_id 或 output_path")
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    series, error = _resolve_series(p, series_id)
    if series is None:
        return CommandResult(success=False, error=error or f"找不到系列: {series_id}")
    try:
        import csv
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([series.x_label or "x", series.y_label or "y"])
            for x, y in zip(series.x, series.y):
                writer.writerow([x, y])
        return CommandResult(data={"path": output_path, "n": len(series.x)})
    except Exception as e:
        return CommandResult(success=False, error=str(e))


def cmd_apply_pipeline_persist(params: dict) -> CommandResult:
    """对系列执行 Pipeline 并将结果保存为新 DataSeries。"""
    series_id = params.get("series_id", "")
    pipeline_id = params.get("pipeline_id", "")
    new_name = params.get("new_name", "")
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    series, error = _resolve_series(p, series_id)
    if series is None:
        return CommandResult(success=False, error=error or f"找不到系列: {series_id}")
    ops = project_manager.load_pipeline(pipeline_id)
    if not ops:
        return CommandResult(success=False, error=f"找不到 Pipeline: {pipeline_id}")
    try:
        from processing.data_engine import apply_pipeline
        from models.schemas import DataSeries
        xs, ys = apply_pipeline(list(series.x), list(series.y), ops)
        new_series = DataSeries(
            name=new_name or f"{series.name}_processed",
            x=xs, y=ys, source="computed",
        )
        # 找到 series 所在 DataFile 并追加
        for df in p.data_files:
            if any(s.id == series_id for s in df.series):
                df.series.append(new_series)
                p.is_modified = True
                return CommandResult(data={"new_series_id": new_series.id, "name": new_series.name})
        return CommandResult(success=False, error="未找到 series 所在 DataFile")
    except Exception as e:
        return CommandResult(success=False, error=str(e))


def cmd_generate_report(params: dict) -> CommandResult:
    """使用指定模板渲染分析报告，返回 Markdown 字符串。"""
    template_id = params.get("template_id", "")
    analysis_id = params.get("analysis_id", "")
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    # 获取模板内容
    if template_id:
        tmpl = project_manager.get_report_template(template_id)
        template_content = tmpl.content if tmpl else ""
    else:
        from core.analysis_engine import _DEFAULT_REPORT_TEMPLATE
        template_content = _DEFAULT_REPORT_TEMPLATE
    # 获取分析结果
    result_data = {}
    if analysis_id:
        ar = p.find_analysis(analysis_id)
        if ar:
            result_data = dict(ar.summary)
            result_data["analysis_type"] = ar.analysis_type
    from core.analysis_engine import render_report
    md = render_report(template_content, result_data)
    return CommandResult(data={"markdown": md})


def cmd_list_image_works(params: dict) -> CommandResult:
    """列出项目中所有图像工作项。"""
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    return CommandResult(data=[
        {"id": img.id, "name": img.name, "curve_count": len(img.curves)}
        for img in p.images
    ])


def cmd_list_report_templates(params: dict) -> CommandResult:
    """列出项目中所有报告模板。"""
    p = project_manager.current_project
    if p is None:
        return CommandResult(success=False, error="没有打开的项目")
    return CommandResult(data=[
        {"id": t.id, "name": t.name, "is_builtin": t.is_builtin}
        for t in global_assets.list_report_templates(include_builtin=True)
    ])


def cmd_save_figure_template(params: dict) -> CommandResult:
    """将指定绘图配置保存为模板。"""
    name = params.get("name", "untitled")
    theme = params.get("theme", "默认")
    from models.schemas import FigureConfig, AxisConfig
    config = FigureConfig(
        name=name,
        theme=theme,
        typed_axis_config=AxisConfig(
            x_label=params.get("x_label", "X"),
            y_label=params.get("y_label", "Y"),
        ),
    )
    template = project_manager.add_figure_template(config)
    if template is None:
        return CommandResult(success=False, error="保存失败")
    return CommandResult(data={"figure_id": template.id, "name": template.name})


def cmd_manage_ai_tool(params: dict) -> CommandResult:
    """创建/更新/删除 AI 工具（prompt/skill/agent）。"""
    action = params.get("action", "create")  # create / update / delete
    tool_type = params.get("tool_type", "prompt")  # prompt / skill / agent
    tool_id = params.get("tool_id", "")
    name = params.get("name", "")
    content = params.get("content", "")
    description = params.get("description", "")

    if action == "create":
        if tool_type == "prompt":
            obj = project_manager.add_ai_prompt(name, content, description)
        elif tool_type == "skill":
            obj = project_manager.add_ai_skill(name, content, description)
        elif tool_type == "agent":
            obj = project_manager.add_ai_agent(name, content, description)
        else:
            return CommandResult(success=False, error=f"未知 tool_type: {tool_type}")
        if obj is None:
            return CommandResult(success=False, error="创建失败")
        return CommandResult(data={"id": obj.id, "name": obj.name, "type": tool_type})

    if action == "delete":
        if tool_type == "prompt":
            ok = project_manager.delete_ai_prompt(tool_id)
        elif tool_type == "skill":
            ok = project_manager.delete_ai_skill(tool_id)
        elif tool_type == "agent":
            ok = project_manager.delete_ai_agent(tool_id)
        else:
            return CommandResult(success=False, error=f"未知 tool_type: {tool_type}")
        return CommandResult(data={"deleted": ok})

    return CommandResult(success=False, error=f"未知 action: {action}")


# ─────────────────────────────────────────────────────────────
# 命令注册表
# ─────────────────────────────────────────────────────────────

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
        for name, cmd in COMMANDS.items():
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
                return CommandResult(success=False, error="找不到指定 Prompt")
            return CommandResult(data={
                "type": "prompt",
                "name": prompt.name,
                "description": prompt.description,
                "content": prompt.content,
            })

        if kind == "skill":
            skill = global_assets.get_ai_skill(item_id)
            if skill is None:
                return CommandResult(success=False, error="找不到指定 Skill")
            result = skill_runner.run(skill.code, extra_vars={
                "task": params.get("task", ""),
                "payload": params.get("payload"),
                "context": dict(self._runtime_context),
            })
            return CommandResult(data={
                "type": "skill",
                "name": skill.name,
                **result.to_dict(),
            })

        if kind == "agent":
            agent = global_assets.get_ai_agent(item_id)
            if agent is None:
                return CommandResult(success=False, error="找不到指定 Agent")
            task = str(params.get("task") or "").strip()
            if not task:
                return CommandResult(success=False, error="缺少 task 参数")
            context_text = str(self._runtime_context.get("context_text") or "暂无上下文")
            try:
                response = asyncio.run(AIClient().chat([
                    {"role": "system", "content": agent.system_prompt},
                    {"role": "user", "content": f"ALine 当前上下文:\n{context_text}\n\n子任务:\n{task}"},
                ]))
            except Exception as exc:
                return CommandResult(success=False, error=str(exc))
            if response.error:
                return CommandResult(success=False, error=response.error)
            return CommandResult(data={
                "type": "agent",
                "name": agent.name,
                "content": response.content or "",
            })

        return CommandResult(success=False, error=f"未知 AI 工具类型: {kind}")

    def execute(self, command: dict) -> CommandResult:
        """command = {"action": "cmd_name", "params": {...}}"""
        action = command.get("action", "")
        params = command.get("params", {})
        cmd_def = COMMANDS.get(action)
        if cmd_def is not None:
            try:
                return cmd_def.handler(params)
            except Exception as e:
                return CommandResult(success=False, error=str(e))

        dynamic_tool = self._dynamic_tool_entry(action)
        if dynamic_tool is not None:
            return self._execute_dynamic_tool(dynamic_tool, params)

        return CommandResult(success=False, error=f"未知命令: {action}")

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
