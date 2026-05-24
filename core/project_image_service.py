"""
ProjectImageService — Image/Picture/SourceFile 的 CRUD 与备份管理。

从 ProjectManager 中提取，持有 project_manager 引用并通过
project_manager.current_project 获取当前项目。
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, cast, List, Optional, Set, Tuple, TYPE_CHECKING

from models.schemas import (
    ImageWork,
    ImageWorkNode,
    PictureAsset,
    PictureNode,
    PicturePlotSnapshot,
    SourceFileAsset,
    SourceFileNode,
    TreeNodeUnion,
    Project,
)

from core.project_name_rules import (
    ensure_non_empty_name as _ensure_non_empty_name_rule,
    ensure_unique_tree_child_name as _ensure_unique_tree_child_name_rule,
    has_tree_child_name_conflict as _has_tree_child_name_conflict_rule,
    next_unique_tree_child_name as _next_unique_tree_child_name_rule,
    normalize_name_key as _normalize_name_key_rule,
)

if TYPE_CHECKING:
    from core.project_manager import ProjectManager

from aline_metadata import CURRENT_PROJECT_VERSION

_ALINE_VERSION = CURRENT_PROJECT_VERSION
_PROJECT_FILE_SUFFIX = ".aline"

_GROUP_TYPE_ALIASES = {
    "datasets": {"datasets", "dataset_set"},
    "source_files": {"source_files"},
    "images": {"images", "image_set"},
    "pictures": {"pictures", "picture_set"},
    "tools": {"tools", "tool_set"},
    "pipeline_group": {"pipeline_group"},
    "template_group": {"template_group", "figure_template_group"},
    "figure_template_group": {"figure_template_group", "template_group"},
    "report_template_group": {"report_template_group"},
    "analysis_result_group": {"analysis_result_group"},
    "ai_group": {"ai_group"},
    "prompt_group": {"prompt_group"},
    "skill_group": {"skill_group"},
    "agent_group": {"agent_group"},
}

_GROUP_DISPLAY_NAMES = {
    "datasets": "数据集",
    "source_files": "源文件",
    "images": "数字化",
    "pictures": "图片集",
    "tools": "工具集",
    "pipeline_group": "Pipelines",
    "figure_template_group": "绘图模板组",
    "report_template_group": "报告模板组",
    "analysis_result_group": "分析结果",
    "ai_group": "AI 工具",
    "prompt_group": "Prompts",
    "skill_group": "Skills",
    "agent_group": "Agents",
}

_TOOL_NODE_PARENT_GROUP = {
    "pipeline": "pipeline_group",
    "figure_template": "figure_template_group",
    "report_template": "report_template_group",
    "ai_prompt": "prompt_group",
}

_NON_REMOVABLE_FOLDER_GROUP_TYPES = set(_GROUP_DISPLAY_NAMES.keys())

from models.schemas import _TREE_QUERY_ANY_PARENT  # noqa: E402


class ProjectImageService:
    """Image / Picture / SourceFile 的管理器。

    需要 project_manager.current_project 获取当前项目。
    初始化后绑定到 project_manager 实例。
    """

    def __init__(self, project_manager: "ProjectManager") -> None:
        self._pm = project_manager

    @property
    def _project(self) -> Any:
        return self._pm.current_project

    # ── 内部辅助 ──────────────────────────────────────────

    def _clear_last_operation_error(self) -> None:
        self._pm._last_operation_error = ""

    def _fail_operation(self, message: str) -> bool:
        self._pm._last_operation_error = message
        return False

    @staticmethod
    def _normalize_name_key(name: str) -> str:
        return _normalize_name_key_rule(name)

    def _ensure_non_empty_name(self, name: str, *, label: str = "名称") -> bool:
        ok, error = _ensure_non_empty_name_rule(name, label=label)
        if ok:
            return True
        return self._fail_operation(error or f"{label}不能为空")

    def _find_tree_linked_node(
        self,
        node_kind: str,
        attr_name: str,
        attr_value: str,
        project: Optional[Project] = None,
    ) -> Optional["TreeNodeUnion"]:
        p = project or self._pm.current_project
        if p is None or p.tree is None:
            return None
        return p.tree.find_linked_node(node_kind, attr_name, attr_value)

    def _ensure_unique_tree_child_name(
        self,
        parent_id: Optional[str],
        name: str,
        *,
        node_kind: Optional[str] = None,
        exclude_node_id: Optional[str] = None,
        project: Optional[Project] = None,
    ) -> bool:
        p = project or self._pm.current_project
        ok, error = _ensure_unique_tree_child_name_rule(
            p,
            parent_id,
            name,
            node_kind=node_kind,
            exclude_node_id=exclude_node_id,
        )
        if ok:
            return True
        return self._fail_operation(error or "名称冲突")

    def _has_tree_child_name_conflict(
        self,
        parent_id: Optional[str],
        name: str,
        *,
        node_kind: Optional[str] = None,
        exclude_node_id: Optional[str] = None,
        project: Optional[Project] = None,
    ) -> bool:
        p = project or self._pm.current_project
        return _has_tree_child_name_conflict_rule(
            p,
            parent_id,
            name,
            node_kind=node_kind,
            exclude_node_id=exclude_node_id,
        )

    def _next_unique_tree_child_name(
        self,
        parent_id: Optional[str],
        name: str,
        *,
        node_kind: Optional[str] = None,
        exclude_node_id: Optional[str] = None,
        project: Optional[Project] = None,
    ) -> str:
        candidate = (name or "").strip()
        p = project or self._pm.current_project
        return _next_unique_tree_child_name_rule(
            p,
            parent_id,
            candidate,
            node_kind=node_kind,
            exclude_node_id=exclude_node_id,
        )

    def _ensure_unique_series_name(
        self,
        owner_name: str,
        series_list: List[Any],
        name: str,
        *,
        owner_label: str,
        exclude_series_id: Optional[str] = None,
    ) -> bool:
        if not self._ensure_non_empty_name(name):
            return False
        normalized = self._normalize_name_key(name)
        for series in series_list:
            if exclude_series_id is not None and series.id == exclude_series_id:
                continue
            if self._normalize_name_key(series.name) == normalized:
                return self._fail_operation(
                    f"{owner_label}“{owner_name or '未命名'}”中已存在名为“{name.strip()}”的数据系列，请先重命名后再试。"
                )
        return True

    def _ensure_unique_curve_name(
        self,
        image_name: str,
        curves: List[Any],
        name: str,
        *,
        exclude_curve_id: Optional[str] = None,
    ) -> bool:
        if not self._ensure_non_empty_name(name):
            return False
        normalized = self._normalize_name_key(name)
        for curve in curves:
            if exclude_curve_id is not None and curve.id == exclude_curve_id:
                continue
            if self._normalize_name_key(curve.name) == normalized:
                return self._fail_operation(
                    f"图像“{image_name or '未命名'}”中已存在名为“{name.strip()}”的曲线，请先重命名后再试。"
                )
        return True

    # ── 树节点内部辅助 ─────────────────────────────────────

    def _find_folder_by_group_type(
        self,
        group_type: str,
        parent_id: Optional[str] = None,
    ) -> Optional[Any]:
        p = self._pm.current_project
        if p is None or p.tree is None:
            return None
        group_type = self._canonical_group_type(group_type) or group_type
        candidates = _GROUP_TYPE_ALIASES.get(group_type, {group_type})
        for node in p.tree.find_nodes(kind="folder", parent_id=parent_id):
            if node.kind == "folder" and getattr(node, "group_type", None) in candidates:
                return node
        return None

    def _canonical_group_type(self, group_type: Optional[str]) -> Optional[str]:
        if group_type is None:
            return None
        canonical_map = {
            "dataset_set": "datasets",
            "image_set": "images",
            "picture_set": "pictures",
            "tool_set": "tools",
            "template_group": "figure_template_group",
            "figure_template_group": "figure_template_group",
        }
        if group_type in canonical_map:
            return canonical_map[group_type]
        for canonical, aliases in _GROUP_TYPE_ALIASES.items():
            if group_type == canonical or group_type in aliases:
                return canonical
        return group_type

    # ── 路径 / 文件名辅助 ──────────────────────────────────

    @staticmethod
    def _normalize_path(path: str) -> str:
        return str(Path(path).expanduser().resolve())

    @staticmethod
    def _safe_filename(text: str) -> str:
        text = (text or "").strip() or "untitled"
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
        return sanitized.rstrip(". ") or "untitled"

    def _backup_filename(
        self,
        asset: Any,
        source_suffix: str,
    ) -> str:
        name = self._safe_filename(asset.name)
        p = Path(name)
        if p.suffix:
            return name
        suffix = (source_suffix or ".bin").lower()
        return f"{name}{suffix}"

    @staticmethod
    def _ensure_unique_path(candidate: Path, asset_id: str) -> Path:
        if not candidate.exists():
            return candidate
        stem, suffix = candidate.stem, candidate.suffix
        for idx in range(1, 1000):
            trial = candidate.with_name(f"{stem}_{idx}{suffix}")
            if not trial.exists():
                return trial
        return candidate.with_name(f"{stem}_{asset_id}{suffix}")

    @staticmethod
    def _copy_file(source_path: Path, backup_path: Path) -> None:
        shutil.copy2(source_path, backup_path)

    # ── 暂存区管理 ─────────────────────────────────────────

    def _get_workspace(self, project: Project) -> Any:
        return self._pm._binary_workspaces.get(project.id)

    def _ensure_workspace(self, project: Project) -> Any:
        ws = self._pm._binary_workspaces.get(project.id)
        if ws is not None:
            return ws
        from core.zip_binary_workspace import ZipBinaryWorkspace
        ws = ZipBinaryWorkspace(project.file_path or "")
        self._pm._binary_workspaces[project.id] = ws
        return ws

    def _project_assets_dir(self, project_file_path: str, folder_name: str = "images") -> Path:
        for p in self._pm._projects:
            if p.file_path and Path(p.file_path).resolve() == Path(project_file_path).resolve():
                ws = self._get_workspace(p)
                if ws is not None:
                    return ws.temp_dir / "files" / folder_name
                break
        return Path(project_file_path).parent / "files" / folder_name

    # ── 上级查询 ───────────────────────────────────────────

    def _get_image_owner(
        self,
        image_id: str,
    ) -> Tuple[Optional[Project], Optional[ImageWork]]:
        for project in self._pm._projects:
            for image in project.images:
                if image.id == image_id:
                    return project, image
        return None, None

    def _get_picture_owner(
        self,
        picture_id: str,
    ) -> Tuple[Optional[Project], Optional[PictureAsset]]:
        for project in self._pm._projects:
            for picture in project.pictures:
                if picture.id == picture_id:
                    return project, picture
        return None, None

    def _get_source_file_owner(
        self,
        source_file_id: str,
    ) -> Tuple[Optional[Project], Optional[SourceFileAsset]]:
        for project in self._pm._projects:
            for source_file in project.source_files:
                if source_file.id == source_file_id:
                    return project, source_file
        return None, None

    # ── 备份方法（委托给 backup_manager） ─────────────────

    def _backup_image_for_project(
        self,
        image: ImageWork,
        project_file_path: str,
        source_project: Optional[Project],
    ) -> None:
        self._pm._project_backup_manager.backup_image_for_project(
            image, project_file_path, source_project,
        )

    def _backup_picture_for_project(
        self,
        picture: PictureAsset,
        project_file_path: str,
        source_project: Optional[Project],
        target_folder_id: Optional[str] = None,
    ) -> None:
        self._pm._project_backup_manager.backup_picture_for_project(
            picture,
            project_file_path,
            source_project,
            target_folder_id=target_folder_id,
        )

    def _backup_source_file_for_project(
        self,
        source_file: SourceFileAsset,
        project_file_path: str,
        source_project: Optional[Project],
        target_folder_id: Optional[str] = None,
    ) -> None:
        self._pm._project_backup_manager.backup_source_file_for_project(
            source_file,
            project_file_path,
            source_project,
            target_folder_id=target_folder_id,
        )

    def _delete_backup_if_managed(
        self,
        image: ImageWork,
        project: Project,
    ) -> None:
        self._pm._project_backup_manager.delete_backup_if_managed(
            image, project, path_attr="image_path",
        )

    def _delete_picture_backup_if_managed(
        self,
        picture: PictureAsset,
        project: Project,
    ) -> None:
        self._pm._project_backup_manager.delete_backup_if_managed(
            picture, project, path_attr="image_path",
        )

    def _delete_source_file_backup_if_managed(
        self,
        source_file: SourceFileAsset,
        project: Project,
    ) -> None:
        self._pm._project_backup_manager.delete_backup_if_managed(
            source_file, project, path_attr="file_path",
        )

    # ── 相对路径辅助 ──────────────────────────────────────

    @staticmethod
    def _picture_relative_subdir(picture: PictureAsset) -> Optional[Path]:
        raw_path = picture.image_path or ""
        if not raw_path or Path(raw_path).is_absolute():
            return None
        parts = Path(raw_path).parts
        if len(parts) >= 3 and parts[0] == "files" and parts[1] == "pictures":
            return Path(*parts[2:-1]) if len(parts) > 3 else Path()
        return None

    @staticmethod
    def _source_file_relative_subdir(source_file: SourceFileAsset) -> Optional[Path]:
        raw_path = source_file.file_path or ""
        if not raw_path or Path(raw_path).is_absolute():
            return None
        parts = Path(raw_path).parts
        if len(parts) >= 3 and parts[0] == "files" and parts[1] == "source_files":
            return Path(*parts[2:-1]) if len(parts) > 3 else Path()
        return None

    # ── 空目录清理 ────────────────────────────────────────

    @staticmethod
    def _remove_empty_directories(
        root_dir: Path,
        exclude: Optional[Set[Path]] = None,
    ) -> None:
        if not root_dir.exists():
            return
        for child in sorted(root_dir.rglob("*"), reverse=True):
            if not child.is_dir():
                continue
            if exclude is not None and child in exclude:
                continue
            try:
                next(child.iterdir())
            except StopIteration:
                try:
                    child.rmdir()
                except OSError:
                    pass
            except OSError:
                continue

    # ── 空文件夹路径收集 ──────────────────────────────────

    def _get_empty_binary_folder_paths(self, project: Project) -> Set[str]:
        if project.tree is None:
            return set()
        group_roots: dict[str, str] = {}
        for node in project.tree.nodes:
            if node.kind != "folder" or node.parent_id is not None:
                continue
            gt: Optional[str] = getattr(node, "group_type", None)
            if gt is None:
                continue
            canonical = self._canonical_group_type(gt)
            if canonical == "source_files":
                group_roots[node.id] = "files/source_files/"
            elif canonical == "pictures":
                group_roots[node.id] = "files/pictures/"
            elif canonical == "images":
                group_roots[node.id] = "files/images/"
        if not group_roots:
            return set()
        file_dirs: Set[str] = set()
        for sf in project.source_files:
            p = sf.file_path or ""
            if p and not Path(p).is_absolute():
                file_dirs.add(str(Path(p).parent).replace("\\", "/") + "/")
        for img in project.images:
            p = img.image_path or ""
            if p and not Path(p).is_absolute():
                file_dirs.add(str(Path(p).parent).replace("\\", "/") + "/")
        for pic in project.pictures:
            p = pic.image_path or ""
            if p and not Path(p).is_absolute():
                file_dirs.add(str(Path(p).parent).replace("\\", "/") + "/")
        empty: Set[str] = set()
        for node in project.tree.nodes:
            if node.kind != "folder":
                continue
            if node.id in group_roots:
                continue
            current_id = node.parent_id
            parent_root_id: Optional[str] = None
            while current_id:
                cur_node = project.tree.get_node(current_id)
                if cur_node is None:
                    break
                if cur_node.id in group_roots:
                    parent_root_id = cur_node.id
                    break
                current_id = cur_node.parent_id
            if parent_root_id is None:
                continue
            prefix = group_roots[parent_root_id]
            parts: List[str] = []
            cur = node
            while cur is not None and cur.kind == "folder" and cur.id != parent_root_id:
                parts.append(self._safe_filename(cur.name))
                cur = project.tree.get_node(cur.parent_id) if cur.parent_id else None
            if not parts:
                continue
            folder_rel = prefix + "/".join(reversed(parts)) + "/"
            if not any(f.startswith(folder_rel) for f in file_dirs):
                empty.add(folder_rel)
        return empty

    # ── 存储同步 ──────────────────────────────────────────

    def _sync_picture_storage(self) -> None:
        p = self._pm.current_project
        if p is None or p.tree is None or not p.file_path:
            return
        base_dir = self._project_assets_dir(p.file_path, "pictures")
        base_dir.mkdir(parents=True, exist_ok=True)
        ws = self._get_workspace(p)
        project_root = ws.temp_dir if ws is not None else Path(p.file_path).parent
        for node in [item for item in p.tree.nodes if item.kind == "picture"]:
            picture = p.find_picture(node.picture_id)
            if picture is None:
                continue
            current_path_str = self.resolve_picture_path(picture, p)
            if not current_path_str:
                continue
            current_path = Path(current_path_str)
            if not current_path.exists():
                continue
            target_folder = self.resolve_picture_folder_path(node.id, create=True)
            if not target_folder:
                continue
            target_dir = Path(target_folder)
            target_name = self._backup_filename(
                picture,
                current_path.suffix or Path(picture.name).suffix,
            )
            target_path = target_dir / target_name
            if target_path.exists() and target_path.resolve() != current_path.resolve():
                target_path = self._ensure_unique_path(target_path, picture.id)
            if current_path.resolve() != target_path.resolve():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if ws is not None:
                    try:
                        old_rel = str(current_path.relative_to(ws.temp_dir))
                        new_rel = str(target_path.relative_to(ws.temp_dir))
                        ws.move(old_rel, new_rel)
                    except ValueError:
                        shutil.move(str(current_path), str(target_path))
                else:
                    shutil.move(str(current_path), str(target_path))
            try:
                picture.image_path = target_path.relative_to(project_root).as_posix()
            except Exception:
                picture.image_path = str(target_path)
        exclude_dirs: Set[Path] = set()
        for node in p.tree.nodes:
            if node.kind == "folder":
                folder_path_str = self.resolve_picture_folder_path(node.id, create=False)
                if folder_path_str and Path(folder_path_str) != base_dir:
                    exclude_dirs.add(Path(folder_path_str))
        self._remove_empty_directories(base_dir, exclude_dirs)

    def _sync_source_file_storage(self) -> None:
        p = self._pm.current_project
        if p is None or p.tree is None or not p.file_path:
            return
        base_dir = self._project_assets_dir(p.file_path, "source_files")
        base_dir.mkdir(parents=True, exist_ok=True)
        ws = self._get_workspace(p)
        project_root = ws.temp_dir if ws is not None else Path(p.file_path).parent
        for node in [item for item in p.tree.nodes if item.kind == "source_file"]:
            source_file = p.find_source_file(node.source_file_id)
            if source_file is None:
                continue
            current_path_str = self.resolve_source_file_path(source_file, p)
            if not current_path_str:
                continue
            current_path = Path(current_path_str)
            if not current_path.exists():
                continue
            target_folder = self.resolve_source_file_folder_path(node.id, create=True)
            if not target_folder:
                continue
            target_dir = Path(target_folder)
            target_name = self._backup_filename(
                source_file,
                current_path.suffix or Path(source_file.name).suffix,
            )
            target_path = target_dir / target_name
            if target_path.exists() and target_path.resolve() != current_path.resolve():
                target_path = self._ensure_unique_path(target_path, source_file.id)
            if current_path.resolve() != target_path.resolve():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if ws is not None:
                    try:
                        old_rel = str(current_path.relative_to(ws.temp_dir))
                        new_rel = str(target_path.relative_to(ws.temp_dir))
                        ws.move(old_rel, new_rel)
                    except ValueError:
                        shutil.move(str(current_path), str(target_path))
                else:
                    shutil.move(str(current_path), str(target_path))
            try:
                source_file.file_path = target_path.relative_to(project_root).as_posix()
            except Exception:
                source_file.file_path = str(target_path)
            if target_path.exists():
                source_file.file_size = target_path.stat().st_size
        exclude_dirs: Set[Path] = set()
        for node in p.tree.nodes:
            if node.kind == "folder":
                folder_path_str = self.resolve_source_file_folder_path(node.id, create=False)
                if folder_path_str and Path(folder_path_str) != base_dir:
                    exclude_dirs.add(Path(folder_path_str))
        self._remove_empty_directories(base_dir, exclude_dirs)

    def _sync_project_backups(
        self,
        project: Project,
        target_file_path: str,
        source_file_path: Optional[str],
    ) -> None:
        source_project = project.model_copy(deep=False)
        source_project.file_path = source_file_path
        for source_file in project.source_files:
            self._backup_source_file_for_project(
                source_file, target_file_path, source_project,
            )
        for image in project.images:
            self._backup_image_for_project(image, target_file_path, source_project)
        for picture in project.pictures:
            self._backup_picture_for_project(
                picture, target_file_path, source_project,
            )

    # ─────────────────────────────────────────────
    # Image CRUD
    # ─────────────────────────────────────────────

    def add_image(
        self,
        image_path: str,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
    ) -> ImageWork:
        self._clear_last_operation_error()
        if self._pm.current_project is None:
            raise ValueError("没有当前项目")
        image_path = self._normalize_path(image_path)
        if self._pm.current_project.tree is None:
            self._pm.migrate_to_v2(self._pm.current_project)
        self._pm._ensure_project_tree_groups(self._pm.current_project)
        if parent_id is None:
            img_folder = self._find_folder_by_group_type("images")
            parent_id = img_folder.id if img_folder else None
        image_name = name or os.path.basename(image_path)
        if not self._ensure_unique_tree_child_name(
            parent_id,
            image_name,
            node_kind="image_work",
            project=self._pm.current_project,
        ):
            raise ValueError(self._pm.get_last_error_message())
        image_work = ImageWork(
            id=str(uuid.uuid4()),
            name=image_name,
            image_path=image_path,
            source_image_path=image_path,
        )
        if self._pm.current_project.file_path:
            self._backup_image_for_project(
                image_work,
                self._pm.current_project.file_path,
                None,
            )
        self._pm.current_project.images.append(image_work)
        self._pm.current_project.is_modified = True
        if self._pm.current_project.tree is not None:
            order = self._pm.current_project.tree.get_siblings_max_order(parent_id) + 1
            img_node = ImageWorkNode(
                name=image_work.name,
                parent_id=parent_id,
                image_work_id=image_work.id,
                order=order,
            )
            self._pm.current_project.tree.nodes.append(img_node)
        return image_work

    def get_image(self, image_id: str) -> Optional[ImageWork]:
        if self._pm.current_project is None:
            return None
        for img in self._pm.current_project.images:
            if img.id == image_id:
                return img
        return None

    def remove_image(self, image_id: str) -> Optional[ImageWork]:
        project, image = self._get_image_owner(image_id)
        if project is None or image is None:
            return None
        self._delete_backup_if_managed(image, project)
        project.images = [i for i in project.images if i.id != image_id]
        project.is_modified = True
        return image

    def rename_image(self, image_id: str, new_name: str) -> bool:
        self._clear_last_operation_error()
        project, image = self._get_image_owner(image_id)
        if project is None or image is None:
            return False
        image_node = self._find_tree_linked_node(
            "image_work", "image_work_id", image_id, project,
        )
        if not self._ensure_unique_tree_child_name(
            image_node.parent_id if image_node is not None else None,
            new_name,
            node_kind="image_work",
            exclude_node_id=image_node.id if image_node is not None else None,
            project=project,
        ):
            return False
        old_name = image.name
        image.name = new_name
        if not project.file_path:
            project.is_modified = True
            return True
        raw_path = image.image_path or ""
        if not raw_path or Path(raw_path).is_absolute():
            project.is_modified = True
            return True
        old_path_str = self.resolve_image_path(image, project)
        if not old_path_str:
            project.is_modified = True
            return True
        old_path = Path(old_path_str)
        if not old_path.exists():
            project.is_modified = True
            return True
        new_filename = self._backup_filename(image, old_path.suffix)
        new_path = old_path.with_name(new_filename)
        if new_path.exists() and new_path.resolve() != old_path.resolve():
            new_path = self._ensure_unique_path(new_path, image.id)
        try:
            old_path.rename(new_path)
            ws = self._get_workspace(project)
            if ws is not None and raw_path:
                ws.remove(raw_path)
            if ws is not None:
                rel = new_path.relative_to(ws.temp_dir)
            else:
                rel = new_path.relative_to(Path(project.file_path).parent)
            image.image_path = rel.as_posix()
        except OSError:
            image.name = old_name
            self._fail_operation(f"图像“{old_name}”重命名失败")
            return False
        project.is_modified = True
        return True

    def move_image(self, image_id: str, dest_project_id: str) -> bool:
        src_project, image = self._get_image_owner(image_id)
        dest_project = self._pm.get_project(dest_project_id)
        if src_project is None or image is None or dest_project is None:
            return False
        if src_project.id == dest_project_id:
            return False
        image.image_path = self.resolve_image_path(image, src_project)
        src_project.images = [i for i in src_project.images if i.id != image_id]
        dest_project.images.append(image)
        src_project.is_modified = True
        dest_project.is_modified = True
        return True

    def resolve_image_path(
        self,
        image: ImageWork,
        project: Optional[Project] = None,
    ) -> str:
        raw_path = image.image_path or image.source_image_path or ""
        if not raw_path:
            return ""
        path = Path(raw_path)
        if path.is_absolute():
            return str(path)
        owner = project
        if owner is None:
            owner, _ = self._get_image_owner(image.id)
        if owner is None:
            return str(path)
        ws = self._get_workspace(owner)
        if ws is not None:
            return ws.resolve(raw_path)
        if owner.file_path:
            return str((Path(owner.file_path).parent / path).resolve())
        return str(path)

    def get_image_path(self, image_id: str) -> str:
        project, image = self._get_image_owner(image_id)
        if image is None:
            return ""
        return self.resolve_image_path(image, project)

    # ─────────────────────────────────────────────
    # Picture CRUD
    # ─────────────────────────────────────────────

    def add_picture(
        self,
        image_path: str,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
        *,
        plot_snapshot: Optional[PicturePlotSnapshot] = None,
    ) -> Optional[PictureNode]:
        self._clear_last_operation_error()
        p = self._pm.current_project
        if p is None:
            return None
        image_path = self._normalize_path(image_path)
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        if p.tree is None:
            self._pm.migrate_to_v2(p)
        self._pm._ensure_project_tree_groups(p)
        if parent_id is None:
            picture_folder = self._find_folder_by_group_type("pictures")
            parent_id = picture_folder.id if picture_folder else None
        picture_name = name or os.path.basename(image_path)
        if not self._ensure_unique_tree_child_name(
            parent_id, picture_name, node_kind="picture", project=p,
        ):
            return None
        picture = PictureAsset(
            id=str(uuid.uuid4()),
            name=picture_name,
            image_path=image_path,
            plot_snapshot=plot_snapshot.model_copy(deep=True)
            if plot_snapshot is not None
            else None,
        )
        if p.file_path:
            self._backup_picture_for_project(
                picture, p.file_path, None, target_folder_id=parent_id,
            )
        p.pictures.append(picture)
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore[union-attr]
        node = PictureNode(
            name=picture.name, parent_id=parent_id, picture_id=picture.id, order=order,
        )
        p.tree.nodes.append(node)  # type: ignore[union-attr]
        p.is_modified = True
        return node

    def get_picture(self, picture_id: str) -> Optional[PictureAsset]:
        if self._pm.current_project is None:
            return None
        return self._pm.current_project.find_picture(picture_id)

    def remove_picture(self, picture_id: str) -> Optional[PictureAsset]:
        project, picture = self._get_picture_owner(picture_id)
        if project is None or picture is None:
            return None
        self._delete_picture_backup_if_managed(picture, project)
        project.pictures = [
            item for item in project.pictures if item.id != picture_id
        ]
        project.is_modified = True
        return picture

    def rename_picture(self, picture_id: str, new_name: str) -> bool:
        self._clear_last_operation_error()
        project, picture = self._get_picture_owner(picture_id)
        if project is None or picture is None:
            return False
        picture_node = self._find_tree_linked_node(
            "picture", "picture_id", picture_id, project,
        )
        if not self._ensure_unique_tree_child_name(
            picture_node.parent_id if picture_node is not None else None,
            new_name,
            node_kind="picture",
            exclude_node_id=picture_node.id if picture_node is not None else None,
            project=project,
        ):
            return False
        old_name = picture.name
        picture.name = new_name
        if not project.file_path:
            project.is_modified = True
            return True
        raw_path = picture.image_path or ""
        if not raw_path:
            project.is_modified = True
            return True
        picture_path = Path(raw_path)
        if picture_path.is_absolute():
            old_path = picture_path
        else:
            old_path_str = self.resolve_picture_path(picture, project)
            if not old_path_str:
                project.is_modified = True
                return True
            old_path = Path(old_path_str)
        if not old_path.exists():
            project.is_modified = True
            return True
        new_filename = self._backup_filename(picture, old_path.suffix)
        new_path = old_path.with_name(new_filename)
        if new_path.exists() and new_path.resolve() != old_path.resolve():
            new_path = self._ensure_unique_path(new_path, picture.id)
        try:
            old_path.rename(new_path)
            try:
                ws = self._get_workspace(project)
                if ws is not None and raw_path:
                    ws.remove(raw_path)
                if ws is not None:
                    rel = new_path.relative_to(ws.temp_dir)
                else:
                    rel = new_path.relative_to(Path(project.file_path).parent)
                picture.image_path = rel.as_posix()
            except Exception:
                picture.image_path = str(new_path)
        except OSError:
            picture.name = old_name
            self._fail_operation(f"图片“{old_name}”重命名失败")
            return False
        project.is_modified = True
        return True

    def resolve_picture_path(
        self,
        picture: PictureAsset,
        project: Optional[Project] = None,
    ) -> str:
        raw_path = picture.image_path or ""
        if not raw_path:
            return ""
        path = Path(raw_path)
        if path.is_absolute():
            return str(path)
        owner = project
        if owner is None:
            owner, _ = self._get_picture_owner(picture.id)
        if owner is None:
            return str(path)
        ws = self._get_workspace(owner)
        if ws is not None:
            return ws.resolve(raw_path)
        if owner.file_path:
            return str((Path(owner.file_path).parent / path).resolve())
        return str(path)

    def get_picture_path(self, picture_id: str) -> str:
        project, picture = self._get_picture_owner(picture_id)
        if picture is None:
            return ""
        return self.resolve_picture_path(picture, project)

    def prepare_picture_export_path(
        self,
        name: str,
        suffix: str = ".png",
        target_node_id: Optional[str] = None,
    ) -> str:
        folder_path = self.resolve_picture_folder_path(
            target_node_id, create=True,
        )
        if not folder_path:
            return ""
        safe_name = self._safe_filename(name or "chart")
        candidate = Path(folder_path) / safe_name
        if candidate.suffix.lower() != suffix.lower():
            candidate = candidate.with_suffix(suffix)
        return str(self._ensure_unique_path(candidate, str(uuid.uuid4())))

    # ─────────────────────────────────────────────
    # SourceFile CRUD
    # ─────────────────────────────────────────────

    def add_source_file(
        self,
        file_path: str,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
        *,
        auto_rename_on_conflict: bool = False,
    ) -> Optional[SourceFileNode]:
        self._clear_last_operation_error()
        p = self._pm.current_project
        if p is None:
            self._pm._last_operation_error = "没有当前项目"
            return None
        normalized_path = self._normalize_path(file_path)
        if not os.path.exists(normalized_path):
            raise FileNotFoundError(f"源文件不存在: {normalized_path}")
        if p.tree is None:
            self._pm.migrate_to_v2(p)
        self._pm._ensure_project_tree_groups(p)
        if parent_id is None:
            source_root = self._find_folder_by_group_type("source_files")
            parent_id = source_root.id if source_root else None
        source_path = Path(normalized_path)
        source_name = name or source_path.name
        if auto_rename_on_conflict:
            source_name = self._next_unique_tree_child_name(
                parent_id,
                source_name,
                node_kind="source_file",
                project=p,
            )
        if not self._ensure_unique_tree_child_name(
            parent_id, source_name, node_kind="source_file", project=p,
        ):
            return None
        asset = SourceFileAsset(
            id=str(uuid.uuid4()),
            name=source_name,
            file_path=normalized_path,
            source_file_path=normalized_path,
            file_size=source_path.stat().st_size,
        )
        if p.file_path:
            self._backup_source_file_for_project(
                asset, p.file_path, None, target_folder_id=parent_id,
            )
        p.source_files.append(asset)
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore[union-attr]
        node = SourceFileNode(
            name=asset.name, parent_id=parent_id, source_file_id=asset.id, order=order,
        )
        p.tree.nodes.append(node)  # type: ignore[union-attr]
        p.is_modified = True
        return node

    def add_source_files(
        self,
        file_paths: List[str],
        parent_id: Optional[str] = None,
        *,
        auto_rename_on_conflict: bool = False,
    ) -> List[SourceFileNode]:
        nodes: List[SourceFileNode] = []
        for file_path in file_paths:
            node = self.add_source_file(
                file_path,
                parent_id=parent_id,
                auto_rename_on_conflict=auto_rename_on_conflict,
            )
            if node is not None:
                nodes.append(node)
        return nodes

    def get_source_file(self, source_file_id: str) -> Optional[SourceFileAsset]:
        if self._pm.current_project is None:
            return None
        return self._pm.current_project.find_source_file(source_file_id)

    def remove_source_file(
        self,
        source_file_id: str,
    ) -> Optional[SourceFileAsset]:
        project, source_file = self._get_source_file_owner(source_file_id)
        if project is None or source_file is None:
            return None
        self._delete_source_file_backup_if_managed(source_file, project)
        project.source_files = [
            item for item in project.source_files if item.id != source_file_id
        ]
        project.is_modified = True
        return source_file

    def rename_source_file(self, source_file_id: str, new_name: str) -> bool:
        self._clear_last_operation_error()
        project, source_file = self._get_source_file_owner(source_file_id)
        if project is None or source_file is None:
            return False
        source_node = self._find_tree_linked_node(
            "source_file", "source_file_id", source_file_id, project,
        )
        if not self._ensure_unique_tree_child_name(
            source_node.parent_id if source_node is not None else None,
            new_name,
            node_kind="source_file",
            exclude_node_id=source_node.id if source_node is not None else None,
            project=project,
        ):
            return False
        old_name = source_file.name
        source_file.name = new_name
        if not project.file_path:
            project.is_modified = True
            return True
        raw_path = source_file.file_path or ""
        if not raw_path or Path(raw_path).is_absolute():
            project.is_modified = True
            return True
        old_path_str = self.resolve_source_file_path(source_file, project)
        if not old_path_str:
            project.is_modified = True
            return True
        old_path = Path(old_path_str)
        if not old_path.exists():
            project.is_modified = True
            return True
        new_filename = self._backup_filename(source_file, old_path.suffix)
        new_path = old_path.with_name(new_filename)
        if new_path.exists() and new_path.resolve() != old_path.resolve():
            new_path = self._ensure_unique_path(new_path, source_file.id)
        try:
            old_path.rename(new_path)
            ws = self._get_workspace(project)
            if ws is not None and raw_path:
                ws.remove(raw_path)
            if ws is not None:
                rel = new_path.relative_to(ws.temp_dir)
            else:
                rel = new_path.relative_to(Path(project.file_path).parent)
            source_file.file_path = rel.as_posix()
        except OSError:
            source_file.name = old_name
            self._fail_operation(f"源文件“{old_name}”重命名失败")
            return False
        project.is_modified = True
        return True

    def resolve_source_file_path(
        self,
        source_file: SourceFileAsset,
        project: Optional[Project] = None,
    ) -> str:
        raw_path = source_file.file_path or source_file.source_file_path or ""
        if not raw_path:
            return ""
        path = Path(raw_path)
        if path.is_absolute():
            return str(path)
        owner = project
        if owner is None:
            owner, _ = self._get_source_file_owner(source_file.id)
        if owner is None:
            return str(path)
        ws = self._get_workspace(owner)
        if ws is not None:
            return ws.resolve(raw_path)
        if owner.file_path:
            return str((Path(owner.file_path).parent / path).resolve())
        return str(path)

    def resolve_source_file_origin_path(
        self,
        source_file: SourceFileAsset,
        project: Optional[Project] = None,
    ) -> str:
        raw_path = source_file.source_file_path or source_file.file_path or ""
        if not raw_path:
            return ""
        path = Path(raw_path)
        if path.is_absolute():
            return str(path)
        owner = project
        if owner is None:
            owner, _ = self._get_source_file_owner(source_file.id)
        if owner is None:
            return str(path)
        ws = self._get_workspace(owner)
        if ws is not None:
            return ws.resolve(raw_path)
        if owner.file_path:
            return str((Path(owner.file_path).parent / path).resolve())
        return str(path)

    def get_source_file_path(self, source_file_id: str) -> str:
        project, source_file = self._get_source_file_owner(source_file_id)
        if source_file is None:
            return ""
        return self.resolve_source_file_path(source_file, project)

    # ─────────────────────────────────────────────
    # Target folder helpers
    # ─────────────────────────────────────────────

    def get_source_file_target_folder_id(
        self,
        node_id: Optional[str] = None,
    ) -> Optional[str]:
        p = self._pm.current_project
        if p is None or p.tree is None:
            return None
        source_root = self._find_folder_by_group_type("source_files")
        if source_root is None:
            return None
        if not node_id:
            return source_root.id
        node = p.tree.get_node(node_id)
        if node is None:
            return source_root.id
        if node.kind == "source_file":
            return node.parent_id or source_root.id
        if (
            node.kind == "folder"
            and self._canonical_group_type(getattr(node, "group_type", None))
            == "source_files"
        ):
            return node.id
        return source_root.id

    def resolve_source_file_folder_path(
        self,
        node_id: Optional[str] = None,
        create: bool = False,
    ) -> str:
        p = self._pm.current_project
        if p is None or p.tree is None or not p.file_path:
            return ""
        source_root = self._find_folder_by_group_type("source_files")
        if source_root is None:
            return ""
        target_folder_id = self.get_source_file_target_folder_id(node_id)
        base_dir = self._project_assets_dir(p.file_path, "source_files")
        parts: List[str] = []
        current = p.tree.get_node(target_folder_id) if target_folder_id else None
        while (
            current is not None
            and current.kind == "folder"
            and current.id != source_root.id
        ):
            parts.append(self._safe_filename(current.name))
            parent_id = getattr(current, "parent_id", None)
            current = p.tree.get_node(parent_id) if parent_id else None
        folder_path = base_dir.joinpath(*reversed(parts)) if parts else base_dir
        if create:
            folder_path.mkdir(parents=True, exist_ok=True)
        return str(folder_path)

    def get_picture_target_folder_id(
        self,
        node_id: Optional[str] = None,
    ) -> Optional[str]:
        p = self._pm.current_project
        if p is None or p.tree is None:
            return None
        pictures_root = self._find_folder_by_group_type("pictures")
        if pictures_root is None:
            return None
        if not node_id:
            return pictures_root.id
        node = p.tree.get_node(node_id)
        if node is None:
            return pictures_root.id
        if node.kind == "picture":
            return node.parent_id or pictures_root.id
        if (
            node.kind == "folder"
            and self._canonical_group_type(getattr(node, "group_type", None))
            == "pictures"
        ):
            return node.id
        return pictures_root.id

    def get_analysis_result_target_folder_id(
        self,
        node_id: Optional[str] = None,
    ) -> Optional[str]:
        p = self._pm.current_project
        if p is None or p.tree is None:
            return None
        analysis_root = self._find_folder_by_group_type("analysis_result_group")
        if analysis_root is None:
            return None
        if not node_id:
            return analysis_root.id
        node = p.tree.get_node(node_id)
        if node is None:
            return analysis_root.id
        if node.kind == "analysis_result":
            return node.parent_id or analysis_root.id
        if node.kind != "folder":
            return analysis_root.id

        current: Optional[TreeNodeUnion] = node
        while current is not None:
            if current.id == analysis_root.id:
                return node.id
            parent_id = getattr(current, "parent_id", None)
            current = p.tree.get_node(parent_id) if parent_id else None
        return analysis_root.id

    def resolve_picture_folder_path(
        self,
        node_id: Optional[str] = None,
        create: bool = False,
    ) -> str:
        p = self._pm.current_project
        if p is None or p.tree is None or not p.file_path:
            return ""
        pictures_root = self._find_folder_by_group_type("pictures")
        if pictures_root is None:
            return ""
        target_folder_id = self.get_picture_target_folder_id(node_id)
        base_dir = self._project_assets_dir(p.file_path, "pictures")
        parts: List[str] = []
        current = p.tree.get_node(target_folder_id) if target_folder_id else None
        while (
            current is not None
            and current.kind == "folder"
            and current.id != pictures_root.id
        ):
            parts.append(self._safe_filename(current.name))
            parent_id = getattr(current, "parent_id", None)
            current = p.tree.get_node(parent_id) if parent_id else None
        folder_path = base_dir.joinpath(*reversed(parts)) if parts else base_dir
        if create:
            folder_path.mkdir(parents=True, exist_ok=True)
        return str(folder_path)
