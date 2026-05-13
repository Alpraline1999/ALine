from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from models.schemas import DataFile, DataFileNode, DataSeries, Project


@dataclass(slots=True)
class ProjectAssetService:
    get_current_project: Callable[[], Project | None]
    clear_last_error: Callable[[], None]
    ensure_project_tree: Callable[[Project], None]
    ensure_unique_tree_child_name: Callable[..., bool]
    next_unique_tree_child_name: Callable[..., str]
    ensure_unique_series_name: Callable[..., bool]
    ensure_unique_curve_name: Callable[..., bool]
    find_folder_by_group_type: Callable[[str], Any | None]
    find_folder_by_name: Callable[[str], Any | None]
    get_image: Callable[[str], Any | None]
    sync_legacy_datasets: Callable[[Project | None], None]

    def add_data_file(
        self,
        data_file: DataFile,
        parent_id: str | None = None,
        *,
        auto_rename_on_conflict: bool = False,
    ) -> DataFileNode | None:
        self.clear_last_error()
        project = self.get_current_project()
        if project is None:
            return None
        self.ensure_project_tree(project)
        if project.tree is None:
            return None
        if parent_id is None:
            ds_folder = self.find_folder_by_group_type("datasets") or self.find_folder_by_name("数据集")
            parent_id = None if ds_folder is None else ds_folder.id
        if auto_rename_on_conflict:
            data_file.name = self.next_unique_tree_child_name(parent_id, data_file.name, node_kind="data_file", project=project)
        if not self.ensure_unique_tree_child_name(parent_id, data_file.name, node_kind="data_file", project=project):
            return None
        project.data_files.append(data_file)
        order = project.tree.get_siblings_max_order(parent_id) + 1
        node = DataFileNode(name=data_file.name, parent_id=parent_id, data_file_id=data_file.id, order=order)
        project.tree.nodes.append(node)
        self.sync_legacy_datasets(project)
        project.is_modified = True
        return node

    def get_data_file(self, data_file_id: str) -> DataFile | None:
        project = self.get_current_project()
        if project is None:
            return None
        return project.find_data_file(data_file_id)

    def add_series_to_data_file(self, data_file_id: str, series: DataSeries) -> bool:
        self.clear_last_error()
        project = self.get_current_project()
        if project is None:
            return False
        data_file = project.find_data_file(data_file_id)
        if data_file is None:
            return False
        if not self.ensure_unique_series_name(data_file.name, data_file.series, series.name, owner_label="数据文件"):
            return False
        data_file.series.append(series)
        self.sync_legacy_datasets(project)
        project.is_modified = True
        return True

    def rename_series(self, series_id: str, new_name: str) -> bool:
        self.clear_last_error()
        owner_kind, owner, series = self._find_series_owner(series_id)
        if owner_kind is None or owner is None or series is None:
            return False
        owner_label = "数据文件" if owner_kind == "data_file" else "数据集"
        if not self.ensure_unique_series_name(
            getattr(owner, "name", ""),
            list(getattr(owner, "series", [])),
            new_name,
            owner_label=owner_label,
            exclude_series_id=series.id,
        ):
            return False
        series.name = new_name
        project = self.get_current_project()
        if project is not None:
            self.sync_legacy_datasets(project)
            project.is_modified = True
        return True

    def delete_series(self, series_id: str) -> bool:
        owner_kind, owner, _series = self._find_series_owner(series_id)
        project = self.get_current_project()
        if owner_kind is None or owner is None or project is None:
            return False
        before = len(owner.series)
        owner.series = [item for item in owner.series if item.id != series_id]
        changed = len(owner.series) < before
        if changed:
            self.sync_legacy_datasets(project)
            project.is_modified = True
        return changed

    def move_series_to_data_file(self, series_id: str, target_data_file_id: str) -> bool:
        self.clear_last_error()
        project = self.get_current_project()
        if project is None:
            return False
        target = project.find_data_file(target_data_file_id)
        owner_kind, owner, series = self._find_series_owner(series_id)
        if target is None or owner_kind is None or owner is None or series is None:
            return False
        if owner_kind == "data_file" and owner.id == target.id:
            return False
        if not self.ensure_unique_series_name(target.name, target.series, series.name, owner_label="数据文件"):
            return False
        owner.series = [item for item in owner.series if item.id != series_id]
        target.series.append(series)
        self.sync_legacy_datasets(project)
        project.is_modified = True
        return True

    def rename_curve(self, curve_id: str, new_name: str) -> bool:
        self.clear_last_error()
        image, curve = self._find_curve_owner(curve_id)
        if image is None or curve is None:
            return False
        if not self.ensure_unique_curve_name(image.name, image.curves, new_name, exclude_curve_id=curve.id):
            return False
        curve.name = new_name
        project = self.get_current_project()
        if project is not None:
            project.is_modified = True
        return True

    def delete_curve(self, curve_id: str) -> bool:
        image, _curve = self._find_curve_owner(curve_id)
        project = self.get_current_project()
        if image is None or project is None:
            return False
        before = len(image.curves)
        image.curves = [item for item in image.curves if item.id != curve_id]
        changed = len(image.curves) < before
        if changed:
            project.is_modified = True
        return changed

    def move_curve_to_image(self, curve_id: str, target_image_id: str) -> bool:
        self.clear_last_error()
        project = self.get_current_project()
        if project is None:
            return False
        source_image, curve = self._find_curve_owner(curve_id)
        target_image = self.get_image(target_image_id)
        if source_image is None or curve is None or target_image is None:
            return False
        if source_image.id == target_image.id:
            return False
        if not self.ensure_unique_curve_name(target_image.name, target_image.curves, curve.name):
            return False
        source_image.curves = [item for item in source_image.curves if item.id != curve_id]
        target_image.curves.append(curve)
        project.is_modified = True
        return True

    def _find_series_owner(self, series_id: str) -> tuple[Optional[str], Any, Optional[DataSeries]]:
        project = self.get_current_project()
        if project is None:
            return None, None, None
        for data_file in project.data_files:
            for series in data_file.series:
                if series.id == series_id:
                    return "data_file", data_file, series
        return None, None, None

    def _find_curve_owner(self, curve_id: str) -> tuple[Optional[Any], Optional[Any]]:
        project = self.get_current_project()
        if project is None:
            return None, None
        for image in project.images:
            for curve in image.curves:
                if curve.id == curve_id:
                    return image, curve
        return None, None
