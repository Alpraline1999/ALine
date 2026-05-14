from __future__ import annotations

import importlib.util
import sys
import types
import unittest


def _load_project_asset_service_module():
    original_models = sys.modules.get("models.schemas")
    fake_models = types.ModuleType("models.schemas")

    class DataSeries:
        def __init__(self, **data) -> None:
            self.id = data.get("id", "series-1")
            self.name = data.get("name", "")

    class DataFile:
        def __init__(self, **data) -> None:
            self.id = data.get("id", "df-1")
            self.name = data.get("name", "")
            self.series = list(data.get("series", []))

    class DataFileNode:
        kind = "data_file"

        def __init__(self, **data) -> None:
            self.id = data.get("id", "node-1")
            self.name = data.get("name", "")
            self.parent_id = data.get("parent_id")
            self.data_file_id = data.get("data_file_id", "df-1")
            self.order = data.get("order", 0)

    class _Tree:
        def __init__(self) -> None:
            self.nodes = []

        def get_siblings_max_order(self, _parent_id):
            return len(self.nodes)

    class Project:
        def __init__(self) -> None:
            self.id = "project-1"
            self.tree = _Tree()
            self.data_files = []
            self.datasets = []
            self.images = []
            self.is_modified = False

        def find_data_file(self, data_file_id: str):
            return next((item for item in self.data_files if item.id == data_file_id), None)

    fake_models.DataFile = DataFile
    fake_models.DataFileNode = DataFileNode
    fake_models.DataSeries = DataSeries
    fake_models.Project = Project
    sys.modules["models.schemas"] = fake_models

    spec = importlib.util.spec_from_file_location(
        "test_project_dataset_runtime_bridge_module",
        "/home/alpraline/Projects/Python/ALine/core/project_asset_service.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if original_models is None:
            sys.modules.pop("models.schemas", None)
        else:
            sys.modules["models.schemas"] = original_models
    module.TestProject = Project
    return module


module = _load_project_asset_service_module()
ProjectAssetService = module.ProjectAssetService
DataFile = module.DataFile
DataSeries = module.DataSeries
TestProject = module.TestProject


class TestProjectDatasetRuntimeBridge(unittest.TestCase):
    def setUp(self) -> None:
        self.project = TestProject()

    def _make_service(self) -> ProjectAssetService:
        return ProjectAssetService(
            get_current_project=lambda: self.project,
            clear_last_error=lambda: None,
            ensure_project_tree=lambda _project: None,
            ensure_unique_tree_child_name=lambda *_args, **_kwargs: True,
            next_unique_tree_child_name=lambda _parent_id, name, **_kwargs: name,
            ensure_unique_series_name=lambda *_args, **_kwargs: True,
            ensure_unique_curve_name=lambda *_args, **_kwargs: True,
            find_folder_by_group_type=lambda _group: types.SimpleNamespace(id="datasets-root"),
            find_folder_by_name=lambda _name: None,
        get_image=lambda _image_id: None,
        )

    def test_add_data_file_and_add_series_work_without_legacy_sync(self) -> None:
        service = self._make_service()
        service.add_data_file(DataFile(id="df-1", name="A"))
        service.add_series_to_data_file("df-1", DataSeries(id="s1", name="S1"))

        self.assertTrue(len(self.project.data_files) > 0)


if __name__ == "__main__":
    unittest.main()
