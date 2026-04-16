from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


class AIAssistantContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_name: str = ""
    selected_node_label: str = ""
    page_context_text: str = ""


def build_context_snapshot(page_name: str, selected_node_label: str, page_context_text: str) -> Dict[str, Any]:
    return AIAssistantContext(
        page_name=page_name,
        selected_node_label=selected_node_label,
        page_context_text=page_context_text,
    ).model_dump()