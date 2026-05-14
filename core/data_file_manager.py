"""
DataFileManager — DataFile/DataSeries/SourceFileAsset 的导入、删除、查找。

从 ProjectManager 中提取，持有 project_manager 引用并通过
project_manager.current_project 获取当前项目。
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, cast, Iterator, List, Optional, TYPE_CHECKING

from models.schemas import (
    DataFile,
    DataFileNode,
    DataSeries,
    Dataset,
    FolderNode,
    Project,
    SourceFileAsset,
    SourceFileNode,
)

if TYPE_CHECKING:
    from core.project_manager import ProjectManager


class DataFileManager:
    """DataFile / DataSeries / SourceFileAsset 的管理器。

    需要 project_manager.current_project 获取当前项目。
    初始化后绑定到 project_manager 实例。
    """

    def __init__(self, project_manager: "ProjectManager") -> None:
        self._pm = project_manager

    @property
    def _project(self) -> Any:
        return self._pm.current_project

    # ─────────────────────────────────────────────
    # DataFile 导入
    # ─────────────────────────────────────────────

    def import_data_file(
        self,
        path: str,
        target_data_file_id: Optional[str] = None,
        create_dataset: bool = False,
    ) -> DataFile:
        """导入数据文件。

        1. 检测文件格式（CSV/Excel/JSON/NumPy）
        2. 解析为 List[DataSeries]
        3. 创建或追加到 DataFile
        4. 注册到项目树的 datasets 组
        5. 返回创建的 DataFile
        """
        from core.data_operations import import_csv, import_excel, import_json, import_numpy

        project = self._project
        if project is None:
            raise ValueError("没有当前项目")

        file_path = os.path.abspath(path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        ext = Path(file_path).suffix.lower()
        if ext in ('.csv', '.txt', '.dat', '.tsv'):
            series_list = import_csv(file_path)
        elif ext in ('.xls', '.xlsx'):
            series_list = import_excel(file_path)
        elif ext == '.json':
            series_list = import_json(file_path)
        elif ext == '.npy':
            series_list = import_numpy(file_path)
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

        if not series_list:
            raise ValueError("文件中没有可导入的数据列")

        # 在每 series 上记录来源
        for s in series_list:
            if not s.source_file_path:
                s.source_file_path = file_path

        # 创建或追加到目标 DataFile
        if target_data_file_id:
            data_file = self.find_data_file(target_data_file_id)
            if data_file is None:
                raise ValueError(f"目标 DataFile 不存在: {target_data_file_id}")
            data_file.series.extend(series_list)
        else:
            data_file = DataFile(
                name=Path(file_path).stem,
                source_path=os.path.abspath(file_path),
                series=series_list,
            )
            project.data_files.append(data_file)

        # 更新项目树
        self._ensure_tree_groups()
        datasets_group = self._pm._find_folder_by_group_type("datasets")

        if datasets_group is not None and project.tree is not None:
            # 若已存在同名 data_file 节点，不重复创建
            existing = project.tree.find_linked_node(
                "data_file", "data_file_id", data_file.id
            )
            if existing is None:
                order = project.tree.get_siblings_max_order(datasets_group.id) + 1
                node = DataFileNode(
                    name=data_file.name,
                    parent_id=datasets_group.id,
                    data_file_id=data_file.id,
                    order=order,
                )
                project.tree.nodes.append(node)

        project.is_modified = True
        return data_file

    # ─────────────────────────────────────────────
    # SourceFile 导入
    # ─────────────────────────────────────────────

    def import_source_file(self, path: str) -> SourceFileAsset:
        """复制源文件到项目目录并注册。

        简化版：将外部文件复制到项目的 source_files 目录，
        创建 SourceFileAsset 并注册到项目树。
        """
        project = self._project
        if project is None:
            raise ValueError("没有当前项目")

        file_path = os.path.abspath(path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"源文件不存在: {file_path}")

        source_path = Path(file_path)
        source_name = source_path.name

        # 确保树结构就绪
        self._ensure_tree_groups()
        source_root = self._pm._find_folder_by_group_type("source_files")

        # 创建 SourceFileAsset
        asset = SourceFileAsset(
            id=str(uuid.uuid4()),
            name=source_name,
            file_path=file_path,
            source_file_path=file_path,
            file_size=source_path.stat().st_size,
        )

        # 如果项目有保存路径，复制到项目目录
        if project.file_path:
            self._pm._backup_source_file_for_project(
                asset,
                project.file_path,
                None,
                target_folder_id=source_root.id if source_root else None,
            )

        project.source_files.append(asset)

        # 在项目树中添加 SourceFileNode
        if source_root is not None and project.tree is not None:
            order = project.tree.get_siblings_max_order(source_root.id) + 1
            node = SourceFileNode(
                name=asset.name,
                parent_id=source_root.id,
                source_file_id=asset.id,
                order=order,
            )
            project.tree.nodes.append(node)

        project.is_modified = True
        return asset

    # ─────────────────────────────────────────────
    # 删除
    # ─────────────────────────────────────────────

    def delete_data_file(self, data_file_id: str) -> bool:
        """删除 DataFile 及其在树中的节点。"""
        project = self._project
        if project is None:
            return False

        data_file = project.find_data_file(data_file_id)
        if data_file is None:
            return False

        # 从 project.data_files 移除
        project.data_files = [df for df in project.data_files if df.id != data_file_id]

        # 从项目树移除对应节点
        if project.tree is not None:
            project.tree.nodes = [
                node for node in project.tree.nodes
                if not (node.kind == "data_file" and node.data_file_id == data_file_id)
            ]

        project.is_modified = True
        return True

    def delete_source_file(self, source_file_id: str) -> bool:
        """删除 SourceFileAsset 及其在树中的节点。"""
        project = self._project
        if project is None:
            return False

        source_file = project.find_source_file(source_file_id)
        if source_file is None:
            return False

        # 尝试删除备份文件
        self._pm._delete_source_file_backup_if_managed(source_file, project)

        # 从 project.source_files 移除
        project.source_files = [
            sf for sf in project.source_files if sf.id != source_file_id
        ]

        # 从项目树移除对应节点
        if project.tree is not None:
            project.tree.nodes = [
                node for node in project.tree.nodes
                if not (node.kind == "source_file" and node.source_file_id == source_file_id)
            ]

        project.is_modified = True
        return True

    # ─────────────────────────────────────────────
    # Dataset 管理（兼容层）
    # ─────────────────────────────────────────────

    def add_dataset(self, name: str, parent_id: Optional[str] = None) -> Optional[Dataset]:
        """创建 Dataset (兼容入口：实际创建 DataFile 并同步 datasets 镜像)。"""
        data_file_node = self._pm.add_data_file(
            DataFile(id=str(uuid.uuid4()), name=name),
            parent_id=parent_id,
        )
        if data_file_node is None or self._project is None:
            return None
        dataset = self._project.find_dataset(data_file_node.data_file_id) if self._project else None
        return cast(Optional[Dataset], dataset)

    def add_series_to_dataset(self, dataset_id: str, series: DataSeries) -> bool:
        """向 Dataset 添加 DataSeries（实际追加到 DataFile）。"""
        return self.add_series_to_data_file(dataset_id, series)

    def remove_series_from_dataset(self, dataset_id: str, series_id: str) -> bool:
        """从 Dataset 移除 DataSeries。"""
        del dataset_id
        return self._pm.delete_series(series_id)

    # ─────────────────────────────────────────────
    # 查找
    # ─────────────────────────────────────────────

    def find_series(self, series_id: str) -> Optional[DataSeries]:
        """在所有 DataFile 中查找 DataSeries。"""
        project = self._project
        if project is None:
            return None
        for data_file in project.data_files:
            for series in data_file.series:
                if series.id == series_id:
                    return cast(DataSeries, series)
        return None

    def find_data_file(self, data_file_id: str) -> Optional[DataFile]:
        """按 ID 查找 DataFile。"""
        project = self._project
        if project is None:
            return None
        return cast(DataFile, project.find_data_file(data_file_id))

    def find_source_file(self, source_file_id: str) -> Optional[SourceFileAsset]:
        """按 ID 查找 SourceFileAsset。"""
        project = self._project
        if project is None:
            return None
        return cast(SourceFileAsset, project.find_source_file(source_file_id))

    def get_data_file(self, data_file_id: str) -> Optional[DataFile]:
        """别名：按 ID 查找 DataFile。"""
        return self.find_data_file(data_file_id)

    # ─────────────────────────────────────────────
    # 迭代
    # ─────────────────────────────────────────────

    def iter_all_series(self) -> Iterator[DataSeries]:
        """遍历所有 DataFile 下的所有 DataSeries。"""
        project = self._project
        if project is None:
            return
        for data_file in project.data_files:
            yield from data_file.series

    # ─────────────────────────────────────────────
    # DataSeries 追加
    # ─────────────────────────────────────────────

    def add_series_to_data_file(self, data_file_id: str, series: DataSeries) -> bool:
        """向已存在的 DataFile 追加 DataSeries。"""
        return self._pm._project_asset_service.add_series_to_data_file(
            data_file_id, series
        )

    # ─────────────────────────────────────────────
    # 内部辅助
    # ─────────────────────────────────────────────

    def _ensure_tree_groups(self) -> None:
        """确保项目树组已初始化。"""
        project = self._project
        if project is None:
            return
        self._pm._ensure_project_tree_groups(project)
