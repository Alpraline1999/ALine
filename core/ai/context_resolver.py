from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.project_manager import project_manager
from core.global_assets import global_assets


@dataclass
class ContextItem:
    """A single @-selected context item."""
    source: str          # "prompt" | "project_item"
    label: str           # Display name
    content: str         # Formatted text content


class ContextBundle:
    """Collection of ContextItems, formatted for system prompt injection."""
    def __init__(self):
        self._items: List[ContextItem] = []

    def add(self, item: ContextItem) -> None:
        self._items.append(item)

    def to_system_text(self, max_chars: int = 8000) -> str:
        parts = []
        total = 0
        for item in self._items:
            block = f"[{item.label}]\n{item.content}\n"
            total += len(block)
            if total > max_chars:
                break
            parts.append(block)
        return "\n".join(parts)


class ContextResolver:
    """Resolve @xxx references in user input to context items."""

    @staticmethod
    def resolve_all(text: str, bundle: ContextBundle) -> str:
        """Scan for @xxx, resolve each, append to bundle, return cleaned text."""
        def _replace(match):
            name = match.group(1)
            item = ContextResolver._resolve_one(name)
            if item:
                bundle.add(item)
            return ""
        return re.sub(r"@(\S+)", _replace, text)

    @staticmethod
    def _resolve_one(name: str) -> Optional[ContextItem]:
        # Prompt has priority
        item = ContextResolver._resolve_prompt(name)
        if item:
            return item
        return ContextResolver._resolve_project_item(name)

    @staticmethod
    def _resolve_prompt(name: str) -> Optional[ContextItem]:
        for p in global_assets.list_ai_prompts():
            if name.lower() in p.name.lower():
                return ContextItem("prompt", p.name, p.content)
        return None

    @staticmethod
    def _resolve_project_item(name: str) -> Optional[ContextItem]:
        p = project_manager.current_project
        if not p:
            return None
        name_lower = name.lower()
        for node in p.tree.nodes:
            node_name = (getattr(node, 'name', '') or '').strip()
            if not node_name:
                continue
            if name_lower not in node_name.lower():
                continue
            return ContextResolver._format_node(node)
        return None

    @staticmethod
    def _format_node(node) -> Optional[ContextItem]:
        kind = node.kind
        name = (getattr(node, 'name', '') or '').strip()
        p = project_manager.current_project
        if not p:
            return ContextItem("project_item", name, f"节点: {name} ({kind})")

        if kind == "data_file":
            df = next((d for d in p.data_files if d.id == node.id), None)
            if not df:
                return ContextItem("project_item", name, f"数据文件: {name}")
            series_lines = [f"  - {s.name} ({len(s.x)} 点)" for s in df.series]
            return ContextItem("project_item", name,
                f"数据文件: {name}\n系列数: {len(df.series)}\n" + "\n".join(series_lines))

        if kind == "pipeline":
            sp = next((s for s in global_assets.list_saved_pipelines() if s.id == node.id), None)
            if sp:
                ops = [f"  {i+1}. {op.get('type','?')}" for i, op in enumerate(sp.ops)]
                return ContextItem("project_item", name,
                    f"Pipeline: {name}\n" + "\n".join(ops))
            return ContextItem("project_item", name, f"Pipeline: {name}")

        if kind == "analysis_result":
            ar = next((a for a in p.analyses if a.id == node.id), None)
            if ar:
                summary = json.dumps(ar.summary, ensure_ascii=False, default=str)
                return ContextItem("project_item", name,
                    f"分析结果: {name}\n类型: {ar.analysis_type}\n摘要: {summary}")
            return ContextItem("project_item", name, f"分析结果: {name}")

        if kind == "report_template":
            rt = next((r for r in global_assets.list_report_templates() if r.id == node.id), None)
            if rt:
                return ContextItem("project_item", name,
                    f"报告模板: {name}\n{rt.content[:800]}")
            return ContextItem("project_item", name, f"报告模板: {name}")

        if kind == "image_work":
            iw = next((im for im in p.images if im.id == node.id), None)
            if iw:
                return ContextItem("project_item", name,
                    f"数字化图像: {name}\n曲线数: {len(iw.curves)}")
            return ContextItem("project_item", name, f"数字化图像: {name}")

        return ContextItem("project_item", name, f"节点: {name} ({kind})")


__all__ = ["ContextItem", "ContextBundle", "ContextResolver"]
