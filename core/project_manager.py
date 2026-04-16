"""
项目管理器 — 兼容读写 .pyline / .aline 文件

完整保留 PyLine 原有所有方法，新增 ALine 数据/分析管理接口。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from models.schemas import (
    AnalysisResult,
    CalibrationData,
    Curve,
    Dataset,
    DataFile,
    DataSeries,
    FigureConfig,
    FolderNode,
    DataFileNode,
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
    Project,
)

_ALINE_VERSION = "0.3"

_GROUP_TYPE_ALIASES = {
    "datasets": {"datasets", "dataset_set"},
    "images": {"images", "image_set"},
    "tools": {"tools", "tool_set"},
    "pipeline_group": {"pipeline_group"},
    "template_group": {"template_group", "figure_template_group"},
    "report_template_group": {"report_template_group"},
    "ai_group": {"ai_group"},
    "prompt_group": {"prompt_group"},
    "skill_group": {"skill_group"},
    "agent_group": {"agent_group"},
}


class ProjectManager:
    """项目管理器（全局单例）。

    支持多项目同时打开，维护当前项目概念。
    同时兼容 .pyline（旧格式）和 .aline / .pyline（含 ALine 扩展字段）。
    """

    def __init__(self) -> None:
        self._projects: List[Project] = []
        self._current_project_id: Optional[str] = None

    # ─────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────

    @property
    def projects(self) -> List[Project]:
        return self._projects

    @property
    def current_project(self) -> Optional[Project]:
        if self._current_project_id is None:
            return None
        return self.get_project(self._current_project_id)

    @property
    def current_project_id(self) -> Optional[str]:
        return self._current_project_id

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

        # 为新项目直接初始化 v0.3 树结构（不经过旧数据迁移路径）
        self._init_new_project_tree(project)

        if create_structure:
            base_dir = self._normalize_path(parent_dir or os.getcwd())
            safe_name = self._safe_filename(name)
            project_dir = Path(base_dir) / safe_name
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "files" / "images").mkdir(parents=True, exist_ok=True)
            project_file = project_dir / f"{safe_name}.pyline"
            self.save(str(project_file))

        return project

    def open(self, file_path: str) -> Project:
        file_path = self._normalize_path(file_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"项目文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        project = Project(**data)
        project.file_path = file_path
        project.is_modified = False

        existing = self.get_project(project.id)
        if existing:
            idx = self._projects.index(existing)
            self._projects[idx] = project
        else:
            self._projects.append(project)

        self._current_project_id = project.id

        # 迁移旧版本文件
        self.migrate_to_v2(project)
        self.migrate_to_v3(project)

        from core.recent_projects import add_recent
        add_recent(file_path, project.name)
        return project

    def open_file(self, file_path: str) -> Project:
        """Alias for open() for backward compatibility."""
        return self.open(file_path)

    def save(self, file_path: Optional[str] = None) -> str:
        if self.current_project is None:
            raise ValueError("没有当前项目")

        if file_path is None:
            file_path = self.current_project.file_path
            if file_path is None:
                raise ValueError("未指定保存路径")

        file_path = self._normalize_path(file_path)
        previous_path = self.current_project.file_path

        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        self.current_project.updated_at = datetime.now().isoformat()
        if self.current_project.aline_version is None:
            self.current_project.aline_version = _ALINE_VERSION

        # 保持向后兼容：同步 data_files → datasets
        self.sync_legacy_datasets(self.current_project)

        self._sync_project_backups(self.current_project, file_path, previous_path)

        data = self.current_project.model_dump()
        data.pop("file_path", None)
        data.pop("is_modified", None)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.current_project.file_path = file_path
        self.current_project.is_modified = False

        from core.recent_projects import add_recent
        add_recent(file_path, self.current_project.name)
        return file_path

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

    def add_image(self, image_path: str, name: Optional[str] = None) -> ImageWork:
        if self.current_project is None:
            raise ValueError("没有当前项目")
        image_path = self._normalize_path(image_path)
        image_work = ImageWork(
            id=str(uuid.uuid4()),
            name=name or os.path.basename(image_path),
            image_path=image_path,
            source_image_path=image_path,
        )
        if self.current_project.file_path:
            self._backup_image_for_project(image_work, self.current_project.file_path, None)
        self.current_project.images.append(image_work)
        self.current_project.is_modified = True
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
        project, image = self._get_image_owner(image_id)
        if project is None or image is None:
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
        """在当前项目中新建 Dataset。"""
        if self.current_project is None:
            return None
        ds = Dataset(id=str(uuid.uuid4()), name=name)
        self.current_project.datasets.append(ds)
        self.current_project.is_modified = True
        return ds

    def remove_dataset(self, dataset_id: str) -> bool:
        if self.current_project is None:
            return False
        before = len(self.current_project.datasets)
        self.current_project.datasets = [
            d for d in self.current_project.datasets if d.id != dataset_id
        ]
        changed = len(self.current_project.datasets) < before
        if changed:
            self.current_project.is_modified = True
        return changed

    def rename_dataset(self, dataset_id: str, new_name: str) -> bool:
        ds = self.current_project.find_dataset(dataset_id) if self.current_project else None
        if ds is None:
            return False
        ds.name = new_name
        self.current_project.is_modified = True  # type: ignore
        return True

    def add_series_to_dataset(self, dataset_id: str, series: DataSeries) -> bool:
        """将 DataSeries 添加到指定 Dataset。"""
        if self.current_project is None:
            return False
        ds = self.current_project.find_dataset(dataset_id)
        if ds is None:
            return False
        ds.series.append(series)
        self.current_project.is_modified = True
        return True

    def remove_series(self, dataset_id: str, series_id: str) -> bool:
        if self.current_project is None:
            return False
        ds = self.current_project.find_dataset(dataset_id)
        if ds is None:
            return False
        before = len(ds.series)
        ds.series = [s for s in ds.series if s.id != series_id]
        changed = len(ds.series) < before
        if changed:
            self.current_project.is_modified = True
        return changed

    def import_curve_as_series(self, curve_id: str, dataset_id: str) -> Optional[DataSeries]:
        """将 PyLine 图像提取曲线复制为 ALine DataSeries（核心互通方法）。

        复制 Curve.x_actual / y_actual 到新 DataSeries，保留来源引用。
        """
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
            source="pyline_curve_copy",
            source_curve_id=curve.id,
            x_label=x_label,
            y_label=y_label,
        )
        return series if self.add_series_to_dataset(dataset_id, series) else None

    # ─────────────────────────────────────────────
    # ALine 分析管理（新增）
    # ─────────────────────────────────────────────

    def add_analysis(self, result: AnalysisResult) -> bool:
        if self.current_project is None:
            return False
        self.current_project.analyses.append(result)
        self.current_project.is_modified = True
        return True

    def remove_analysis(self, analysis_id: str) -> bool:
        if self.current_project is None:
            return False
        before = len(self.current_project.analyses)
        self.current_project.analyses = [
            a for a in self.current_project.analyses if a.id != analysis_id
        ]
        changed = len(self.current_project.analyses) < before
        if changed:
            self.current_project.is_modified = True
        return changed

    # ─────────────────────────────────────────────
    # ALine 图表配置管理（新增）
    # ─────────────────────────────────────────────

    def save_figure_config(self, config: FigureConfig) -> bool:
        if self.current_project is None:
            return False
        # 替换同 id 或追加
        for i, existing in enumerate(self.current_project.figures):
            if existing.id == config.id:
                self.current_project.figures[i] = config
                self.current_project.is_modified = True
                return True
        self.current_project.figures.append(config)
        self.current_project.is_modified = True
        return True

    def remove_figure_config(self, figure_id: str) -> bool:
        if self.current_project is None:
            return False
        before = len(self.current_project.figures)
        self.current_project.figures = [
            f for f in self.current_project.figures if f.id != figure_id
        ]
        changed = len(self.current_project.figures) < before
        if changed:
            self.current_project.is_modified = True
        return changed

    # ─────────────────────────────────────────────
    # v0.2 迁移
    # ─────────────────────────────────────────────

    def migrate_to_v2(self, project: Optional[Project] = None) -> None:
        """将旧 v0.1/PyLine 项目迁移到 v0.2 树形结构。

        - 已有 tree 则跳过（幂等）
        - datasets → DataFile + DataFileNode（挂在"数据集"文件夹）
        - images   → ImageWorkNode（挂在"图片集"文件夹）
        """
        p = project or self.current_project
        if p is None:
            return
        if p.tree is not None:
            return

        p.tree = ProjectTree()
        order = 0

        # 数据集文件夹
        if p.datasets:
            ds_folder = FolderNode(name="数据集", order=order, group_type="datasets")
            p.tree.nodes.append(ds_folder)
            order += 1

            for ds in p.datasets:
                df = DataFile(
                    id=str(uuid.uuid4()),
                    name=ds.name,
                    series=list(ds.series),
                )
                p.data_files.append(df)
                df_node = DataFileNode(
                    name=ds.name,
                    parent_id=ds_folder.id,
                    data_file_id=df.id,
                    order=len(p.tree.nodes),
                )
                p.tree.nodes.append(df_node)

        # 图片集文件夹
        if p.images:
            img_folder = FolderNode(name="图片集", order=order, group_type="images")
            p.tree.nodes.append(img_folder)
            order += 1

            for img in p.images:
                img_node = ImageWorkNode(
                    name=img.name,
                    parent_id=img_folder.id,
                    image_work_id=img.id,
                    order=len(p.tree.nodes),
                )
                p.tree.nodes.append(img_node)

        # 工具集文件夹（空，占位）
        tools_folder = FolderNode(name="工具集", order=order, group_type="tools")
        p.tree.nodes.append(tools_folder)
        pipelines_folder = FolderNode(
            name="Pipelines", parent_id=tools_folder.id, order=0, group_type="pipeline_group"
        )
        p.tree.nodes.append(pipelines_folder)

        p.aline_version = "0.2"
        p.is_modified = True

    def migrate_to_v3(self, project: Optional[Project] = None) -> None:
        """将 v0.2 项目迁移到 v0.3。

        - 无 tree 则先执行 migrate_to_v2（幂等保证）
        - 为旧 FolderNode 补充 group_type（按名称推断）
        - 将 AIToolNode 转换为 AIPromptNode / AISkillNode / AIAgentNode
        - 确保工具集内存在 template_group / ai_group 子文件夹
        - 已是 v0.3 则跳过（幂等）
        """
        p = project or self.current_project
        if p is None:
            return
        if p.tree is None:
            self.migrate_to_v2(p)

        # 幂等检查
        if p.aline_version == "0.3":
            return

        # 为旧 FolderNode 推断 group_type
        _name_to_group = {
            "数据集": "datasets",
            "图片集": "images",
            "工具集": "tools",
            "Pipelines": "pipeline_group",
            "绘图模板": "template_group",
            "报告模板": "report_template_group",
            "AI 工具": "ai_group",
        }
        tools_folder_id = None
        for node in p.tree.nodes:
            if node.kind == "folder":
                if node.group_type is None:
                    node.group_type = _name_to_group.get(node.name)  # type: ignore[assignment]
                if node.group_type == "tools":
                    tools_folder_id = node.id

        # 把 AIToolNode 转换为具体类型
        new_nodes = []
        for node in p.tree.nodes:
            if node.kind == "ai_tool":
                if node.tool_type == "prompt":
                    new_nodes.append(AIPromptNode(
                        id=node.id, name=node.name,
                        parent_id=node.parent_id, order=node.order,
                        prompt_id=node.tool_id,
                    ))
                elif node.tool_type == "skill":
                    new_nodes.append(AISkillNode(
                        id=node.id, name=node.name,
                        parent_id=node.parent_id, order=node.order,
                        skill_id=node.tool_id,
                    ))
                elif node.tool_type == "agent":
                    new_nodes.append(AIAgentNode(
                        id=node.id, name=node.name,
                        parent_id=node.parent_id, order=node.order,
                        agent_id=node.tool_id,
                    ))
            else:
                new_nodes.append(node)
        p.tree.nodes = new_nodes

        # 确保工具集内存在 figure/report/ai 子文件夹
        if tools_folder_id:
            has_template = any(
                n.kind == "folder" and getattr(n, "group_type", None) in _GROUP_TYPE_ALIASES["template_group"]
                for n in p.tree.nodes
            )
            has_report = any(
                n.kind == "folder" and getattr(n, "group_type", None) in _GROUP_TYPE_ALIASES["report_template_group"]
                for n in p.tree.nodes
            )
            has_ai = any(
                n.kind == "folder" and getattr(n, "group_type", None) in _GROUP_TYPE_ALIASES["ai_group"]
                for n in p.tree.nodes
            )
            base_order = p.tree.get_siblings_max_order(tools_folder_id) + 1
            if not has_template:
                p.tree.nodes.append(FolderNode(
                    name="绘图模板", parent_id=tools_folder_id,
                    order=base_order, group_type="template_group",
                ))
                base_order += 1
            if not has_report:
                p.tree.nodes.append(FolderNode(
                    name="报告模板", parent_id=tools_folder_id,
                    order=base_order, group_type="report_template_group",
                ))
                base_order += 1
            if not has_ai:
                p.tree.nodes.append(FolderNode(
                    name="AI 工具", parent_id=tools_folder_id,
                    order=base_order, group_type="ai_group",
                ))

        p.aline_version = "0.3"
        p.is_modified = True

    def _init_new_project_tree(self, p: Project) -> None:
        """直接为新建（空）项目创建 v0.3 标准树结构。"""
        p.tree = ProjectTree()
        # 数据集文件夹
        ds_folder = FolderNode(name="数据集", order=0, group_type="datasets")
        p.tree.nodes.append(ds_folder)
        # 图片集文件夹
        img_folder = FolderNode(name="图片集", order=1, group_type="images")
        p.tree.nodes.append(img_folder)
        # 工具集文件夹 + 子文件夹
        tools_folder = FolderNode(name="工具集", order=2, group_type="tools")
        p.tree.nodes.append(tools_folder)
        p.tree.nodes.append(FolderNode(
            name="Pipelines", parent_id=tools_folder.id, order=0, group_type="pipeline_group"
        ))
        p.tree.nodes.append(FolderNode(
            name="绘图模板", parent_id=tools_folder.id, order=1, group_type="template_group"
        ))
        p.tree.nodes.append(FolderNode(
            name="报告模板", parent_id=tools_folder.id, order=2, group_type="report_template_group"
        ))
        p.tree.nodes.append(FolderNode(
            name="AI 工具", parent_id=tools_folder.id, order=3, group_type="ai_group"
        ))

    def sync_legacy_datasets(self, project: Optional[Project] = None) -> None:
        """保存前将 data_files[*].series 同步回 datasets（确保旧 PyLine 可读）。"""
        p = project or self.current_project
        if p is None:
            return
        # 清理旧 datasets 列表，重建
        existing_by_df_id = {df.id: df for df in p.data_files}
        # 找到所有 DataFileNode
        if p.tree is None:
            return
        for node in p.tree.nodes:
            if node.kind == "data_file":
                df = existing_by_df_id.get(node.data_file_id)
                if df is None:
                    continue
                # 查找 datasets 中是否已存在同名
                existing_ds = next((d for d in p.datasets if d.name == df.name), None)
                if existing_ds is None:
                    from models.schemas import Dataset
                    existing_ds = Dataset(name=df.name)
                    p.datasets.append(existing_ds)
                existing_ds.series = list(df.series)

    # ─────────────────────────────────────────────
    # v0.2 树节点 CRUD
    # ─────────────────────────────────────────────

    def add_folder(self, name: str, parent_id: Optional[str] = None, group_type: Optional[str] = None) -> Optional[FolderNode]:
        p = self.current_project
        if p is None:
            return None
        if p.tree is None:
            self.migrate_to_v2(p)
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore
        node = FolderNode(name=name, parent_id=parent_id, order=order, group_type=group_type)  # type: ignore[arg-type]
        p.tree.nodes.append(node)  # type: ignore
        p.is_modified = True
        return node

    def rename_node(self, node_id: str, new_name: str) -> bool:
        p = self.current_project
        if p is None or p.tree is None:
            return False
        node = p.tree.get_node(node_id)
        if node is None:
            return False
        node.name = new_name
        # 同步关联数据实体名称
        if node.kind == "data_file":
            df = p.find_data_file(node.data_file_id)
            if df:
                df.name = new_name
        elif node.kind == "pipeline":
            sp = p.find_saved_pipeline(node.pipeline_id)
            if sp:
                sp.name = new_name
        elif node.kind == "report_template":
            tmpl = p.find_report_template(node.template_id)
            if tmpl:
                tmpl.name = new_name
        elif node.kind == "ai_prompt":
            prompt = self.get_ai_prompt(node.prompt_id)
            if prompt:
                prompt.name = new_name
        elif node.kind == "ai_skill":
            skill = self.get_ai_skill(node.skill_id)
            if skill:
                skill.name = new_name
        elif node.kind == "ai_agent":
            agent = self.get_ai_agent(node.agent_id)
            if agent:
                agent.name = new_name
        p.is_modified = True
        return True

    def delete_node(self, node_id: str) -> bool:
        """删除节点及其所有子节点和关联数据实体。"""
        p = self.current_project
        if p is None or p.tree is None:
            return False

        def _collect_ids(nid: str) -> List[str]:
            ids = [nid]
            for child in p.tree.get_children(nid):  # type: ignore
                ids.extend(_collect_ids(child.id))
            return ids

        ids_to_delete = set(_collect_ids(node_id))

        for nid in ids_to_delete:
            node = p.tree.get_node(nid)
            if node is None:
                continue
            if node.kind == "data_file":
                p.data_files = [df for df in p.data_files if df.id != node.data_file_id]
            elif node.kind == "pipeline":
                p.saved_pipelines = [sp for sp in p.saved_pipelines if sp.id != node.pipeline_id]
            elif node.kind == "figure_template":
                p.figures = [f for f in p.figures if f.id != node.figure_id]
            elif node.kind == "report_template":
                p.report_templates = [t for t in p.report_templates if t.id != node.template_id]
            elif node.kind == "ai_prompt":
                p.ai_prompts = [x for x in p.ai_prompts if x.id != node.prompt_id]
            elif node.kind == "ai_skill":
                p.ai_skills = [x for x in p.ai_skills if x.id != node.skill_id]
            elif node.kind == "ai_agent":
                p.ai_agents = [x for x in p.ai_agents if x.id != node.agent_id]
            elif node.kind == "ai_tool":  # v0.2 legacy
                tool_id = getattr(node, "tool_id", "")
                p.ai_prompts = [x for x in p.ai_prompts if x.id != tool_id]
                p.ai_skills = [x for x in p.ai_skills if x.id != tool_id]
                p.ai_agents = [x for x in p.ai_agents if x.id != tool_id]

        p.tree.nodes = [n for n in p.tree.nodes if n.id not in ids_to_delete]
        p.is_modified = True
        return True

    def move_node(self, node_id: str, new_parent_id: Optional[str], new_order: int) -> bool:
        p = self.current_project
        if p is None or p.tree is None:
            return False
        node = p.tree.get_node(node_id)
        if node is None:
            return False
        node.parent_id = new_parent_id
        node.order = new_order
        p.is_modified = True
        return True

    def get_node_by_id(self, node_id: str):
        p = self.current_project
        if p is None or p.tree is None:
            return None
        return p.tree.get_node(node_id)

    def get_children(self, parent_id: Optional[str]):
        p = self.current_project
        if p is None or p.tree is None:
            return []
        return p.tree.get_children(parent_id)

    def _find_folder_by_name(self, name: str, parent_id: Optional[str] = None):
        """在树中按名称查找指定层级的文件夹节点。"""
        p = self.current_project
        if p is None or p.tree is None:
            return None
        for node in p.tree.nodes:
            if node.kind == "folder" and node.name == name and node.parent_id == parent_id:
                return node
        return None

    def _find_folder_by_group_type(self, group_type: str, parent_id: Optional[str] = None):
        """按 group_type 查找文件夹节点（更稳健，不依赖名称）。"""
        p = self.current_project
        if p is None or p.tree is None:
            return None
        candidates = _GROUP_TYPE_ALIASES.get(group_type, {group_type})
        for node in p.tree.nodes:
            if (node.kind == "folder"
                    and getattr(node, "group_type", None) in candidates
                    and (parent_id is None or node.parent_id == parent_id)):
                return node
        return None

    # ─────────────────────────────────────────────
    # v0.2 DataFile CRUD
    # ─────────────────────────────────────────────

    def add_data_file(self, df: DataFile, parent_id: Optional[str] = None) -> Optional[DataFileNode]:
        p = self.current_project
        if p is None:
            return None
        if p.tree is None:
            self.migrate_to_v2(p)
        p.data_files.append(df)
        # 默认挂在"数据集"文件夹下（优先 group_type，回退名称）
        if parent_id is None:
            ds_folder = self._find_folder_by_group_type("datasets") or self._find_folder_by_name("数据集")
            parent_id = ds_folder.id if ds_folder else None
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore
        node = DataFileNode(name=df.name, parent_id=parent_id, data_file_id=df.id, order=order)
        p.tree.nodes.append(node)  # type: ignore
        p.is_modified = True
        return node

    def get_data_file(self, df_id: str) -> Optional[DataFile]:
        p = self.current_project
        if p is None:
            return None
        return p.find_data_file(df_id)

    def add_series_to_data_file(self, data_file_id: str, series: DataSeries) -> bool:
        p = self.current_project
        if p is None:
            return False
        df = p.find_data_file(data_file_id)
        if df is None:
            return False
        df.series.append(series)
        p.is_modified = True
        return True

    # ─────────────────────────────────────────────
    # v0.2 Pipeline CRUD
    # ─────────────────────────────────────────────

    def add_saved_pipeline(
        self, name: str, ops: List[dict], description: str = "", parent_id: Optional[str] = None
    ) -> Optional[SavedPipeline]:
        p = self.current_project
        if p is None:
            return None
        if p.tree is None:
            self.migrate_to_v2(p)
        sp = SavedPipeline(name=name, ops=ops, description=description)
        p.saved_pipelines.append(sp)
        # 默认挂在工具集/Pipelines 文件夹
        if parent_id is None:
            pipelines_folder = self._find_folder_by_group_type("pipeline_group")
            if pipelines_folder is None:
                tools_folder = self._find_folder_by_group_type("tools") or self._find_folder_by_name("工具集")
                if tools_folder:
                    pipelines_folder = self._find_folder_by_name("Pipelines", tools_folder.id)
                    parent_id = pipelines_folder.id if pipelines_folder else tools_folder.id
            else:
                parent_id = pipelines_folder.id
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore
        node = PipelineNode(name=name, parent_id=parent_id, pipeline_id=sp.id, order=order)
        p.tree.nodes.append(node)  # type: ignore
        p.is_modified = True
        return sp

    def load_pipeline(self, pipeline_id: str) -> List[dict]:
        """返回 ops 列表；未找到时返回空列表。"""
        p = self.current_project
        if p is None:
            return []
        sp = p.find_saved_pipeline(pipeline_id)
        return list(sp.ops) if sp else []

    def update_saved_pipeline(
        self,
        pipeline_id: str,
        *,
        name: Optional[str] = None,
        ops: Optional[List[dict]] = None,
        description: Optional[str] = None,
    ) -> bool:
        p = self.current_project
        if p is None:
            return False
        sp = p.find_saved_pipeline(pipeline_id)
        if sp is None:
            return False
        if name is not None:
            sp.name = name
        if ops is not None:
            sp.ops = list(ops)
        if description is not None:
            sp.description = description
        if name is not None and p.tree is not None:
            for node in p.tree.nodes:
                if node.kind == "pipeline" and node.pipeline_id == pipeline_id:
                    node.name = name
                    break
        p.is_modified = True
        return True

    def delete_saved_pipeline(self, pipeline_id: str) -> bool:
        p = self.current_project
        if p is None:
            return False
        before = len(p.saved_pipelines)
        p.saved_pipelines = [sp for sp in p.saved_pipelines if sp.id != pipeline_id]
        if len(p.saved_pipelines) < before:
            # 删除对应树节点
            if p.tree:
                p.tree.nodes = [
                    n for n in p.tree.nodes
                    if not (n.kind == "pipeline" and n.pipeline_id == pipeline_id)
                ]
            p.is_modified = True
            return True
        return False

    # ─────────────────────────────────────────────
    # v0.2 FigureTemplate CRUD
    # ─────────────────────────────────────────────

    def add_figure_template(self, config: FigureConfig, parent_id: Optional[str] = None) -> Optional[FigureTemplateNode]:
        p = self.current_project
        if p is None:
            return None
        if p.tree is None:
            self.migrate_to_v2(p)
        # 保存 FigureConfig（复用现有 save_figure_config）
        self.save_figure_config(config)
        if parent_id is None:
            template_folder = self._find_folder_by_group_type("template_group")
            if template_folder is None:
                tools_folder = self._find_folder_by_group_type("tools") or self._find_folder_by_name("工具集")
                parent_id = tools_folder.id if tools_folder else None
            else:
                parent_id = template_folder.id
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore
        node = FigureTemplateNode(name=config.name, parent_id=parent_id, figure_id=config.id, order=order)
        p.tree.nodes.append(node)  # type: ignore
        p.is_modified = True
        return node

    def delete_figure_template(self, figure_id: str) -> bool:
        """删除 FigureConfig 及对应树节点。"""
        p = self.current_project
        if p is None:
            return False
        before = len(p.figures)
        p.figures = [f for f in p.figures if f.id != figure_id]
        if len(p.figures) < before:
            if p.tree:
                p.tree.nodes = [
                    n for n in p.tree.nodes
                    if not (n.kind == "figure_template" and n.figure_id == figure_id)
                ]
            p.is_modified = True
            return True
        return False

    def _report_template_parent_id(self) -> Optional[str]:
        folder = self._find_folder_by_group_type("report_template_group")
        return folder.id if folder else None

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
        p = self.current_project
        if p is None:
            return None
        if p.tree is None:
            self.migrate_to_v2(p)
        tmpl = ReportTemplate(name=name, content=content, is_builtin=is_builtin)
        p.report_templates.append(tmpl)
        if parent_id is None:
            parent_id = self._report_template_parent_id()
            if parent_id is None:
                tools_folder = self._find_folder_by_group_type("tools") or self._find_folder_by_name("工具集")
                parent_id = tools_folder.id if tools_folder else None
        order = p.tree.get_siblings_max_order(parent_id) + 1  # type: ignore[union-attr]
        p.tree.nodes.append(ReportTemplateNode(  # type: ignore[union-attr]
            name=name,
            parent_id=parent_id,
            template_id=tmpl.id,
            order=order,
        ))
        p.is_modified = True
        return tmpl

    def get_report_template(self, template_id: str) -> Optional[ReportTemplate]:
        p = self.current_project
        if p is None:
            return None
        return p.find_report_template(template_id)

    def update_report_template(self, template_id: str, name: Optional[str] = None, content: Optional[str] = None) -> bool:
        p = self.current_project
        if p is None:
            return False
        tmpl = p.find_report_template(template_id)
        if tmpl is None:
            return False
        if name is not None:
            tmpl.name = name
            if p.tree is not None:
                for node in p.tree.nodes:
                    if node.kind == "report_template" and node.template_id == template_id:
                        node.name = name
                        break
        if content is not None:
            tmpl.content = content
        p.is_modified = True
        return True

    def delete_report_template(self, template_id: str) -> bool:
        p = self.current_project
        if p is None:
            return False
        tmpl = p.find_report_template(template_id)
        if tmpl is None or tmpl.is_builtin:
            return False
        p.report_templates = [t for t in p.report_templates if t.id != template_id]
        if p.tree is not None:
            p.tree.nodes = [
                n for n in p.tree.nodes
                if not (n.kind == "report_template" and n.template_id == template_id)
            ]
        p.is_modified = True
        return True

    # ─────────────────────────────────────────────
    # v0.3 AI 工具 CRUD
    # ─────────────────────────────────────────────

    def _ai_group_parent_id(self) -> Optional[str]:
        folder = self._find_folder_by_group_type("ai_group")
        return folder.id if folder else None

    def add_ai_prompt(self, name: str, content: str = "", description: str = "") -> Optional[AIPrompt]:
        p = self.current_project
        if p is None:
            return None
        prompt = AIPrompt(name=name, content=content, description=description)
        p.ai_prompts.append(prompt)
        if p.tree is not None:
            parent_id = self._ai_group_parent_id()
            order = p.tree.get_siblings_max_order(parent_id) + 1
            p.tree.nodes.append(AIPromptNode(
                name=name, parent_id=parent_id, prompt_id=prompt.id, order=order
            ))
        p.is_modified = True
        return prompt

    def get_ai_prompt(self, prompt_id: str) -> Optional[AIPrompt]:
        p = self.current_project
        if p is None:
            return None
        for prompt in p.ai_prompts:
            if prompt.id == prompt_id:
                return prompt
        return None

    def update_ai_prompt(self, prompt_id: str, name: Optional[str] = None, content: Optional[str] = None, description: Optional[str] = None) -> bool:
        prompt = self.get_ai_prompt(prompt_id)
        if prompt is None:
            return False
        if name is not None:
            prompt.name = name
        if content is not None:
            prompt.content = content
        if description is not None:
            prompt.description = description
        if self.current_project:
            self.current_project.is_modified = True
        return True

    def delete_ai_prompt(self, prompt_id: str) -> bool:
        p = self.current_project
        if p is None:
            return False
        before = len(p.ai_prompts)
        p.ai_prompts = [x for x in p.ai_prompts if x.id != prompt_id]
        if len(p.ai_prompts) < before:
            if p.tree:
                p.tree.nodes = [
                    n for n in p.tree.nodes
                    if not (n.kind == "ai_prompt" and n.prompt_id == prompt_id)
                ]
            p.is_modified = True
            return True
        return False

    def add_ai_skill(self, name: str, code: str = "", description: str = "") -> Optional[AISkill]:
        p = self.current_project
        if p is None:
            return None
        skill = AISkill(name=name, code=code, description=description)
        p.ai_skills.append(skill)
        if p.tree is not None:
            parent_id = self._ai_group_parent_id()
            order = p.tree.get_siblings_max_order(parent_id) + 1
            p.tree.nodes.append(AISkillNode(
                name=name, parent_id=parent_id, skill_id=skill.id, order=order
            ))
        p.is_modified = True
        return skill

    def get_ai_skill(self, skill_id: str) -> Optional[AISkill]:
        p = self.current_project
        if p is None:
            return None
        for skill in p.ai_skills:
            if skill.id == skill_id:
                return skill
        return None

    def delete_ai_skill(self, skill_id: str) -> bool:
        p = self.current_project
        if p is None:
            return False
        before = len(p.ai_skills)
        p.ai_skills = [x for x in p.ai_skills if x.id != skill_id]
        if len(p.ai_skills) < before:
            if p.tree:
                p.tree.nodes = [
                    n for n in p.tree.nodes
                    if not (n.kind == "ai_skill" and n.skill_id == skill_id)
                ]
            p.is_modified = True
            return True
        return False

    def add_ai_agent(self, name: str, system_prompt: str = "", description: str = "") -> Optional[AIAgent]:
        p = self.current_project
        if p is None:
            return None
        agent = AIAgent(name=name, system_prompt=system_prompt, description=description)
        p.ai_agents.append(agent)
        if p.tree is not None:
            parent_id = self._ai_group_parent_id()
            order = p.tree.get_siblings_max_order(parent_id) + 1
            p.tree.nodes.append(AIAgentNode(
                name=name, parent_id=parent_id, agent_id=agent.id, order=order
            ))
        p.is_modified = True
        return agent

    def get_ai_agent(self, agent_id: str) -> Optional[AIAgent]:
        p = self.current_project
        if p is None:
            return None
        for agent in p.ai_agents:
            if agent.id == agent_id:
                return agent
        return None

    def delete_ai_agent(self, agent_id: str) -> bool:
        p = self.current_project
        if p is None:
            return False
        before = len(p.ai_agents)
        p.ai_agents = [x for x in p.ai_agents if x.id != agent_id]
        if len(p.ai_agents) < before:
            if p.tree:
                p.tree.nodes = [
                    n for n in p.tree.nodes
                    if not (n.kind == "ai_agent" and n.agent_id == agent_id)
                ]
            p.is_modified = True
            return True
        return False

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
                    source="pyline_curve_copy",
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
                            source="pyline_curve_copy",
                            source_curve_id=c.id,
                        )
            return None

        return None

    def get_all_series_from_node(self, kind: str, node_id: str) -> list:
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
                                source="pyline_curve_copy",
                                source_curve_id=c.id,
                            ))
                    return result
            return []

        return []

    # ─────────────────────────────────────────────
    # 可视化数据聚合（供各页面调用）
    # ─────────────────────────────────────────────

    def collect_all_series(self, project: Optional[Project] = None):
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

    def _backup_filename(self, image: ImageWork, source_suffix: str) -> str:
        name = self._safe_filename(image.name)
        p = Path(name)
        if p.suffix:
            return name
        suffix = (source_suffix or ".img").lower()
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

    def _project_assets_dir(self, project_file_path: str) -> Path:
        return Path(project_file_path).parent / "files" / "images"

    def _backup_image_for_project(
        self,
        image: ImageWork,
        project_file_path: str,
        source_project: Optional[Project],
    ) -> None:
        source_abs = self.resolve_image_path(image, source_project)
        if not source_abs:
            return
        source_path = Path(source_abs)
        if not source_path.exists():
            raise FileNotFoundError(f"图像文件不存在: {source_abs}")
        backup_dir = self._project_assets_dir(project_file_path)
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_filename = self._backup_filename(image, source_path.suffix)
        backup_path = backup_dir / backup_filename
        current_backup_abs = ""
        if image.image_path and not Path(image.image_path).is_absolute():
            current_backup_abs = str(
                (Path(project_file_path).parent / image.image_path).resolve()
            )
        if backup_path.exists() and str(backup_path.resolve()) != current_backup_abs:
            backup_path = self._ensure_unique_path(backup_path, image.id)
        if source_path.resolve() != backup_path.resolve():
            shutil.copy2(source_path, backup_path)
        rel_path = backup_path.relative_to(Path(project_file_path).parent)
        image.image_path = rel_path.as_posix()
        image.source_image_path = str(source_path)

    def _sync_project_backups(
        self,
        project: Project,
        target_file_path: str,
        source_file_path: Optional[str],
    ) -> None:
        source_project = project.model_copy(deep=False)
        source_project.file_path = source_file_path
        for image in project.images:
            self._backup_image_for_project(image, target_file_path, source_project)

    def _delete_backup_if_managed(self, image: ImageWork, project: Project) -> None:
        if not project.file_path:
            return
        raw_path = image.image_path or ""
        if not raw_path or Path(raw_path).is_absolute():
            return
        backup_path = Path(project.file_path).parent / raw_path
        try:
            if backup_path.exists():
                backup_path.unlink()
        except OSError:
            pass


# 全局单例
project_manager = ProjectManager()
