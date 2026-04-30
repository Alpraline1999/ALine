from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from models.schemas import Project


@dataclass(slots=True)
class ProjectRepository:
    project_file_suffix: str
    aline_version: str
    normalize_path: Callable[[str], str]
    sync_legacy_datasets: Callable[[Project], None]
    sync_project_backups: Callable[[Project, str, str | None], None]
    add_recent_project: Callable[[str, str], None]

    def normalize_project_file_path(self, file_path: str, *, for_save: bool) -> str:
        normalized = self.normalize_path(file_path)
        suffix = Path(normalized).suffix.lower()
        if not suffix:
            if for_save:
                return f"{normalized}{self.project_file_suffix}"
            raise ValueError(f"项目文件必须使用 {self.project_file_suffix} 扩展名")
        if suffix != self.project_file_suffix:
            action = "保存" if for_save else "打开"
            raise ValueError(f"仅支持 {self.project_file_suffix} 项目文件，无法{action}: {normalized}")
        return normalized

    def open_project(self, file_path: str) -> Project:
        normalized_path = self.normalize_project_file_path(file_path, for_save=False)
        if not os.path.exists(normalized_path):
            raise FileNotFoundError(f"项目文件不存在: {normalized_path}")

        with open(normalized_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        project = Project(**data)
        project.file_path = normalized_path
        project.is_modified = False
        self.add_recent_project(normalized_path, project.name)
        return project

    def save_project(self, project: Project, file_path: str | None = None) -> str:
        target_path = file_path or project.file_path
        if target_path is None:
            raise ValueError("未指定保存路径")

        normalized_path = self.normalize_project_file_path(target_path, for_save=True)
        previous_path = project.file_path

        dir_path = os.path.dirname(normalized_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        project.updated_at = datetime.now().isoformat()
        if project.aline_version is None:
            project.aline_version = self.aline_version

        self.sync_legacy_datasets(project)
        self.sync_project_backups(project, normalized_path, previous_path)

        data = project.model_dump()
        data.pop("file_path", None)
        data.pop("is_modified", None)

        with open(normalized_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

        project.file_path = normalized_path
        project.is_modified = False
        self.add_recent_project(normalized_path, project.name)
        return normalized_path
