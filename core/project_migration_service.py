"""项目树初始化服务 — 为新项目创建标准树结构。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from aline_metadata import CURRENT_PROJECT_VERSION
from models.schemas import Project, ProjectTree


@dataclass(slots=True)
class ProjectTreeInitService:
    """为新项目创建标准 v0.3 树结构。

    旧版项目格式（.pyline / 旧 .aline JSON）的迁移方法
    ``migrate_to_v2`` / ``migrate_to_v3`` 已随旧格式支持移除。
    """

    ensure_project_tree_groups: Callable[[Project | None], None]

    def init_new_project_tree(self, project: Project) -> None:
        project.tree = ProjectTree()
        project.aline_version = CURRENT_PROJECT_VERSION
        self.ensure_project_tree_groups(project)

    def ensure_project_tree(self, project: Project | None) -> None:
        """确保 project.tree 已初始化，如果已有树则不覆盖（避免丢失已有节点）。"""
        if project is None:
            return
        if project.tree is not None:
            return
        self.init_new_project_tree(project)
