"""项目文件序列化层 — 读写 .aline 文件，处理版本迁移"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.project_migration_service import ProjectMigrationService

from aline_metadata import CURRENT_PROJECT_VERSION
from models.schemas import Project


class ProjectSerializer:
    """项目文件序列化器。

    职责：
    - 将 Project 对象原子写入 .aline 文件（临时文件 → fsync → os.replace）
    - 从 .aline 文件加载 Project 对象
    - 检测项目文件格式版本（pyline_v1 / pyline_v2 / aline_v3）
    - 处理旧版本格式迁移（v1 → v2 → v3）

    使用方式：
        serializer = ProjectSerializer(migration_service)
        serializer.save(project, "/path/to/project.aline")
        project = serializer.load("/path/to/project.aline")
    """

    SUFFIX = ".aline"

    def __init__(self, migration_service: Optional[ProjectMigrationService] = None, aline_version: str = CURRENT_PROJECT_VERSION):
        """初始化序列化器。

        Args:
            migration_service: ProjectMigrationService 实例，用于加载时自动迁移。
                               为 None 时 load() 不执行迁移（仅用于独立测试）。
            aline_version: 保存时写入的 aline_version 值。
        """
        self._migration = migration_service
        self._aline_version = aline_version or CURRENT_PROJECT_VERSION

    # ── save ─────────────────────────────────────────────────────

    def save(self, project: Project, path: str) -> None:
        """将 project 序列化到 path。

        原子写入：先写入 .tmp 文件 → fsync → os.replace 原子替换。
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

        data = project.model_dump()
        data.pop("file_path", None)
        data.pop("is_modified", None)

        temp_path = path + ".tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, path)
        except Exception:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

        project.file_path = path
        project.is_modified = False

    # ── load ─────────────────────────────────────────────────────

    def load(self, path: str) -> Optional[Project]:
        """从 path 加载 Project，自动检测版本并迁移。

        Args:
            path: .aline 文件路径。

        Returns:
            Project 对象，如果文件不存在或 JSON 无效则返回 None。
        """
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        try:
            project = Project(**data)
        except Exception:
            return None

        project.file_path = path
        project.is_modified = False

        self._migrate_loaded(project)

        return project

    # ── detect_format ────────────────────────────────────────────

    def detect_format(self, path: str) -> Optional[str]:
        """检测文件格式: 'pyline_v1' | 'pyline_v2' | 'aline_v3'。

        Args:
            path: 项目文件路径。

        Returns:
            格式字符串，如果文件不存在返回 None。
        """
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        version = data.get("aline_version")
        if version is None:
            return "pyline_v1"
        if version == "0.2":
            return "pyline_v2"
        return "aline_v3"

    # ── migrate ──────────────────────────────────────────────────

    def migrate(self, project: Project, target_version: str) -> Project:
        """将 project 迁移到目标格式版本。

        Args:
            project: 待迁移的 Project 对象。
            target_version: 目标版本（"0.2" 或 "0.3" / CURRENT_PROJECT_VERSION）。

        Returns:
            迁移后的 Project（就地修改）。
        """
        if self._migration is None:
            return project

        current = project.aline_version
        if current is None:
            self._migration.migrate_to_v2(project)
        if project.aline_version and project.aline_version == "0.2" and target_version in ("0.3", CURRENT_PROJECT_VERSION, "0.1.0"):
            self._migration.migrate_to_v3(project)
        return project

    # ── 内部迁移 ─────────────────────────────────────────────────

    def _migrate_loaded(self, project: Project) -> None:
        """加载后执行版本迁移（如果 migration_service 可用）。"""
        if self._migration is None:
            return
        try:
            self._migration.migrate_to_v2(project)
            self._migration.migrate_to_v3(project)
        except Exception:
            pass
