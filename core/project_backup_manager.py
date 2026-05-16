from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from models.schemas import ImageWork, PictureAsset, Project, SourceFileAsset


@dataclass(slots=True)
class ProjectBackupManager:
    manager: Any

    # ── 内部辅助 ────────────────────────────────────────────

    def _rel_root(self, project_file_path: str) -> Path:
        """返回存储相对路径的计算基准目录。

        有暂存区时返回 ws.temp_dir，否则返回项目父目录。
        """
        for p in self.manager._projects:
            if p.file_path and Path(p.file_path).resolve() == Path(project_file_path).resolve():
                ws = self.manager._get_workspace(p)
                if ws is not None:
                    return ws.temp_dir
                break
        return Path(project_file_path).parent

    def _resolve_managed_abs(self, raw_path: str, project_file_path: str) -> str:
        """将相对路径解析为绝对路径（支持暂存区）。"""
        for p in self.manager._projects:
            if p.file_path and Path(p.file_path).resolve() == Path(project_file_path).resolve():
                ws = self.manager._get_workspace(p)
                if ws is not None:
                    return ws.resolve(raw_path)
                break
        return str((Path(project_file_path).parent / raw_path).resolve())

    # ── 备份方法 ────────────────────────────────────────────

    def backup_image_for_project(
        self,
        image: ImageWork,
        project_file_path: str,
        source_project: Optional[Project],
    ) -> None:
        source_abs = self.manager.resolve_image_path(image, source_project)
        if not source_abs:
            return
        source_path = Path(source_abs)
        if not source_path.exists():
            raise FileNotFoundError(f"图像文件不存在: {source_abs}")
        backup_dir = self.manager._project_assets_dir(project_file_path, "images")
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_filename = self.manager._backup_filename(image, source_path.suffix)
        backup_path = backup_dir / backup_filename
        current_backup_abs = ""
        if image.image_path and not Path(image.image_path).is_absolute():
            current_backup_abs = self._resolve_managed_abs(image.image_path, project_file_path)
        if backup_path.exists() and str(backup_path.resolve()) not in {current_backup_abs, str(source_path.resolve())}:
            backup_path = self.manager._ensure_unique_path(backup_path, image.id)
        if source_path.resolve() != backup_path.resolve():
            self.manager._copy_file(source_path, backup_path)
        rel_path = backup_path.relative_to(self._rel_root(project_file_path))
        image.image_path = rel_path.as_posix()
        image.source_image_path = str(source_path)

    def backup_picture_for_project(
        self,
        picture: PictureAsset,
        project_file_path: str,
        source_project: Optional[Project],
        target_folder_id: Optional[str] = None,
    ) -> None:
        source_abs = self.manager.resolve_picture_path(picture, source_project)
        if not source_abs:
            return
        source_path = Path(source_abs)
        if not source_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {source_abs}")
        backup_root = self.manager._project_assets_dir(project_file_path, "pictures")
        relative_subdir = self.manager._picture_relative_subdir(picture)
        if relative_subdir is not None:
            backup_dir = backup_root / relative_subdir
        elif target_folder_id and self.manager.current_project is not None and self.manager.current_project.file_path == project_file_path:
            folder_path = self.manager.resolve_picture_folder_path(target_folder_id, create=True)
            backup_dir = Path(folder_path) if folder_path else backup_root
        else:
            backup_dir = backup_root
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_filename = self.manager._backup_filename(picture, source_path.suffix)
        backup_path = backup_dir / backup_filename
        current_backup_abs = ""
        if picture.image_path and not Path(picture.image_path).is_absolute():
            current_backup_abs = self._resolve_managed_abs(picture.image_path, project_file_path)
        if backup_path.exists() and str(backup_path.resolve()) not in {current_backup_abs, str(source_path.resolve())}:
            backup_path = self.manager._ensure_unique_path(backup_path, picture.id)
        if source_path.resolve() != backup_path.resolve():
            self.manager._copy_file(source_path, backup_path)
        rel_path = backup_path.relative_to(self._rel_root(project_file_path))
        picture.image_path = rel_path.as_posix()

    def backup_source_file_for_project(
        self,
        source_file: SourceFileAsset,
        project_file_path: str,
        source_project: Optional[Project],
        target_folder_id: Optional[str] = None,
    ) -> None:
        origin_abs = self.manager.resolve_source_file_origin_path(source_file, source_project)
        source_abs = origin_abs if origin_abs and Path(origin_abs).exists() else self.manager.resolve_source_file_path(source_file, source_project)
        if not source_abs:
            return
        source_path = Path(source_abs)
        if not source_path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_abs}")
        backup_root = self.manager._project_assets_dir(project_file_path, "source_files")
        relative_subdir = self.manager._source_file_relative_subdir(source_file)
        if relative_subdir is not None:
            backup_dir = backup_root / relative_subdir
        elif target_folder_id and self.manager.current_project is not None and self.manager.current_project.file_path == project_file_path:
            folder_path = self.manager.resolve_source_file_folder_path(target_folder_id, create=True)
            backup_dir = Path(folder_path) if folder_path else backup_root
        else:
            backup_dir = backup_root
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_filename = self.manager._backup_filename(source_file, source_path.suffix)
        backup_path = backup_dir / backup_filename
        current_backup_abs = ""
        if source_file.file_path and not Path(source_file.file_path).is_absolute():
            current_backup_abs = self._resolve_managed_abs(source_file.file_path, project_file_path)
        if backup_path.exists() and str(backup_path.resolve()) not in {current_backup_abs, str(source_path.resolve())}:
            backup_path = self.manager._ensure_unique_path(backup_path, source_file.id)
        if source_path.resolve() != backup_path.resolve():
            self.manager._copy_file(source_path, backup_path)
        rel_path = backup_path.relative_to(self._rel_root(project_file_path))
        source_file.file_path = rel_path.as_posix()
        source_file.source_file_path = origin_abs or str(source_path)
        source_file.file_size = backup_path.stat().st_size

    def delete_backup_if_managed(self, asset: Any, project: Project, *, path_attr: str) -> None:
        if not project.file_path:
            return
        raw_path = str(getattr(asset, path_attr, "") or "")
        if not raw_path or Path(raw_path).is_absolute():
            return
        ws = self.manager._get_workspace(project)
        if ws is not None:
            backup_path = Path(ws.resolve(raw_path))
        else:
            backup_path = Path(project.file_path).parent / raw_path
        try:
            if backup_path.exists():
                backup_path.unlink()
        except OSError:
            pass
        if ws is not None:
            ws.remove(raw_path)
