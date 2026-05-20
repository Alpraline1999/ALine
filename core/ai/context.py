from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class AIAssistantContext(BaseModel):
    """AI 助手的完整上下文快照，包含页面状态和项目信息。"""
    model_config = ConfigDict(extra="ignore")

    # 页面信息
    page_name: str = ""
    selected_node_label: str = ""
    page_context_text: str = ""

    # 项目信息
    project_name: str = ""
    available_curves_summary: str = ""
    available_curve_count: int = 0

    # 扩展信息（供 AI 参考已有扩展，防止生成重复）
    registered_extension_types: List[str] = []
    registered_extensions_summary: str = ""


def build_context_snapshot(
    page_name: str = "",
    selected_node_label: str = "",
    page_context_text: str = "",
    project_name: str = "",
    available_curves_summary: str = "",
    available_curve_count: int = 0,
    registered_extension_types: List[str] | None = None,
    registered_extensions_summary: str = "",
) -> Dict[str, Any]:
    return AIAssistantContext(
        page_name=page_name,
        selected_node_label=selected_node_label,
        page_context_text=page_context_text,
        project_name=project_name,
        available_curves_summary=available_curves_summary,
        available_curve_count=available_curve_count,
        registered_extension_types=registered_extension_types or [],
        registered_extensions_summary=registered_extensions_summary,
    ).model_dump()