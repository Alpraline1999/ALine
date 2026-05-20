from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.ai.context import AIAssistantContext


def collect_context(
    page_name: str = "",
    selected_node_label: str = "",
    project_name: str = "",
    visible_series_count: int = 0,
    visible_series_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """收集当前页面上下文，构建 AIAssistantContext。

    此函数由各页面的 AIAssistantPanel.refresh_context() 调用，
    传入当前页面的状态信息，返回结构化的上下文快照。
    """
    # 从扩展注册表收集已有扩展类型（防 AI 重复生成）
    ext_types, ext_summary = _collect_extension_registry_info()

    return AIAssistantContext(
        page_name=page_name,
        selected_node_label=selected_node_label,
        page_context_text=_build_page_context_text(page_name, visible_series_count, visible_series_names),
        project_name=project_name,
        available_curves_summary=_build_curves_summary(visible_series_count, visible_series_names),
        available_curve_count=visible_series_count,
        registered_extension_types=ext_types,
        registered_extensions_summary=ext_summary,
    ).model_dump()


def _collect_extension_registry_info() -> tuple[List[str], str]:
    """从全局扩展注册表收集已有扩展的类型列表和摘要。"""
    try:
        from core.extension_api import extension_registry

        all_types: List[str] = []
        for ext in extension_registry.list_processing():
            all_types.append(f"[处理] {ext.type}")
        for ext in extension_registry.list_analysis():
            all_types.append(f"[分析] {ext.type}")
        for ext in extension_registry.list_plot():
            all_types.append(f"[绘图] {ext.type}")
        for ext in extension_registry.list_digitize():
            all_types.append(f"[数字化] {ext.type}")

        type_only = [t.split("] ", 1)[1] for t in all_types if "] " in t]
        summary = f"已注册 {len(all_types)} 个扩展：{', '.join(type_only[:30])}"
        if len(type_only) > 30:
            summary += f" 等共 {len(type_only)} 个"
        return type_only, summary
    except Exception:
        return [], "（无法获取扩展注册表信息）"


def _build_page_context_text(
    page_name: str,
    visible_series_count: int,
    visible_series_names: Optional[List[str]],
) -> str:
    parts = [f"当前页面：{page_name}"]
    if visible_series_count > 0:
        parts.append(f"可见曲线：{visible_series_count} 条")
        if visible_series_names:
            parts.append(f"曲线名称：{', '.join(visible_series_names[:10])}")
    return " | ".join(parts)


def _build_curves_summary(count: int, names: Optional[List[str]]) -> str:
    if count == 0:
        return "当前无可选曲线"
    name_list = ", ".join(names[:10]) if names else ""
    return f"{count} 条曲线" + (f"（{name_list}）" if name_list else "")
