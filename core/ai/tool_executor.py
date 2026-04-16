from __future__ import annotations

from typing import Any, Dict

from core.analysis_engine import render_report
from core.project_manager import project_manager
from .tool_registry import TOOLS


def execute_tool(tool_name: str, context: Dict[str, Any] | None = None) -> str:
    ctx = context or {}
    if tool_name not in TOOLS:
        return f"未知工具: {tool_name}"

    if tool_name == "list_tree_nodes":
        project = project_manager.current_project
        if project is None or project.tree is None:
            return "当前没有已打开项目"
        lines = [f"- {node.kind}: {node.name}" for node in project.tree.nodes[:50]]
        return "\n".join(lines) if lines else "项目树为空"

    if tool_name == "get_node_detail":
        node_id = ctx.get("selected_node_id")
        if not node_id:
            return "当前没有选中节点"
        node = project_manager.get_node_by_id(node_id)
        if node is None:
            return f"未找到节点: {node_id}"
        return str(node.model_dump())

    if tool_name == "list_data_files":
        project = project_manager.current_project
        if project is None:
            return "当前没有已打开项目"
        lines = [f"- {df.name}: {len(df.series)} 列" for df in project.data_files]
        return "\n".join(lines) if lines else "当前项目没有数据文件"

    if tool_name == "read_chart_config":
        page = ctx.get("chart_page")
        if page is None:
            return "当前不在可视化页"
        return str(page._figure_state.model_dump())

    if tool_name == "save_pipeline_template":
        page = ctx.get("process_page")
        if page is None:
            return "当前不在数据处理页"
        if not page._ops:
            return "当前没有可保存的处理链"
        name = ctx.get("template_name", "AI 保存模板")
        if page._save_pipeline_template_as_named(name):
            return f"已保存 Pipeline 模板: {name}"
        return "保存 Pipeline 模板失败"

    if tool_name == "render_report_template":
        page = ctx.get("analysis_page")
        if page is None:
            return "当前不在数据分析页"
        content = page._report_editor.toPlainText()
        return render_report(content, page._result)

    if tool_name == "export_curve_to_data_file":
        page = ctx.get("digitize_page")
        if page is None:
            return "当前不在图片取点页"
        page._on_export_to_data_file()
        return page._status_label.text() or "已尝试导出当前曲线"

    return f"工具尚未实现: {tool_name}"