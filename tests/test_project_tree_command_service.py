from __future__ import annotations

import importlib.util
import sys
import types
import unittest


def _load_command_service_module():
    fake_models = types.ModuleType("models.schemas")

    class DataFile:
        def __init__(self, name: str):
            self.name = name

    fake_models.DataFile = DataFile
    sys.modules["models.schemas"] = fake_models

    fake_pm_module = types.ModuleType("core.project_manager")

    class _FakeProjectManager:
        def __init__(self) -> None:
            self.deleted: list[str] = []
            self.added: list[tuple[str, str]] = []
            self.renamed_series: list[tuple[str, str]] = []
            self.removed_empty_folder_args: list[str | None] = []
            self.deleted_series: list[str] = []
            self.deleted_curves: list[str] = []
            self.source_file_batches: list[tuple[list[str], str | None, bool]] = []
            self.added_images: list[tuple[str, str, str | None]] = []
            self.return_node = types.SimpleNamespace(id="node-1")

        def delete_node(self, node_id: str) -> None:
            self.deleted.append(node_id)

        def add_data_file(self, data_file, parent_id: str | None = None):
            self.added.append((data_file.name, parent_id))
            return self.return_node

        def rename_series(self, node_id: str, name: str) -> bool:
            self.renamed_series.append((node_id, name))
            return True

        def rename_curve(self, node_id: str, name: str) -> bool:
            return True

        def remove_empty_folders(self, root_id: str | None = None):
            self.removed_empty_folder_args.append(root_id)
            return ["f1", "f2"]

        def delete_series(self, node_id: str) -> bool:
            self.deleted_series.append(node_id)
            return True

        def delete_curve(self, node_id: str) -> bool:
            self.deleted_curves.append(node_id)
            return True

        def add_source_files(self, paths: list[str], parent_id: str | None = None, auto_rename_on_conflict: bool = False):
            self.source_file_batches.append((list(paths), parent_id, auto_rename_on_conflict))
            return [types.SimpleNamespace(id="src-node-1"), types.SimpleNamespace(id="src-node-2")]

        def add_image(self, path: str, name: str, parent_id: str | None = None):
            self.added_images.append((path, name, parent_id))
            return types.SimpleNamespace(id=f"image-{len(self.added_images)}")

    fake_pm_module.project_manager = _FakeProjectManager()
    sys.modules["core.project_manager"] = fake_pm_module

    spec = importlib.util.spec_from_file_location(
        "test_project_tree_command_service_module",
        "/home/alpraline/Projects/Python/ALine/app/project_tree_command_service.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


module = _load_command_service_module()
ProjectTreeCommandService = module.ProjectTreeCommandService
project_manager = module.project_manager


class TestProjectTreeCommandService(unittest.TestCase):
    def setUp(self) -> None:
        project_manager.deleted.clear()
        project_manager.added.clear()
        project_manager.renamed_series.clear()
        project_manager.removed_empty_folder_args.clear()
        project_manager.deleted_series.clear()
        project_manager.deleted_curves.clear()
        project_manager.source_file_batches.clear()
        project_manager.added_images.clear()

    def test_delete_node_confirms_then_refreshes(self) -> None:
        calls: list[str] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: True,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda *_args: False,
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda *_args: None,
            notify_success=lambda *_args: None,
            refresh=lambda: calls.append("refresh"),
            select_node=lambda node_id: calls.append(f"select:{node_id}"),
            project_modified=lambda: calls.append("modified"),
            last_error_message=lambda: "",
        )

        service.delete_node("n1", "Node 1")

        self.assertEqual(["n1"], project_manager.deleted)
        self.assertEqual(["refresh", "modified"], calls)

    def test_add_dataset_node_creates_and_selects(self) -> None:
        calls: list[str] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: False,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("dataset-a", True),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda *_args: False,
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda *_args: None,
            notify_success=lambda *_args: None,
            refresh=lambda: calls.append("refresh"),
            select_node=lambda node_id: calls.append(f"select:{node_id}"),
            project_modified=lambda: calls.append("modified"),
            last_error_message=lambda: "",
        )

        service.add_dataset_node("parent-1")

        self.assertEqual([("dataset-a", "parent-1")], project_manager.added)
        self.assertEqual(["refresh", "select:node-1", "modified"], calls)

    def test_rename_virtual_series_renames_then_refreshes(self) -> None:
        calls: list[str] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: False,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("series-b", True),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda *_args: False,
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda *_args: None,
            notify_success=lambda *_args: None,
            refresh=lambda: calls.append("refresh"),
            select_node=lambda node_id: calls.append(f"select:{node_id}"),
            project_modified=lambda: calls.append("modified"),
            last_error_message=lambda: "",
        )

        service.rename_virtual("series", "s1", "old")

        self.assertEqual([("s1", "series-b")], project_manager.renamed_series)
        self.assertEqual(["refresh", "modified"], calls)

    def test_prune_empty_folders_reports_success(self) -> None:
        calls: list[tuple[str, str]] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: False,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda *_args: False,
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda *_args: None,
            notify_success=lambda title, content: calls.append((title, content)),
            refresh=lambda: calls.append(("refresh", "")),
            select_node=lambda node_id: calls.append((f"select:{node_id}", "")),
            project_modified=lambda: calls.append(("modified", "")),
            last_error_message=lambda: "",
        )

        service.prune_empty_folders("root-1", scope_label="测试树")

        self.assertEqual(["root-1"], project_manager.removed_empty_folder_args)
        self.assertEqual(("refresh", ""), calls[0])
        self.assertEqual(("modified", ""), calls[1])
        self.assertEqual(("清理完成", "已移除 2 个空文件夹"), calls[2])

    def test_delete_virtual_series_deletes_then_refreshes(self) -> None:
        calls: list[str] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: True,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda *_args: False,
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda *_args: None,
            notify_success=lambda *_args: None,
            refresh=lambda: calls.append("refresh"),
            select_node=lambda node_id: calls.append(f"select:{node_id}"),
            project_modified=lambda: calls.append("modified"),
            last_error_message=lambda: "",
        )

        service.delete_virtual("series", "s99", "Series 99")

        self.assertEqual(["s99"], project_manager.deleted_series)
        self.assertEqual(["refresh", "modified"], calls)

    def test_delete_batch_deletes_all_payloads(self) -> None:
        calls: list[str] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: False,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda *_args: False,
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda *_args: None,
            notify_success=lambda *_args: None,
            refresh=lambda: calls.append("refresh"),
            select_node=lambda node_id: calls.append(f"select:{node_id}"),
            project_modified=lambda: calls.append("modified"),
            last_error_message=lambda: "",
        )

        service.delete_batch([
            {"kind": "series", "node_id": "s1", "name": "S1"},
            {"kind": "curve", "node_id": "c1", "name": "C1"},
            {"kind": "data_file", "node_id": "d1", "name": "D1"},
        ])

        self.assertEqual(["s1"], project_manager.deleted_series)
        self.assertEqual(["c1"], project_manager.deleted_curves)
        self.assertEqual(["d1"], project_manager.deleted)
        self.assertEqual(["refresh", "modified"], calls)

    def test_move_batch_uses_target_selection_and_warns_on_failures(self) -> None:
        calls: list[tuple[str, str]] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: False,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("目标A", True),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda kind, node_id, target_id: node_id == "ok1",
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda title, content: calls.append((title, content)),
            notify_success=lambda *_args: None,
            refresh=lambda: calls.append(("refresh", "")),
            select_node=lambda node_id: calls.append((f"select:{node_id}", "")),
            project_modified=lambda: calls.append(("modified", "")),
            last_error_message=lambda: "",
        )

        service.move_batch(
            [{"kind": "series", "node_id": "ok1", "name": "OK"}, {"kind": "curve", "node_id": "bad1", "name": "BAD"}],
            [("目标A", "target-a"), ("目标B", "target-b")],
        )

        self.assertEqual(("refresh", ""), calls[0])
        self.assertEqual(("modified", ""), calls[1])
        self.assertEqual(("批量移动未完成", "有 1 项移动失败"), calls[2])

    def test_move_virtual_moves_then_refreshes(self) -> None:
        calls: list[tuple[str, str]] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: False,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("目标A", True),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda kind, node_id, target_id: (kind, node_id, target_id) == ("series", "ok2", "target-a"),
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda title, content: calls.append((title, content)),
            notify_success=lambda *_args: None,
            refresh=lambda: calls.append(("refresh", "")),
            select_node=lambda node_id: calls.append((f"select:{node_id}", "")),
            project_modified=lambda: calls.append(("modified", "")),
            last_error_message=lambda: "",
        )

        service.move_virtual("series", "ok2", [("目标A", "target-a"), ("目标B", "target-b")])

        self.assertEqual(("refresh", ""), calls[0])
        self.assertEqual(("modified", ""), calls[1])

    def test_import_source_files_refreshes_and_selects_last_node(self) -> None:
        calls: list[tuple[str, str]] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: False,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: ["a.csv", "b.csv"],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda *_args: False,
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda title, content: calls.append((title, content)),
            notify_success=lambda title, content: calls.append((title, content)),
            refresh=lambda: calls.append(("refresh", "")),
            select_node=lambda node_id: calls.append((f"select:{node_id}", "")),
            project_modified=lambda: calls.append(("modified", "")),
            last_error_message=lambda: "",
        )

        service.import_source_files("parent-s")

        self.assertEqual([(["a.csv", "b.csv"], "parent-s", True)], project_manager.source_file_batches)
        self.assertEqual(("refresh", ""), calls[0])
        self.assertEqual(("select:src-node-2", ""), calls[1])
        self.assertEqual(("modified", ""), calls[2])

    def test_import_digitize_images_reports_success_and_partial_failures(self) -> None:
        calls: list[tuple[str, str]] = []
        linked_map = {"image-1": "img-node-1", "image-2": "img-node-2"}
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: False,
            confirm_batch_delete=lambda *_args: True,
            choose_files=lambda *_args: ["ok1.png", "bad.txt", "ok2.jpg"],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            move_node_to_target=lambda *_args: False,
            supports_digitize_import=lambda path: path.endswith((".png", ".jpg")),
            linked_tree_node_id=lambda _kind, _attr, value: linked_map.get(value),
            notify_warning=lambda title, content: calls.append((title, content)),
            notify_success=lambda title, content: calls.append((title, content)),
            refresh=lambda: calls.append(("refresh", "")),
            select_node=lambda node_id: calls.append((f"select:{node_id}", "")),
            project_modified=lambda: calls.append(("modified", "")),
            last_error_message=lambda: "",
        )

        service.import_digitize_images("parent-i")

        self.assertEqual(
            [("ok1.png", "ok1.png", "parent-i"), ("ok2.jpg", "ok2.jpg", "parent-i")],
            project_manager.added_images,
        )
        self.assertEqual(("refresh", ""), calls[0])
        self.assertEqual(("select:img-node-2", ""), calls[1])
        self.assertEqual(("modified", ""), calls[2])
        self.assertEqual(("导入完成", "已导入 2 张图片到数字化"), calls[3])
        self.assertEqual(("部分导入失败", "以下图片未能导入: bad.txt"), calls[4])


if __name__ == "__main__":
    unittest.main()
