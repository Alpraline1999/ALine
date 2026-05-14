"""项目文件序列化层 — 读写 .aline ZIP 容器文件"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from aline_metadata import CURRENT_PROJECT_VERSION
from models.schemas import Project


class ProjectSerializer:
    """项目文件序列化器。

    职责：
    - 将 Project 对象原子写入 .aline ZIP 容器（临时文件 + os.replace）
    - 从 .aline ZIP 文件加载 Project 对象，series/curve 数据点通过
      LazyDataSeries/LazyCurve 按需加载

    使用方式：
        serializer = ProjectSerializer()
        serializer.save(project, "/path/to/project.aline")
        project = serializer.load("/path/to/project.aline")
    """

    SUFFIX = ".aline"

    def __init__(self, aline_version: str = CURRENT_PROJECT_VERSION):
        self._aline_version = aline_version or CURRENT_PROJECT_VERSION

    # ── save ─────────────────────────────────────────────────────

    def save(self, project: Project, path: str) -> None:
        """将 project 序列化到 path（ZIP 容器格式）。

        写入前自动更新 updated_at、补充 aline_version、排除运行时字段。

        Args:
            project: 要保存的 Project 对象。
            path: 目标 .aline 文件路径。

        Raises:
            OSError: 写入失败时抛出。
        """
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        project.updated_at = datetime.now().isoformat()
        if project.aline_version is None:
            project.aline_version = self._aline_version

        # Collect all data IDs for ZIP container save
        all_series: set[str] = set()
        for df in project.data_files:
            for s in df.series:
                all_series.add(s.id)
        for ds in project.datasets:
            for s in ds.series:
                all_series.add(s.id)
        all_curves: set[str] = set()
        for img in project.images:
            for c in img.curves:
                all_curves.add(c.id)
        for c in project.imported_curves:
            all_curves.add(c.id)

        from core.zip_serializer import ZipProjectSerializer
        ZipProjectSerializer.save(
            project, path,
            modified_series_ids=all_series,
            modified_curve_ids=all_curves,
        )

        project.file_path = path
        project.is_modified = False

    # ── load ─────────────────────────────────────────────────────

    def load(self, path: str) -> Optional[Project]:
        """从 path 加载 Project（仅支持 ZIP 容器格式）。

        ZIP 格式下 series/curve 的数据点通过 LazyDataSeries/LazyCurve 按需加载。

        Args:
            path: .aline 文件路径。

        Returns:
            Project 对象，如果文件不存在或格式无效则返回 None。
        """
        if not os.path.exists(path):
            return None

        from core.zip_serializer import ZipProjectSerializer
        try:
            project = ZipProjectSerializer.load(path)
        except (ValueError, Exception):
            return None

        from core.lazy_series import convert_to_lazy
        convert_to_lazy(project, path)

        project.file_path = path
        project.is_modified = False

        return project
