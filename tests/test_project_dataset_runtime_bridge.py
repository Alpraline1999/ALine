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
        self.sync_calls: list[str] = []

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
            sync_legacy_datasets=lambda _project: self.sync_calls.append("sync"),
        )

    def test_datafile_write_path_triggers_legacy_dataset_sync(self) -> None:
        service = self._make_service()
        service.add_data_file(DataFile(id="df-1", name="A"))
        service.add_series_to_data_file("df-1", DataSeries(id="s1", name="S1"))

        self.assertEqual(["sync", "sync"], self.sync_calls)

    def test_series_owner_no_longer_resolves_legacy_dataset_only_payloads(self) -> None:
        self.project.datasets.append(types.SimpleNamespace(id="legacy-ds", name="Legacy", series=[DataSeries(id="s1", name="Old")]))
        service = self._make_service()

        changed = service.rename_series("s1", "New")

        self.assertFalse(changed)
        self.assertEqual([], self.sync_calls)


if __name__ == "__main__":
    unittest.main()
