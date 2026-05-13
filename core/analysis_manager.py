"""
分析结果管理器 — 分析结果的 CRUD 与查询。

只处理 AnalysisResult 对象自身的管理，
不涉及分析算法的执行（由 core/analysis_engine.py 负责）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.schemas import AnalysisResult, AnalysisResultNode


class AnalysisManager:
    """分析结果的 CRUD 与查询。

    通过持有 ProjectManager 引用来访问当前项目，
    负责 AnalysisResult 的创建、删除、查找和查询。
    """

    def __init__(self, project_manager):
        self._pm = project_manager

    @property
    def _project(self):
        return self._pm.current_project

    def create_analysis(
        self,
        name: str,
        analysis_type: str,
        input_series_ids: List[str],
        params: Dict[str, Any],
        result_series_id: Optional[str] = None,
        summary: Optional[Dict[str, Any]] = None,
    ) -> AnalysisResult:
        """创建分析结果并添加到当前项目。"""
        result = AnalysisResult(
            name=name,
            analysis_type=analysis_type,
            input_series_ids=input_series_ids,
            params=params,
            result_series_id=result_series_id,
            summary=summary or {},
        )
        project = self._project
        project.analyses.append(result)
        self._pm._ensure_project_tree_groups(project)
        folder = self._pm._find_folder_by_group_type("analysis_result_group")
        parent_id = folder.id if folder else None
        if project.tree is not None:
            project.tree.nodes.append(
                AnalysisResultNode(
                    name=result.name,
                    analysis_id=result.id,
                    parent_id=parent_id,
                )
            )
        project.is_modified = True
        return result

    def delete_analysis(self, analysis_id: str) -> bool:
        """从项目中删除指定分析结果。"""
        project = self._project
        if project is None:
            return False
        before = len(project.analyses)
        project.analyses = [a for a in project.analyses if a.id != analysis_id]
        changed = len(project.analyses) < before
        if changed:
            if project.tree is not None:
                project.tree.nodes = [
                    n
                    for n in project.tree.nodes
                    if not (n.kind == "analysis_result" and n.analysis_id == analysis_id)
                ]
            project.is_modified = True
        return changed

    def find_analysis(self, analysis_id: str) -> Optional[AnalysisResult]:
        """按 ID 查找分析结果。"""
        project = self._project
        if project is None:
            return None
        for a in project.analyses:
            if a.id == analysis_id:
                return a
        return None

    def get_analyses_for_series(self, series_id: str) -> List[AnalysisResult]:
        """返回引用了指定数据系列的所有分析结果。"""
        project = self._project
        if project is None:
            return []
        return [a for a in project.analyses if series_id in a.input_series_ids]
