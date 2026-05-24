from __future__ import annotations
from typing import Dict, List, Optional

from core.project_manager import project_manager
from core.global_assets import global_assets


class AIContextProvider:
    """Provides search results for @-completion in the AI input."""

    @staticmethod
    def search(query: str, max_results: int = 30) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        q = query.lower()

        # 1. Match prompts (all if no query)
        for prompt in global_assets.list_ai_prompts():
            if not q or q in prompt.name.lower():
                results.append({
                    "label": prompt.name,
                    "type": "Prompt",
                    "description": prompt.description or prompt.content[:60],
                    "source": "prompt",
                })

        # 2. Match project tree nodes (all if no query)
        p = project_manager.current_project
        if p:
            for node in p.tree.nodes:
                node_name = (getattr(node, 'name', '') or '').strip()
                if not node_name:
                    continue
                if not q or q in node_name.lower():
                    results.append({
                        "label": node_name,
                        "type": node.kind,
                        "description": node.kind,
                        "source": "project_item",
                    })

        return results[:max_results]


__all__ = ["AIContextProvider"]
