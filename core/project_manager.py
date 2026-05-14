"""
项目管理器 — 管理多项目打开、保存、CRUD 操作。
"""
from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, List, Optional, Tuple, cast

from aline_metadata import CURRENT_PROJECT_VERSION
from core.analysis_manager import AnalysisManager
from core.data_file_manager import DataFileManager
from core.project_serializer import ProjectSerializer
from core.tree_manager import TreeManager
from core.global_assets import global_assets
from core.project_name_rules import (
    ensure_non_empty_name as _ensure_non_empty_name_rule,
    ensure_unique_tree_child_name as _ensure_unique_tree_child_name_rule,
    has_tree_child_name_conflict as _has_tree_child_name_conflict_rule,
    next_unique_tree_child_name as _next_unique_tree_child_name_rule,
    split_name_suffix as _split_name_suffix_rule,
    normalize_name_key as _normalize_name_key_rule,
)
from core.project_session import ProjectSession
from core.project_services import build_project_services
from models.schemas import (
    AnalysisResult,
    AnalysisResultNode,
    CalibrationData,
    Curve,
    Dataset,
    DataFile,
    DataSeries,
    FigureConfig,
    FolderNode,
    DataFileNode,
    SourceFileAsset,
    SourceFileNode,
    ImageWorkNode,
    PipelineNode,
    FigureTemplateNode,
    ReportTemplateNode,
    AIToolNode,
    AIPromptNode,
    AISkillNode,
    AIAgentNode,
    ProjectTree,
    SavedPipeline,
    ReportTemplate,
    AIPrompt,
    AISkill,
    AIAgent,
    ImageWork,
    PictureAsset,
    PicturePlotSnapshot,
    PictureNode,
    TreeNodeUnion,
    Project,
)

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
    "ai_skill": "skill_group",
    "ai_agent": "agent_group",
}

_NON_REMOVABLE_FOLDER_GROUP_TYPES = set(_GROUP_DISPLAY_NAMES.keys())


