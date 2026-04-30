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
            self.nodes: list[object] = []

        def get_siblings_max_order(self, _parent_id):
            return len(self.nodes)

    class _Dataset:
        def __init__(self, name: str, series=None) -> None:
            self.id = f"ds-{name}"
            self.name = name
            self.series = list(series or [])

    class _Curve:
        def __init__(self, curve_id: str, name: str) -> None:
            self.id = curve_id
            self.name = name

    class _Image:
        def __init__(self, image_id: str, name: str, curves=None) -> None:
            self.id = image_id
            self.name = name
            self.curves = list(curves or [])

    class Project:
        def __init__(self) -> None:
            self.id = "project-1"
            self.tree = _Tree()
            self.data_files: list[DataFile] = []
            self.datasets: list[_Dataset] = []
            self.images: list[_Image] = []
            self.is_modified = False

        def find_data_file(self, data_file_id: str):
            return next((item for item in self.data_files if item.id == data_file_id), None)

    fake_models.DataFile = DataFile
    fake_models.DataFileNode = DataFileNode
    fake_models.DataSeries = DataSeries
    fake_models.Project = Project
    sys.modules["models.schemas"] = fake_models

    spec = importlib.util.spec_from_file_location(
        "test_project_asset_service_module",
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
    module.TestDataset = _Dataset
    module.TestCurve = _Curve
    module.TestImage = _Image
    module.TestProject = Project
    return module


module = _load_project_asset_service_module()
ProjectAssetService = module.ProjectAssetService
DataFile = module.DataFile
DataSeries = module.DataSeries
TestDataset = module.TestDataset
TestCurve = module.TestCurve
TestImage = module.TestImage
TestProject = module.TestProject


class TestProjectAssetService(unittest.TestCase):
    def setUp(self) -> None:
        self.project = TestProject()
        self.calls: list[object] = []

    def _make_service(self, **overrides):
        defaults = dict(
            get_current_project=lambda: self.project,
            clear_last_error=lambda: self.calls.append("clear"),
            ensure_project_tree=lambda project: self.calls.append(("ensure_tree", project.id)),
            ensure_unique_tree_child_name=lambda *_args, **_kwargs: True,
            next_unique_tree_child_name=lambda _parent_id, name, **_kwargs: f"{name}_1",
            ensure_unique_series_name=lambda *_args, **_kwargs: True,
            ensure_unique_curve_name=lambda *_args, **_kwargs: True,
            find_folder_by_group_type=lambda _group: types.SimpleNamespace(id="datasets-root"),
            find_folder_by_name=lambda _name: None,
            get_image=lambda image_id: next((item for item in self.project.images if item.id == image_id), None),
            sync_legacy_datasets=lambda _project: self.calls.append("sync"),
        )
        defaults.update(overrides)
        return ProjectAssetService(**defaults)

    def test_add_data_file_appends_and_marks_project_modified(self) -> None:
        service = self._make_service()

        node = service.add_data_file(DataFile(id="df-1", name="a.csv"))

        self.assertIsNotNone(node)
        self.assertEqual(1, len(self.project.data_files))
        self.assertTrue(self.project.is_modified)

    def test_rename_series_updates_owner(self) -> None:
        series = DataSeries(id="s1", name="old")
        self.project.data_files.append(DataFile(id="df-1", name="A", series=[series]))
        service = self._make_service()

        changed = service.rename_series("s1", "new")

        self.assertTrue(changed)
        self.assertEqual("new", series.name)
        self.assertTrue(self.project.is_modified)

    def test_move_series_to_data_file_rehomes_series(self) -> None:
        series = DataSeries(id="s1", name="curve")
        source = DataFile(id="df-1", name="A", series=[series])
        target = DataFile(id="df-2", name="B", series=[])
        self.project.data_files.extend([source, target])
        service = self._make_service()

        changed = service.move_series_to_data_file("s1", "df-2")

        self.assertTrue(changed)
        self.assertEqual([], source.series)
        self.assertEqual([series], target.series)

    def test_move_curve_to_image_rehomes_curve(self) -> None:
        curve = TestCurve("c1", "Curve 1")
        source = TestImage("img-1", "Image 1", [curve])
        target = TestImage("img-2", "Image 2", [])
        self.project.images.extend([source, target])
        service = self._make_service()

        changed = service.move_curve_to_image("c1", "img-2")

        self.assertTrue(changed)
        self.assertEqual([], source.curves)
        self.assertEqual([curve], target.curves)


if __name__ == "__main__":
    unittest.main()
