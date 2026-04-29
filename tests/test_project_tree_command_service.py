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
            self.return_node = types.SimpleNamespace(id="node-1")

        def delete_node(self, node_id: str) -> None:
            self.deleted.append(node_id)

        def add_data_file(self, data_file, parent_id: str | None = None):
            self.added.append((data_file.name, parent_id))
            return self.return_node

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
    def test_delete_node_confirms_then_refreshes(self) -> None:
        calls: list[str] = []
        service = ProjectTreeCommandService(
            confirm_delete=lambda *_args: True,
            prompt_text=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            notify_warning=lambda *_args: None,
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
            prompt_text=lambda *_args: ("dataset-a", True),
            create_child_folder=lambda *_args: None,
            notify_warning=lambda *_args: None,
            refresh=lambda: calls.append("refresh"),
            select_node=lambda node_id: calls.append(f"select:{node_id}"),
            project_modified=lambda: calls.append("modified"),
            last_error_message=lambda: "",
        )

        service.add_dataset_node("parent-1")

        self.assertEqual([("dataset-a", "parent-1")], project_manager.added)
        self.assertEqual(["refresh", "select:node-1", "modified"], calls)


if __name__ == "__main__":
    unittest.main()