class ProjectManager:
    """项目管理器（全局单例）。

    支持多项目同时打开，维护当前项目概念。
    """

    def __init__(self) -> None:
        self._projects: List[Project] = []
        self._current_project_id: Optional[str] = None
        self._last_operation_error: str = ""
        services = build_project_services(
            self,
            project_file_suffix=_PROJECT_FILE_SUFFIX,
            aline_version=_ALINE_VERSION,
        )
        self._project_repository = services.repository
        self._project_tree_init_service = services.tree_init_service
        self._project_backup_manager = services.backup_manager
        self._project_tree_service = services.tree_service
        self._project_asset_service = services.asset_service
        self._project_session = services.session

        self._serializer = ProjectSerializer(
            aline_version=_ALINE_VERSION,
        )
        self._tree_manager = TreeManager()
        self._data_file_manager = DataFileManager(self)
        self._analysis_manager = AnalysisManager(self)

    def get_last_error_message(self) -> str:
        return self._last_operation_error

    def _clear_last_operation_error(self) -> None:
        self._last_operation_error = ""

    def _fail_operation(self, message: str) -> bool:
        self._last_operation_error = message
        return False

    @staticmethod
    def _normalize_name_key(name: str) -> str:
        return _normalize_name_key_rule(name)

    @staticmethod
    def normalize_name_key(name: str) -> str:
        """Public facade: 标准化名称用于比较（去除空格、统一大小写）。"""
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
        p = project or self.current_project
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
        p = project or self.current_project
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
        p = project or self.current_project
        return _has_tree_child_name_conflict_rule(
            p,
            parent_id,
            name,
            node_kind=node_kind,
            exclude_node_id=exclude_node_id,
        )

    @staticmethod
    def _split_name_suffix(name: str) -> tuple[str, str]:
        return _split_name_suffix_rule(name)

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
        p = project or self.current_project
        return _next_unique_tree_child_name_rule(
            p,
            parent_id,
            candidate,
            node_kind=node_kind,
            exclude_node_id=exclude_node_id,
        )

    def format_tree_path_label(
        self,
        node_id: str,
        *,
        separator: str = " / ",
        omit_root_group: bool = False,
    ) -> str:
        p = self.current_project
        if p is None or p.tree is None:
            return node_id
        parts: List[str] = []
        current = p.tree.get_node(node_id)
        while current is not None:
            name = (getattr(current, "name", "") or "").strip()
            parent_id = getattr(current, "parent_id", None)
            canonical_group = self._canonical_group_type(getattr(current, "group_type", None))
            is_group_root = getattr(current, "kind", None) == "folder" and parent_id is None and canonical_group is not None
            if not (omit_root_group and is_group_root):
                parts.append(name)
            current = p.tree.get_node(parent_id) if parent_id else None
        labels = [part for part in reversed(parts) if part]
        return separator.join(labels) if labels else node_id

    def format_series_origin_path_label(
        self,
        series_id: str,
        *,
        separator: str = " / ",
        omit_root_group: bool = False,
    ) -> str:
        owner_kind, owner, series = self._find_series_owner(series_id)
        if owner_kind == "data_file" and owner is not None and series is not None:
            node = self._find_tree_linked_node("data_file", "data_file_id", owner.id)
            base = self.format_tree_path_label(node.id, separator=separator, omit_root_group=omit_root_group) if node else (owner.name or "")
            labels = [label for label in [base, series.name] if label]
            return separator.join(labels)
        if owner_kind == "dataset" and owner is not None and series is not None:
            labels = [label for label in [getattr(owner, "name", ""), series.name] if label]
            return separator.join(labels)
        image, curve = self._find_curve_owner(series_id)
        if image is not None and curve is not None:
            node = self._find_tree_linked_node("image_work", "image_work_id", image.id)
            base = self.format_tree_path_label(node.id, separator=separator, omit_root_group=omit_root_group) if node else (image.name or "")
            labels = [label for label in [base, curve.name] if label]
            return separator.join(labels)
        return ""

    def _ensure_unique_series_name(
        self,
        owner_name: str,
        series_list: List[DataSeries],
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
        curves: List[Curve],
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

    # ─────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────

    @property
    def projects(self) -> List[Project]:
        return self._projects

    @property
    def project_session(self) -> ProjectSession:
        return self._project_session

    @property
    def current_project(self) -> Optional[Project]:
        if self._current_project_id is None:
            return None
        return self.get_project(self._current_project_id)

    @property
    def current_project_id(self) -> Optional[str]:
        return self._current_project_id

    @property
    def tree(self) -> TreeManager:
        return self._tree_manager

    @property
    def data_files(self) -> DataFileManager:
        return self._data_file_manager

    @property
    def analysis(self) -> AnalysisManager:
        return self._analysis_manager

    # ─────────────────────────────────────────────
    # 项目查找与切换
    # ─────────────────────────────────────────────

    def get_project(self, project_id: str) -> Optional[Project]:
        for p in self._projects:
            if p.id == project_id:
                return p
        return None

    def set_current_project(self, project_id: str) -> None:
        if self.get_project(project_id):
            self._current_project_id = project_id

    def clear_current_project(self) -> None:
        """Public facade: 清除当前项目选择。"""
        self._current_project_id = None

    def find_folder_by_group_type(self, group_type: str, parent_id: Optional[str] = None) -> Optional[FolderNode]:
        """Public facade: 按 group_type 查找文件夹节点。"""
        return self._find_folder_by_group_type(group_type, parent_id)

    @staticmethod
    def canonical_group_type(group_type: Optional[str]) -> Optional[str]:
        """Public facade: 标准化 group_type。"""
        if group_type is None:
            return None
        canonical_map = {
            "dataset_set": "datasets",
            "image_set": "images",
            "picture_set": "pictures",
            "tool_set": "tools",
            "template_group": "figure_template_group",
            "figure_template_group": "figure_template_group",
            "report_template_group": "report_template_group",
            "ai_group": "ai_group",
        }
        return canonical_map.get(group_type, group_type)

    # ─────────────────────────────────────────────
    # 创建 / 打开 / 保存 / 关闭
    # ─────────────────────────────────────────────

    def create_new(
        self,
        name: str,
        parent_dir: Optional[str] = None,
        create_structure: bool = False,
    ) -> Project:
        project = Project.create_new(name)
        self._projects.append(project)
        self._current_project_id = project.id

        self._project_tree_init_service.init_new_project_tree(project)

        if create_structure:
            base_dir = self._normalize_path(parent_dir or os.getcwd())
            safe_name = self._safe_filename(name)
            project_dir = Path(base_dir) / safe_name
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "files" / "images").mkdir(parents=True, exist_ok=True)
            (project_dir / "files" / "source_files").mkdir(parents=True, exist_ok=True)
            (project_dir / "files" / "pictures").mkdir(parents=True, exist_ok=True)
            project_file = project_dir / f"{safe_name}.aline"
            self.save(str(project_file))

        return project

    def _normalize_project_file_path(self, file_path: str, *, for_save: bool) -> str:
        return self._project_repository.normalize_project_file_path(file_path, for_save=for_save)

    def open(self, file_path: str) -> Project:
        project = self._project_repository.open_project(file_path)

        existing = self.get_project(project.id)
        if existing:
            idx = self._projects.index(existing)
            self._projects[idx] = project
        else:
            self._projects.append(project)

        self._current_project_id = project.id

        return project

    def save(self, file_path: Optional[str] = None) -> str:
        if self.current_project is None:
            raise ValueError("没有当前项目")
        return self._project_repository.save_project(self.current_project, file_path)

    def _save_project(self, path: str) -> None:
        if self.current_project is None:
            raise ValueError("没有当前项目")
        self._serializer.save(self.current_project, path)

    def _load_project(self, path: str) -> Optional[Project]:
        return self._serializer.load(path)

    def close_project(self, project_id: str) -> None:
        self._projects = [p for p in self._projects if p.id != project_id]
        if self._current_project_id == project_id:
            self._current_project_id = self._projects[0].id if self._projects else None

    def close_current_project(self) -> None:
        if self._current_project_id:
            self.close_project(self._current_project_id)

    # ─────────────────────────────────────────────
    # 图像管理（PyLine 原有，保持完整）
    # ─────────────────────────────────────────────

    def add_image(self, image_path: str, name: Optional[str] = None, parent_id: Optional[str] = None) -> ImageWork:
        self._clear_last_operation_error()
        if self.current_project is None:
            raise ValueError("没有当前项目")
        image_path = self._normalize_path(image_path)
        if self.current_project.tree is None:
            self.migrate_to_v2(self.current_project)
        self._ensure_project_tree_groups(self.current_project)
        if parent_id is None:
            img_folder = self._find_folder_by_group_type("images")
            parent_id = img_folder.id if img_folder else None
        image_name = name or os.path.basename(image_path)
        if not self._ensure_unique_tree_child_name(
            parent_id,
            image_name,
            node_kind="image_work",
            project=self.current_project,
        ):
            raise ValueError(self.get_last_error_message())
        image_work = ImageWork(
            id=str(uuid.uuid4()),
            name=image_name,
            image_path=image_path,
            source_image_path=image_path,
        )
        if self.current_project.file_path:
            self._backup_image_for_project(image_work, self.current_project.file_path, None)
        self.current_project.images.append(image_work)
        self.current_project.is_modified = True
        # 同时在项目树中添加 ImageWorkNode
        if self.current_project.tree is not None:
            order = self.current_project.tree.get_siblings_max_order(parent_id) + 1
            img_node = ImageWorkNode(
                name=image_work.name,
                parent_id=parent_id,
                image_work_id=image_work.id,
                order=order,
            )
            self.current_project.tree.nodes.append(img_node)
        return image_work

    def get_image(self, image_id: str) -> Optional[ImageWork]:
        if self.current_project is None:
            return None
        for img in self.current_project.images:
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
        image_node = self._find_tree_linked_node("image_work", "image_work_id", image_id, project)
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
        old_path = (Path(project.file_path).parent / raw_path).resolve()
        if not old_path.exists():
            project.is_modified = True
            return True
        new_filename = self._backup_filename(image, old_path.suffix)
        new_path = old_path.with_name(new_filename)
        if new_path.exists() and new_path.resolve() != old_path.resolve():
            new_path = self._ensure_unique_path(new_path, image.id)
        try:
            old_path.rename(new_path)
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
        dest_project = self.get_project(dest_project_id)
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

    def resolve_image_path(self, image: ImageWork, project: Optional[Project] = None) -> str:
        raw_path = image.image_path or image.source_image_path or ""
        if not raw_path:
            return ""
        path = Path(raw_path)
        if path.is_absolute():
            return str(path)
        owner = project
        if owner is None:
            owner, _ = self._get_image_owner(image.id)
        if owner and owner.file_path:
            return str((Path(owner.file_path).parent / path).resolve())
        return str(path)

    def get_image_path(self, image_id: str) -> str:
        project, image = self._get_image_owner(image_id)
        if image is None:
            return ""
        return self.resolve_image_path(image, project)

    def add_picture(
        self,
        image_path: str,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
        *,
        plot_snapshot: Optional[PicturePlotSnapshot] = None,
    ) -> Optional[PictureNode]:
        self._clear_last_operation_error()
        p = self.current_project
        if p is None:
            return None
        image_path = self._normalize_path(image_path)
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        if p.tree is None:
            self.migrate_to_v2(p)
        self._ensure_project_tree_groups(p)
        if parent_id is None:
            picture_folder = self._find_folder_by_group_type("pictures")
            parent_id = picture_folder.id if picture_folder else None
        picture_name = name or os.path.basename(image_path)
        if not self._ensure_unique_tree_child_name(parent_id, picture_name, node_kind="picture", project=p):
            return None
        picture = PictureAsset(
            id=str(uuid.uuid4()),
            name=picture_name,
            image_path=image_path,
            plot_snapshot=plot_snapshot.model_copy(deep=True) if plot_snapshot is not None else None,
        )
        if p.file_path:
            self._backup_picture_for_project(picture, p.file_path, None, target_folder_id=parent_id)
        p.pictures.append(picture)
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore[union-attr]
        node = PictureNode(name=picture.name, parent_id=parent_id, picture_id=picture.id, order=order)
        p.tree.nodes.append(node)  # type: ignore[union-attr]
        p.is_modified = True
        return node

    def get_picture(self, picture_id: str) -> Optional[PictureAsset]:
        if self.current_project is None:
            return None
        return self.current_project.find_picture(picture_id)

    def remove_picture(self, picture_id: str) -> Optional[PictureAsset]:
        project, picture = self._get_picture_owner(picture_id)
        if project is None or picture is None:
            return None
        self._delete_picture_backup_if_managed(picture, project)
        project.pictures = [item for item in project.pictures if item.id != picture_id]
        project.is_modified = True
        return picture

    def rename_picture(self, picture_id: str, new_name: str) -> bool:
        self._clear_last_operation_error()
        project, picture = self._get_picture_owner(picture_id)
        if project is None or picture is None:
            return False
        picture_node = self._find_tree_linked_node("picture", "picture_id", picture_id, project)
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
        old_path = picture_path if picture_path.is_absolute() else (Path(project.file_path).parent / picture_path).resolve()
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

    def resolve_picture_path(self, picture: PictureAsset, project: Optional[Project] = None) -> str:
        raw_path = picture.image_path or ""
        if not raw_path:
            return ""
        path = Path(raw_path)
        if path.is_absolute():
            return str(path)
        owner = project
        if owner is None:
            owner, _ = self._get_picture_owner(picture.id)
        if owner and owner.file_path:
            return str((Path(owner.file_path).parent / path).resolve())
        return str(path)

    def get_picture_path(self, picture_id: str) -> str:
        project, picture = self._get_picture_owner(picture_id)
        if picture is None:
            return ""
        return self.resolve_picture_path(picture, project)

    def add_source_file(
        self,
        file_path: str,
        name: Optional[str] = None,
        parent_id: Optional[str] = None,
        *,
        auto_rename_on_conflict: bool = False,
    ) -> Optional[SourceFileNode]:
        self._clear_last_operation_error()
        p = self.current_project
        if p is None:
            return None
        normalized_path = self._normalize_path(file_path)
        if not os.path.exists(normalized_path):
            raise FileNotFoundError(f"源文件不存在: {normalized_path}")
        if p.tree is None:
            self.migrate_to_v2(p)
        self._ensure_project_tree_groups(p)
        if parent_id is None:
            source_root = self._find_folder_by_group_type("source_files")
            parent_id = source_root.id if source_root else None
        source_path = Path(normalized_path)
        source_name = name or source_path.name
        if auto_rename_on_conflict:
            source_name = self._next_unique_tree_child_name(parent_id, source_name, node_kind="source_file", project=p)
        if not self._ensure_unique_tree_child_name(parent_id, source_name, node_kind="source_file", project=p):
            return None
        asset = SourceFileAsset(
            id=str(uuid.uuid4()),
            name=source_name,
            file_path=normalized_path,
            source_file_path=normalized_path,
            file_size=source_path.stat().st_size,
        )
        if p.file_path:
            self._backup_source_file_for_project(asset, p.file_path, None, target_folder_id=parent_id)
        p.source_files.append(asset)
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore[union-attr]
        node = SourceFileNode(name=asset.name, parent_id=parent_id, source_file_id=asset.id, order=order)
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
        if self.current_project is None:
            return None
        return self.current_project.find_source_file(source_file_id)

    def remove_source_file(self, source_file_id: str) -> Optional[SourceFileAsset]:
        project, source_file = self._get_source_file_owner(source_file_id)
        if project is None or source_file is None:
            return None
        self._delete_source_file_backup_if_managed(source_file, project)
        project.source_files = [item for item in project.source_files if item.id != source_file_id]
        project.is_modified = True
        return source_file

    def rename_source_file(self, source_file_id: str, new_name: str) -> bool:
        self._clear_last_operation_error()
        project, source_file = self._get_source_file_owner(source_file_id)
        if project is None or source_file is None:
            return False
        source_node = self._find_tree_linked_node("source_file", "source_file_id", source_file_id, project)
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
        old_path = (Path(project.file_path).parent / raw_path).resolve()
        if not old_path.exists():
            project.is_modified = True
            return True
        new_filename = self._backup_filename(source_file, old_path.suffix)
        new_path = old_path.with_name(new_filename)
        if new_path.exists() and new_path.resolve() != old_path.resolve():
            new_path = self._ensure_unique_path(new_path, source_file.id)
        try:
            old_path.rename(new_path)
            rel = new_path.relative_to(Path(project.file_path).parent)
            source_file.file_path = rel.as_posix()
        except OSError:
            source_file.name = old_name
            self._fail_operation(f"源文件“{old_name}”重命名失败")
            return False
        project.is_modified = True
        return True

    def resolve_source_file_path(self, source_file: SourceFileAsset, project: Optional[Project] = None) -> str:
        raw_path = source_file.file_path or source_file.source_file_path or ""
        if not raw_path:
            return ""
        path = Path(raw_path)
        if path.is_absolute():
            return str(path)
        owner = project
        if owner is None:
            owner, _ = self._get_source_file_owner(source_file.id)
        if owner and owner.file_path:
            return str((Path(owner.file_path).parent / path).resolve())
        return str(path)

    def resolve_source_file_origin_path(self, source_file: SourceFileAsset, project: Optional[Project] = None) -> str:
        raw_path = source_file.source_file_path or source_file.file_path or ""
        if not raw_path:
            return ""
        path = Path(raw_path)
        if path.is_absolute():
            return str(path)
        owner = project
        if owner is None:
            owner, _ = self._get_source_file_owner(source_file.id)
        if owner and owner.file_path:
            return str((Path(owner.file_path).parent / path).resolve())
        return str(path)

    def get_source_file_path(self, source_file_id: str) -> str:
        project, source_file = self._get_source_file_owner(source_file_id)
        if source_file is None:
            return ""
        return self.resolve_source_file_path(source_file, project)

    def get_source_file_target_folder_id(self, node_id: Optional[str] = None) -> Optional[str]:
        p = self.current_project
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
        if node.kind == "folder" and self._canonical_group_type(getattr(node, "group_type", None)) == "source_files":
            return node.id
        return source_root.id

    def resolve_source_file_folder_path(self, node_id: Optional[str] = None, create: bool = False) -> str:
        p = self.current_project
        if p is None or p.tree is None or not p.file_path:
            return ""
        source_root = self._find_folder_by_group_type("source_files")
        if source_root is None:
            return ""
        target_folder_id = self.get_source_file_target_folder_id(node_id)
        base_dir = self._project_assets_dir(p.file_path, "source_files")
        parts: List[str] = []
        current = p.tree.get_node(target_folder_id) if target_folder_id else None
        while current is not None and current.kind == "folder" and current.id != source_root.id:
            parts.append(self._safe_filename(current.name))
            parent_id = getattr(current, "parent_id", None)
            current = p.tree.get_node(parent_id) if parent_id else None
        folder_path = base_dir.joinpath(*reversed(parts)) if parts else base_dir
        if create:
            folder_path.mkdir(parents=True, exist_ok=True)
        return str(folder_path)

    def get_picture_target_folder_id(self, node_id: Optional[str] = None) -> Optional[str]:
        p = self.current_project
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
        if node.kind == "folder" and self._canonical_group_type(getattr(node, "group_type", None)) == "pictures":
            return node.id
        return pictures_root.id

    def get_analysis_result_target_folder_id(self, node_id: Optional[str] = None) -> Optional[str]:
        p = self.current_project
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

    def resolve_picture_folder_path(self, node_id: Optional[str] = None, create: bool = False) -> str:
        p = self.current_project
        if p is None or p.tree is None or not p.file_path:
            return ""
        pictures_root = self._find_folder_by_group_type("pictures")
        if pictures_root is None:
            return ""
        target_folder_id = self.get_picture_target_folder_id(node_id)
        base_dir = self._project_assets_dir(p.file_path, "pictures")
        parts: List[str] = []
        current = p.tree.get_node(target_folder_id) if target_folder_id else None
        while current is not None and current.kind == "folder" and current.id != pictures_root.id:
            parts.append(self._safe_filename(current.name))
            parent_id = getattr(current, "parent_id", None)
            current = p.tree.get_node(parent_id) if parent_id else None
        folder_path = base_dir.joinpath(*reversed(parts)) if parts else base_dir
        if create:
            folder_path.mkdir(parents=True, exist_ok=True)
        return str(folder_path)

    def prepare_picture_export_path(
        self,
        name: str,
        suffix: str = ".png",
        target_node_id: Optional[str] = None,
    ) -> str:
        folder_path = self.resolve_picture_folder_path(target_node_id, create=True)
        if not folder_path:
            return ""
        safe_name = self._safe_filename(name or "chart")
        candidate = Path(folder_path) / safe_name
        if candidate.suffix.lower() != suffix.lower():
            candidate = candidate.with_suffix(suffix)
        return str(self._ensure_unique_path(candidate, str(uuid.uuid4())))

    # ─────────────────────────────────────────────
    # 曲线管理（PyLine 原有，保持完整）
    # ─────────────────────────────────────────────

    def add_curve_to_image(
        self,
        image_id: str,
        x_data: List[float],
        y_data: List[float],
        name: str = "新曲线",
        color: str = "#0078D4",
        point_shape: str = "circle",
        calibration: Optional[CalibrationData] = None,
    ) -> Optional[Curve]:
        if self.current_project is None:
            return None
        image = self.get_image(image_id)
        if image is None:
            return None

        from processing.calibration import compute_actual_coords
        x_actual, y_actual = [], []
        for px, py in zip(x_data, y_data):
            if calibration:
                x, y = compute_actual_coords(calibration, px, py)
            else:
                x, y = px, py
            x_actual.append(x)
            y_actual.append(y)

        curve = Curve(
            id=str(uuid.uuid4()),
            name=name,
            x_data=x_data,
            y_data=y_data,
            x_actual=x_actual,
            y_actual=y_actual,
            color=color,
            point_shape=point_shape,
            source_image_id=image_id,
            calibration=calibration,
        )
        image.curves.append(curve)
        self.current_project.is_modified = True
        return curve

    def get_curve(self, curve_id: str) -> Optional[Curve]:
        if self.current_project is None:
            return None
        for img in self.current_project.images:
            for curve in img.curves:
                if curve.id == curve_id:
                    return curve
        for curve in self.current_project.imported_curves:
            if curve.id == curve_id:
                return curve
        return None

    def update_curve_calibration(self, curve_id: str, calibration: CalibrationData) -> None:
        if self.current_project is None:
            return
        curve = self.get_curve(curve_id)
        if curve:
            curve.calibration = calibration
            self.current_project.is_modified = True

    def pixel_to_actual_coords(
        self, curve_id: str, px: float, py: float
    ) -> Tuple[float, float]:
        curve = self.get_curve(curve_id)
        if curve is None or curve.calibration is None:
            return (px, py)
        from processing.calibration import compute_actual_coords
        return compute_actual_coords(curve.calibration, px, py)

    # ─────────────────────────────────────────────
    # ALine 数据集管理（新增）
    # ─────────────────────────────────────────────

    def add_dataset(self, name: str) -> Optional[Dataset]:
        from models.schemas import Dataset
        project = self.current_project
        if project is None:
            return None
        dataset = Dataset(name=name)
        project.datasets.append(dataset)
        project.is_modified = True
        return dataset

    def remove_dataset(self, dataset_id: str) -> bool:
        project = self.current_project
        if project is None:
            return False
        before = len(project.datasets)
        project.datasets = [ds for ds in project.datasets if ds.id != dataset_id]
        changed = len(project.datasets) < before
        if changed:
            project.is_modified = True
        return changed

    def rename_dataset(self, dataset_id: str, new_name: str) -> bool:
        project = self.current_project
        if project is None:
            return False
        for ds in project.datasets:
            if ds.id == dataset_id:
                ds.name = new_name
                project.is_modified = True
                return True
        return False

    def add_series_to_dataset(self, dataset_id: str, series: DataSeries) -> bool:
        project = self.current_project
        if project is None:
            return False
        for ds in project.datasets:
            if ds.id == dataset_id:
                ds.series.append(series)
                project.is_modified = True
                return True
        return False

    def remove_series(self, dataset_id: str, series_id: str) -> bool:
        del dataset_id
        return self.delete_series(series_id)

    def _find_series_owner(self, series_id: str) -> tuple[Optional[str], Any, Optional[DataSeries]]:
        p = self.current_project
        if p is None:
            return None, None, None
        for df in p.data_files:
            for series in df.series:
                if series.id == series_id:
                    return "data_file", df, series
        for ds in p.datasets:
            for series in ds.series:
                if series.id == series_id:
                    return "dataset", ds, series
        return None, None, None

    def rename_series(self, series_id: str, new_name: str) -> bool:
        return self._project_asset_service.rename_series(series_id, new_name)

    def delete_series(self, series_id: str) -> bool:
        return self._project_asset_service.delete_series(series_id)

    def move_series_to_data_file(self, series_id: str, target_data_file_id: str) -> bool:
        return self._project_asset_service.move_series_to_data_file(series_id, target_data_file_id)

    def import_curve_as_series(self, curve_id: str, dataset_id: str) -> Optional[DataSeries]:
        if self.current_project is None:
            return None
        curve = self.get_curve(curve_id)
        if curve is None:
            return None
        calib = curve.calibration
        x_label = "r" if (calib and calib.coord_type == "polar") else "x"
        y_label = "θ" if (calib and calib.coord_type == "polar") else "y"
        series = DataSeries(
            name=curve.name,
            x=list(curve.x_actual),
            y=list(curve.y_actual),
            color=curve.color,
            source_curve_id=curve.id,
            x_label=x_label,
            y_label=y_label,
        )
        return series if self.add_series_to_data_file(dataset_id, series) else None

    def _find_curve_owner(self, curve_id: str) -> tuple[Optional[Any], Optional[Curve]]:
        p = self.current_project
        if p is None:
            return None, None
        for img in p.images:
            for curve in img.curves:
                if curve.id == curve_id:
                    return img, curve
        return None, None

    def rename_curve(self, curve_id: str, new_name: str) -> bool:
        return self._project_asset_service.rename_curve(curve_id, new_name)

    def delete_curve(self, curve_id: str) -> bool:
        return self._project_asset_service.delete_curve(curve_id)

    def move_curve_to_image(self, curve_id: str, target_image_id: str) -> bool:
        return self._project_asset_service.move_curve_to_image(curve_id, target_image_id)

    # ─────────────────────────────────────────────
    # ALine 分析管理（新增）
    # ─────────────────────────────────────────────

    def add_analysis(self, result: AnalysisResult, parent_id: Optional[str] = None) -> bool:
        self._clear_last_operation_error()
        if self.current_project is None:
            return False
        if self.current_project.tree is None:
            self.migrate_to_v2(self.current_project)
        self._ensure_project_tree_groups(self.current_project)
        folder = self._find_folder_by_group_type("analysis_result_group")
        target_parent_id = self.get_analysis_result_target_folder_id(parent_id)
        if target_parent_id is None:
            target_parent_id = folder.id if folder is not None else None
        if not self._ensure_unique_tree_child_name(
            target_parent_id,
            result.name or result.analysis_type or "分析结果",
            node_kind="analysis_result",
            project=self.current_project,
        ):
            return False
        self.current_project.analyses.append(result)
        order = self.current_project.tree.get_siblings_max_order(target_parent_id) + 1  # type: ignore[union-attr]
        self.current_project.tree.nodes.append(  # type: ignore[union-attr]
            AnalysisResultNode(
                name=result.name or result.analysis_type or "分析结果",
                parent_id=target_parent_id,
                analysis_id=result.id,
                order=order,
            )
        )
        self.current_project.is_modified = True
        return True

    def remove_analysis(self, analysis_id: str) -> bool:
        return self._analysis_manager.delete_analysis(analysis_id)

    # ─────────────────────────────────────────────
    # ALine 图表配置管理（新增）
    # ─────────────────────────────────────────────

    def save_figure_config(self, config: FigureConfig) -> bool:
        if self.current_project is None:
            return False
        if global_assets.update_figure_template(config.id, template=config):
            return True
        global_assets.ensure_figure_template(config)
        return True

    def remove_figure_config(self, figure_id: str) -> bool:
        if self.current_project is None:
            return False
        return global_assets.delete_figure_template(figure_id)

    # ─────────────────────────────────────────────
    # v0.2 迁移
    # ─────────────────────────────────────────────

    def _init_new_project_tree(self, p: Project) -> None:
        self._project_tree_init_service.init_new_project_tree(p)

    def migrate_to_v2(self, project: Optional[Project] = None) -> None:
        """兼容旧调用点：当前版本不再做格式迁移，只初始化树结构。"""
        target = project or self.current_project
        if target is None:
            return
        self._init_new_project_tree(target)

    # ─────────────────────────────────────────────
    # 树节点 CRUD
    # ─────────────────────────────────────────────

    def add_folder(self, name: str, parent_id: Optional[str] = None, group_type: Optional[str] = None) -> Optional[FolderNode]:
        return self._project_tree_service.add_folder(name, parent_id, group_type)

    def rename_node(self, node_id: str, new_name: str) -> bool:
        return self._project_tree_service.rename_node(node_id, new_name)

    def delete_node(self, node_id: str) -> bool:
        """删除节点及其所有子节点和关联数据实体。"""
        return self._project_tree_service.delete_node(node_id)

    def remove_empty_folders(self, root_id: Optional[str] = None, *, include_root: bool = False) -> List[str]:
        """清理空的用户文件夹，保留系统分组文件夹。"""
        return self._project_tree_service.remove_empty_folders(root_id, include_root=include_root)

    def move_node(self, node_id: str, new_parent_id: Optional[str], new_order: int) -> bool:
        return self._project_tree_service.move_node(
            node_id,
            new_parent_id,
            new_order,
            group_type_aliases=_GROUP_TYPE_ALIASES,
            tool_node_parent_group=_TOOL_NODE_PARENT_GROUP,
        )

    def get_node_by_id(self, node_id: str) -> Optional["TreeNodeUnion"]:
        p = self.current_project
        if p is None or p.tree is None:
            return None
        return p.tree.get_node(node_id)

    def get_node_remark(self, node_id: str) -> str:
        node = self.get_node_by_id(node_id)
        return "" if node is None else str(getattr(node, "remark", "") or "")

    def set_node_remark(self, node_id: str, remark: str) -> bool:
        node = self.get_node_by_id(node_id)
        if node is None:
            return False
        clean = str(remark or "").strip()
        if getattr(node, "remark", "") == clean:
            return True
        setattr(node, "remark", clean)
        if self.current_project is not None:
            self.current_project.is_modified = True
        return True

    def get_children(self, parent_id: Optional[str]) -> list["TreeNodeUnion"]:
        p = self.current_project
        if p is None or p.tree is None:
            return []
        return p.tree.get_children(parent_id)

    def _find_folder_by_name(self, name: str, parent_id: Optional[str] = None) -> Optional["TreeNodeUnion"]:
        """在树中按名称查找指定层级的文件夹节点。"""
        p = self.current_project
        if p is None or p.tree is None:
            return None
        return p.tree.find_first(kind="folder", name=name, parent_id=parent_id)

    def _find_folder_by_group_type(self, group_type: str, parent_id: Optional[str] = None) -> Optional[FolderNode]:
        """按 group_type 查找文件夹节点（更稳健，不依赖名称）。"""
        p = self.current_project
        if p is None or p.tree is None:
            return None
        group_type = self._canonical_group_type(group_type) or group_type
        candidates = _GROUP_TYPE_ALIASES.get(group_type, {group_type})
        for node in p.tree.find_nodes(kind="folder", parent_id=parent_id):
            if (node.kind == "folder"
                    and getattr(node, "group_type", None) in candidates):
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

    def _ensure_group_folder(
        self,
        project: Project,
        group_type: str,
        parent_id: Optional[str],
        order: int,
    ) -> tuple[FolderNode, bool]:
        if project.tree is None:
            raise ValueError("project tree is not initialized")

        previous_project_id = self._current_project_id
        self._current_project_id = project.id
        try:
            folder = self._find_folder_by_group_type(group_type, parent_id)
        finally:
            self._current_project_id = previous_project_id

        canonical = self._canonical_group_type(group_type) or group_type
        changed = False
        if folder is None:
            folder = FolderNode(
                name=_GROUP_DISPLAY_NAMES[canonical],
                parent_id=parent_id,
                order=order,
                group_type=canonical,  # type: ignore[arg-type]
            )
            project.tree.nodes.append(folder)
            changed = True

        if folder.name != _GROUP_DISPLAY_NAMES[canonical]:
            folder.name = _GROUP_DISPLAY_NAMES[canonical]
            changed = True
        if folder.parent_id != parent_id:
            folder.parent_id = parent_id
            changed = True
        if folder.order != order:
            folder.order = order
            changed = True
        if folder.group_type != canonical:
            folder.group_type = cast(Any, canonical)
            changed = True
        return folder, changed

    def _merge_duplicate_group_folders(self, project: Project, primary_id: str) -> bool:
        if project.tree is None:
            return False
        primary = project.tree.get_node(primary_id)
        if primary is None or primary.kind != "folder":
            return False

        canonical = self._canonical_group_type(getattr(primary, "group_type", None))
        if canonical is None:
            return False

        duplicate_ids = []
        next_order = project.tree.get_siblings_max_order(primary.id) + 1
        for node in list(project.tree.nodes):
            if node.kind != "folder" or node.id == primary.id:
                continue
            if self._canonical_group_type(getattr(node, "group_type", None)) != canonical:
                continue
            if node.parent_id != primary.parent_id:
                continue
            for child in project.tree.get_children(node.id):
                child.parent_id = primary.id
                child.order = next_order
                next_order += 1
            duplicate_ids.append(node.id)

        if duplicate_ids:
            project.tree.nodes = [node for node in project.tree.nodes if node.id not in duplicate_ids]
            return True
        return False

    def _ensure_project_tree_groups(self, project: Optional[Project] = None) -> bool:
        p = project or self.current_project
        if p is None or p.tree is None:
            return False

        changed = False
        source_folder, source_changed = self._ensure_group_folder(p, "source_files", None, 0)
        ds_folder, ds_changed = self._ensure_group_folder(p, "datasets", None, 1)
        picture_folder, picture_changed = self._ensure_group_folder(p, "pictures", None, 2)
        img_folder, img_changed = self._ensure_group_folder(p, "images", None, 3)
        analysis_folder, analysis_changed = self._ensure_group_folder(p, "analysis_result_group", None, 4)
        changed = changed or source_changed or ds_changed or picture_changed or img_changed
        changed = changed or analysis_changed

        for folder in (source_folder, ds_folder, picture_folder, img_folder, analysis_folder):
            if folder is None:
                continue
            changed = self._merge_duplicate_group_folders(p, folder.id) or changed

        for node in p.tree.nodes:
            desired_parent_id = None
            if node.kind == "data_file" and node.parent_id is None:
                desired_parent_id = ds_folder.id
            elif node.kind == "source_file" and node.parent_id is None:
                desired_parent_id = source_folder.id
            elif node.kind == "image_work" and node.parent_id is None:
                desired_parent_id = img_folder.id
            elif node.kind == "picture" and node.parent_id is None:
                desired_parent_id = picture_folder.id

            if desired_parent_id is not None and node.parent_id != desired_parent_id:
                node.parent_id = desired_parent_id
                node.order = p.tree.get_siblings_max_order(desired_parent_id) + 1
                changed = True
            elif node.kind == "analysis_result" and node.parent_id != analysis_folder.id:
                node.parent_id = analysis_folder.id
                node.order = p.tree.get_siblings_max_order(analysis_folder.id) + 1
                changed = True

        if changed:
            p.is_modified = True
        return changed

    # ─────────────────────────────────────────────
    # v0.2 DataFile CRUD
    # ─────────────────────────────────────────────

    def add_data_file(
        self,
        df: DataFile,
        parent_id: Optional[str] = None,
        *,
        auto_rename_on_conflict: bool = False,
    ) -> Optional[DataFileNode]:
        return self._project_asset_service.add_data_file(df, parent_id, auto_rename_on_conflict=auto_rename_on_conflict)

    def get_data_file(self, df_id: str) -> Optional[DataFile]:
        return self._project_asset_service.get_data_file(df_id)

    def add_series_to_data_file(self, data_file_id: str, series: DataSeries) -> bool:
        return self._project_asset_service.add_series_to_data_file(data_file_id, series)

    # ─────────────────────────────────────────────
    # v0.2 Pipeline CRUD
    # ─────────────────────────────────────────────

    def add_saved_pipeline(
        self, name: str, ops: List[dict[str, Any]], description: str = "", parent_id: Optional[str] = None
    ) -> Optional[SavedPipeline]:
        if self.current_project is None:
            return None
        del parent_id
        pipeline = SavedPipeline(name=name, ops=ops, description=description)
        global_assets.add_saved_pipeline(pipeline)
        return pipeline

    def load_pipeline(self, pipeline_id: str) -> List[dict[str, Any]]:
        """返回 ops 列表；未找到时返回空列表。"""
        sp = global_assets.get_saved_pipeline(pipeline_id)
        return list(sp.ops) if sp else []

    def update_saved_pipeline(
        self,
        pipeline_id: str,
        *,
        name: Optional[str] = None,
        ops: Optional[List[dict[str, Any]]] = None,
        description: Optional[str] = None,
    ) -> bool:
        return global_assets.update_saved_pipeline(pipeline_id, name=name, ops=ops, description=description)

    def delete_saved_pipeline(self, pipeline_id: str) -> bool:
        return global_assets.delete_saved_pipeline(pipeline_id)

    # ─────────────────────────────────────────────
    # v0.2 FigureTemplate CRUD
    # ─────────────────────────────────────────────

    def add_figure_template(self, config: FigureConfig, parent_id: Optional[str] = None) -> Optional[FigureConfig]:
        if self.current_project is None:
            return None
        del parent_id
        global_assets.add_figure_template(config)
        return config

    def delete_figure_template(self, figure_id: str) -> bool:
        return global_assets.delete_figure_template(figure_id)

    # ─────────────────────────────────────────────
    # v0.3 ReportTemplate CRUD
    # ─────────────────────────────────────────────

    def add_report_template(
        self,
        name: str,
        content: str = "",
        is_builtin: bool = False,
        parent_id: Optional[str] = None,
    ) -> Optional[ReportTemplate]:
        if self.current_project is None:
            return None
        del parent_id
        tmpl = ReportTemplate(name=name, content=content, is_builtin=is_builtin)
        global_assets.add_report_template(tmpl)
        return tmpl

    def get_report_template(self, template_id: str) -> Optional[ReportTemplate]:
        return global_assets.get_report_template(template_id)

    def update_report_template(self, template_id: str, name: Optional[str] = None, content: Optional[str] = None) -> bool:
        return global_assets.update_report_template(template_id, name=name, content=content)

    def delete_report_template(self, template_id: str) -> bool:
        return global_assets.delete_report_template(template_id)

    # ─────────────────────────────────────────────
    # v0.3 AI 工具 CRUD
    # ─────────────────────────────────────────────

    def add_ai_prompt(self, name: str, content: str = "", description: str = "") -> Optional[AIPrompt]:
        if self.current_project is None:
            return None
        return global_assets.add_ai_prompt(name, content, description)

    def get_ai_prompt(self, prompt_id: str) -> Optional[AIPrompt]:
        return global_assets.get_ai_prompt(prompt_id)

    def update_ai_prompt(self, prompt_id: str, name: Optional[str] = None, content: Optional[str] = None, description: Optional[str] = None) -> bool:
        return global_assets.update_ai_prompt(
            prompt_id,
            name=name,
            content=content,
            description=description,
        )

    def delete_ai_prompt(self, prompt_id: str) -> bool:
        return global_assets.delete_ai_prompt(prompt_id)

    def add_ai_skill(self, name: str, code: str = "", description: str = "") -> Optional[AISkill]:
        if self.current_project is None:
            return None
        return global_assets.add_ai_skill(name, code, description)

    def get_ai_skill(self, skill_id: str) -> Optional[AISkill]:
        return global_assets.get_ai_skill(skill_id)

    def delete_ai_skill(self, skill_id: str) -> bool:
        return global_assets.delete_ai_skill(skill_id)

    def add_ai_agent(self, name: str, system_prompt: str = "", description: str = "") -> Optional[AIAgent]:
        if self.current_project is None:
            return None
        return global_assets.add_ai_agent(name, system_prompt, description)

    def get_ai_agent(self, agent_id: str) -> Optional[AIAgent]:
        return global_assets.get_ai_agent(agent_id)

    def delete_ai_agent(self, agent_id: str) -> bool:
        return global_assets.delete_ai_agent(agent_id)

    def get_series_remark(self, series_id: str) -> str:
        series = self.get_series_from_node("series", series_id)
        return "" if series is None else str(getattr(series, "remark", "") or "")

    def set_series_remark(self, series_id: str, remark: str) -> bool:
        series = self.get_series_from_node("series", series_id)
        if series is None:
            return False
        clean = str(remark or "").strip()
        if getattr(series, "remark", "") == clean:
            return True
        series.remark = clean
        if self.current_project is not None:
            self.current_project.is_modified = True
        return True

    def get_curve_remark(self, curve_id: str) -> str:
        curve = self.get_curve(curve_id)
        return "" if curve is None else str(getattr(curve, "remark", "") or "")

    def set_curve_remark(self, curve_id: str, remark: str) -> bool:
        curve = self.get_curve(curve_id)
        if curve is None:
            return False
        clean = str(remark or "").strip()
        if getattr(curve, "remark", "") == clean:
            return True
        curve.remark = clean
        if self.current_project is not None:
            self.current_project.is_modified = True
        return True

    # ─────────────────────────────────────────────
    # v0.3 数据系列路由
    # ─────────────────────────────────────────────

    def get_series_from_node(self, kind: str, node_id: str) -> Optional[DataSeries]:
        """根据树节点 kind + node_id 返回对应 DataSeries（供各页面统一调用）。

        支持：
        - kind="data_file"   → 返回 DataFile.series[0]（第一个系列）
        - kind="series"      → 按 node_id 直接查找 DataSeries（虚拟叶节点）
        - kind="image_work"  → 返回 ImageWork.curves[0] 转换的 DataSeries
        - kind="curve"       → 按 node_id 查找 Curve 并转换为 DataSeries
        """
        p = self.current_project
        if p is None:
            return None

        if kind == "series":
            # 虚拟叶节点：node_id 即 DataSeries.id
            return p.find_series(node_id)

        if kind == "curve":
            # 虚拟叶节点：node_id 即 Curve.id
            curve = self.get_curve(node_id)
            if curve and curve.x_actual:
                return DataSeries(
                    id=curve.id,
                    name=curve.name,
                    x=list(curve.x_actual),
                    y=list(curve.y_actual),
                    color=curve.color,
                    source_curve_id=curve.id,
                )
            return None

        if kind == "data_file":
            node = self.get_node_by_id(node_id)
            if node and node.kind == "data_file":
                df = p.find_data_file(node.data_file_id)
                if df and df.series:
                    return df.series[0]
            return None

        if kind == "image_work":
            node = self.get_node_by_id(node_id)
            if node and node.kind == "image_work":
                img = self.get_image(node.image_work_id)
                if img and img.curves:
                    c = img.curves[0]
                    if c.x_actual:
                        return DataSeries(
                            id=c.id,
                            name=c.name,
                            x=list(c.x_actual),
                            y=list(c.y_actual),
                            color=c.color,
                            source_curve_id=c.id,
                        )
            return None

        return None

    def get_all_series_from_node(self, kind: str, node_id: str) -> list[Any]:
        """返回节点下所有 DataSeries 列表（data_file/image_work 返回多个）。"""
        p = self.current_project
        if p is None:
            return []

        if kind in ("series", "curve"):
            s = self.get_series_from_node(kind, node_id)
            return [s] if s else []

        if kind == "data_file":
            node = self.get_node_by_id(node_id)
            if node and node.kind == "data_file":
                df = p.find_data_file(node.data_file_id)
                if df:
                    return list(df.series)
            return []

        if kind == "image_work":
            node = self.get_node_by_id(node_id)
            if node and node.kind == "image_work":
                img = self.get_image(node.image_work_id)
                if img:
                    result = []
                    for c in img.curves:
                        if c.x_actual:
                            result.append(DataSeries(
                                id=c.id,
                                name=c.name,
                                x=list(c.x_actual),
                                y=list(c.y_actual),
                                color=c.color,
                                source_curve_id=c.id,
                            ))
                    return result
            return []

        return []

    # ─────────────────────────────────────────────
    # 可视化数据聚合（供各页面调用）
    # ─────────────────────────────────────────────

    def collect_all_series(self, project: Optional[Project] = None) -> list[dict[str, Any]]:
        """汇总项目中所有可用数据系列，供可视化页和分析页使用。

        Returns:
            List[dict]: 每项包含 type / id / name / series_obj / color 等键。
        """
        p = project or self.current_project
        if p is None:
            return []
        result = []
        # 1. 图像提取曲线
        for img in p.images:
            for curve in img.curves:
                if curve.x_actual:
                    result.append({
                        "type": "curve",
                        "id": curve.id,
                        "name": f"{img.name} / {curve.name}",
                        "obj": curve,
                    })
        # 2. imported_curves
        for curve in p.imported_curves:
            if curve.x_actual:
                result.append({
                    "type": "curve",
                    "id": curve.id,
                    "name": f"[导入] {curve.name}",
                    "obj": curve,
                })
        # 3. ALine DataSeries
        for ds in p.datasets:
            for series in ds.series:
                result.append({
                    "type": "series",
                    "id": series.id,
                    "name": f"{ds.name} / {series.name}",
                    "obj": series,
                })
        # 4. v0.2+ DataFile.series
        for df in p.data_files:
            for series in df.series:
                result.append({
                    "type": "series",
                    "id": series.id,
                    "name": f"{df.name} / {series.name}",
                    "obj": series,
                })
        return result

    # ─────────────────────────────────────────────
    # 内部辅助（PyLine 原有逻辑，保持完整）
    # ─────────────────────────────────────────────

    def _normalize_path(self, path: str) -> str:
        return str(Path(path).expanduser().resolve())

    def _safe_filename(self, text: str) -> str:
        text = (text or "").strip() or "untitled"
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
        return sanitized.rstrip(". ") or "untitled"

    def _get_image_owner(self, image_id: str) -> Tuple[Optional[Project], Optional[ImageWork]]:
        for project in self._projects:
            for image in project.images:
                if image.id == image_id:
                    return project, image
        return None, None

    def _get_picture_owner(self, picture_id: str) -> Tuple[Optional[Project], Optional[PictureAsset]]:
        for project in self._projects:
            for picture in project.pictures:
                if picture.id == picture_id:
                    return project, picture
        return None, None

    def _get_source_file_owner(self, source_file_id: str) -> Tuple[Optional[Project], Optional[SourceFileAsset]]:
        for project in self._projects:
            for source_file in project.source_files:
                if source_file.id == source_file_id:
                    return project, source_file
        return None, None

    def _backup_filename(self, asset: ImageWork | PictureAsset | SourceFileAsset, source_suffix: str) -> str:
        name = self._safe_filename(asset.name)
        p = Path(name)
        if p.suffix:
            return name
        suffix = (source_suffix or ".bin").lower()
        return f"{name}{suffix}"

    def _ensure_unique_path(self, candidate: Path, image_id: str) -> Path:
        if not candidate.exists():
            return candidate
        stem, suffix = candidate.stem, candidate.suffix
        for idx in range(1, 1000):
            trial = candidate.with_name(f"{stem}_{idx}{suffix}")
            if not trial.exists():
                return trial
        return candidate.with_name(f"{stem}_{image_id}{suffix}")

    def _copy_file(self, source_path: Path, backup_path: Path) -> None:
        shutil.copy2(source_path, backup_path)

    def _project_assets_dir(self, project_file_path: str, folder_name: str = "images") -> Path:
        return Path(project_file_path).parent / "files" / folder_name

    def _backup_image_for_project(
        self,
        image: ImageWork,
        project_file_path: str,
        source_project: Optional[Project],
    ) -> None:
        self._project_backup_manager.backup_image_for_project(image, project_file_path, source_project)

    def _backup_picture_for_project(
        self,
        picture: PictureAsset,
        project_file_path: str,
        source_project: Optional[Project],
        target_folder_id: Optional[str] = None,
    ) -> None:
        self._project_backup_manager.backup_picture_for_project(
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
        self._project_backup_manager.backup_source_file_for_project(
            source_file,
            project_file_path,
            source_project,
            target_folder_id=target_folder_id,
        )

    def _picture_relative_subdir(self, picture: PictureAsset) -> Optional[Path]:
        raw_path = picture.image_path or ""
        if not raw_path or Path(raw_path).is_absolute():
            return None
        parts = Path(raw_path).parts
        if len(parts) >= 3 and parts[0] == "files" and parts[1] == "pictures":
            return Path(*parts[2:-1]) if len(parts) > 3 else Path()
        return None

    def _source_file_relative_subdir(self, source_file: SourceFileAsset) -> Optional[Path]:
        raw_path = source_file.file_path or ""
        if not raw_path or Path(raw_path).is_absolute():
            return None
        parts = Path(raw_path).parts
        if len(parts) >= 3 and parts[0] == "files" and parts[1] == "source_files":
            return Path(*parts[2:-1]) if len(parts) > 3 else Path()
        return None

    def _node_collection_group_type(self, node_id: str) -> Optional[str]:
        p = self.current_project
        if p is None or p.tree is None:
            return None
        current = p.tree.get_node(node_id)
        while current is not None:
            if current.kind == "folder":
                group_type = self._canonical_group_type(getattr(current, "group_type", None))
                if group_type is not None:
                    return group_type
            parent_id = getattr(current, "parent_id", None)
            current = p.tree.get_node(parent_id) if parent_id else None
        return None

    def _sync_picture_storage(self) -> None:
        p = self.current_project
        if p is None or p.tree is None or not p.file_path:
            return
        base_dir = self._project_assets_dir(p.file_path, "pictures")
        base_dir.mkdir(parents=True, exist_ok=True)
        project_root = Path(p.file_path).parent
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
            target_name = self._backup_filename(picture, current_path.suffix or Path(picture.name).suffix)
            target_path = target_dir / target_name
            if target_path.exists() and target_path.resolve() != current_path.resolve():
                target_path = self._ensure_unique_path(target_path, picture.id)
            if current_path.resolve() != target_path.resolve():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current_path), str(target_path))
            try:
                picture.image_path = target_path.relative_to(project_root).as_posix()
            except Exception:
                picture.image_path = str(target_path)
        self._remove_empty_directories(base_dir)

    def _sync_source_file_storage(self) -> None:
        p = self.current_project
        if p is None or p.tree is None or not p.file_path:
            return
        base_dir = self._project_assets_dir(p.file_path, "source_files")
        base_dir.mkdir(parents=True, exist_ok=True)
        project_root = Path(p.file_path).parent
        for node in [item for item in p.tree.nodes if item.kind == "source_file"]:
            source_file = p.find_source_file(node.source_file_id)
            if source_file is None:
                continue
            current_path_str = self.resolve_source_file_path(source_file, p)
            if not current_path_str:
                continue
            current_path = Path(current_path_str)
            if not current_path.exists() or Path(source_file.file_path or "").is_absolute():
                continue
            target_folder = self.resolve_source_file_folder_path(node.id, create=True)
            if not target_folder:
                continue
            target_dir = Path(target_folder)
            target_name = self._backup_filename(source_file, current_path.suffix or Path(source_file.name).suffix)
            target_path = target_dir / target_name
            if target_path.exists() and target_path.resolve() != current_path.resolve():
                target_path = self._ensure_unique_path(target_path, source_file.id)
            if current_path.resolve() != target_path.resolve():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(current_path), str(target_path))
            try:
                source_file.file_path = target_path.relative_to(project_root).as_posix()
            except Exception:
                source_file.file_path = str(target_path)
            if target_path.exists():
                source_file.file_size = target_path.stat().st_size
        self._remove_empty_directories(base_dir)

    def _remove_empty_directories(self, root_dir: Path) -> None:
        if not root_dir.exists():
            return
        for child in sorted(root_dir.rglob("*"), reverse=True):
            if not child.is_dir():
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

    def _sync_project_backups(
        self,
        project: Project,
        target_file_path: str,
        source_file_path: Optional[str],
    ) -> None:
        source_project = project.model_copy(deep=False)
        source_project.file_path = source_file_path
        for source_file in project.source_files:
            self._backup_source_file_for_project(source_file, target_file_path, source_project)
        for image in project.images:
            self._backup_image_for_project(image, target_file_path, source_project)
        for picture in project.pictures:
            self._backup_picture_for_project(picture, target_file_path, source_project)

    def _delete_backup_if_managed(self, image: ImageWork, project: Project) -> None:
        self._project_backup_manager.delete_backup_if_managed(image, project, path_attr="image_path")

    def _delete_picture_backup_if_managed(self, picture: PictureAsset, project: Project) -> None:
        self._project_backup_manager.delete_backup_if_managed(picture, project, path_attr="image_path")

    def _delete_source_file_backup_if_managed(self, source_file: SourceFileAsset, project: Project) -> None:
        self._project_backup_manager.delete_backup_if_managed(source_file, project, path_attr="file_path")


# 全局单例
project_manager = ProjectManager()
