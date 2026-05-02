"""
跨页共享的保存/导出目标解析协调器。

提取 DigitizePage/AnalysisPage/ProcessPage 之间重复的
find-or-create 文件夹目标解析和导出协调模式。
"""
from __future__ import annotations

from typing import Callable, Optional

from core.project_manager import project_manager


class SaveExportCoordinator:
    """保存/导出目标协调器。

    通过回调注入，避免对页面类的循环引用。
    """

    def __init__(
        self,
        *,
        get_children: Callable,
        add_folder: Callable,
        notify_info: Callable,
        notify_warning: Callable,
        notify_error: Callable,
    ):
        self._get_children = get_children
        self._add_folder = add_folder
        self._notify_info = notify_info
        self._notify_warning = notify_warning
        self._notify_error = notify_error

    def find_or_create_folder(
        self,
        folder_name: str,
        parent_group_type: str = "datasets",
        *,
        folder_group_type: Optional[str] = None,
        fallback: Optional[str] = None,
    ) -> Optional[str]:
        """在指定分组下查找或创建文件夹。

        Args:
            folder_name: 要查找/创建的文件夹名称
            parent_group_type: 父级分组的 group_type，默认 "datasets"
            folder_group_type: 新建子文件夹的 group_type；默认与父分组一致
            fallback: 若创建失败时返回的 fallback 节点 ID

        Returns:
            文件夹节点 ID，或 None（找不到且创建失败）
        """
        root = project_manager.find_folder_by_group_type(parent_group_type)
        if root is None:
            return None

        for node in self._get_children(root.id):
            if node.kind == "folder" and getattr(node, "name", "") == folder_name:
                return node.id

        folder = self._add_folder(
            folder_name,
            parent_id=root.id,
            group_type=folder_group_type or parent_group_type,
        )
        if folder is not None:
            return folder.id
        return fallback

    @staticmethod
    def find_folder(parent_group_type: str = "datasets") -> Optional[str]:
        """查找分组文件夹。"""
        root = project_manager.find_folder_by_group_type(parent_group_type)
        return root.id if root is not None else None

    @staticmethod
    def normalize_name(name: str) -> str:
        """标准化名称（用于去重比较）。"""
        return project_manager.normalize_name_key(name)

    def notify_info(self, title: str, content: str) -> None:
        self._notify_info(title, content)

    def notify_warning(self, title: str, content: str) -> None:
        self._notify_warning(title, content)

    def notify_error(self, title: str, content: str) -> None:
        self._notify_error(title, content)
