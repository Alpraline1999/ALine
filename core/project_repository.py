from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Set

from models.schemas import Project


@dataclass(slots=True)
class ProjectRepository:
    project_file_suffix: str
    aline_version: str
    normalize_path: Callable[[str], str]
    sync_project_backups: Callable[[Project, str, str | None], None]
    add_recent_project: Callable[[str, str], None]
    get_binary_workspace: Callable[[str], Any] = field(default=lambda pid: None)
    get_empty_binary_folder_paths: Callable[[Project], Set[str]] = field(default=lambda p: set())

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

        from core.zip_serializer import ZipProjectSerializer
        project = ZipProjectSerializer.load(normalized_path)
        project.file_path = normalized_path
        project.is_modified = False

        from core.lazy_series import convert_to_lazy
        convert_to_lazy(project, normalized_path)

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

        self.sync_project_backups(project, normalized_path, previous_path)

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

        # Collect binary file paths for ZIP container save
        modified_binary_paths: Set[str] = set()

        # Include removed paths so old ZIP entries are excluded on save
        ws = self.get_binary_workspace(project.id) if project.id else None
        if ws is not None:
            for removed in ws.removed_paths():
                modified_binary_paths.add(removed)

        for sf in project.source_files:
            p = sf.file_path or ""
            if p and not Path(p).is_absolute():
                modified_binary_paths.add(p)
        for img in project.images:
            p = img.image_path or ""
            if p and not Path(p).is_absolute():
                modified_binary_paths.add(p)
        for pic in project.pictures:
            p = pic.image_path or ""
            if p and not Path(p).is_absolute():
                modified_binary_paths.add(p)

        # Collect empty tree folder paths for ZIP persistence
        empty_binary_dirs = self.get_empty_binary_folder_paths(project)

        from core.zip_serializer import ZipProjectSerializer
        ZipProjectSerializer.save(
            project, normalized_path,
            modified_series_ids=all_series,
            modified_curve_ids=all_curves,
            modified_binary_paths=modified_binary_paths,
            binary_workspace=ws,
            empty_binary_dirs=empty_binary_dirs,
        )

        project.file_path = normalized_path
        project.is_modified = False
        self.add_recent_project(normalized_path, project.name)
        return normalized_path
