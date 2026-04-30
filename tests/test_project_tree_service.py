from __future__ import annotations

import importlib.util
import sys
import types
import unittest


def _load_project_tree_service_module():
    fake_global_assets = types.ModuleType("core.global_assets")

    class _FakeGlobalAssets:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str | None]] = []

        def update_saved_pipeline(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_saved_pipeline", node_id, name))
            return True

        def update_figure_template(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_figure_template", node_id, name))
            return True

        def update_report_template(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_report_template", node_id, name))
            return True

        def update_ai_prompt(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_ai_prompt", node_id, name))
            return True

        def update_ai_skill(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_ai_skill", node_id, name))
            return True

        def update_ai_agent(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_ai_agent", node_id, name))
            return True

        def delete_saved_pipeline(self, node_id: str) -> bool:
            self.calls.append(("delete_saved_pipeline", node_id, None))
            return True

        def delete_figure_template(self, node_id: str) -> bool:
            self.calls.append(("delete_figure_template", node_id, None))
            return True

        def delete_report_template(self, node_id: str) -> bool:
            self.calls.append(("delete_report_template", node_id, None))
            return True

        def delete_ai_prompt(self, node_id: str) -> bool:
            self.calls.append(("delete_ai_prompt", node_id, None))
            return True

        def delete_ai_skill(self, node_id: str) -> bool:
            self.calls.append(("delete_ai_skill", node_id, None))
            return True

        def delete_ai_agent(self, node_id: str) -> bool:
            self.calls.append(("delete_ai_agent", node_id, None))
            return True

    fake_global_assets.global_assets = _FakeGlobalAssets()
    sys.modules["core.global_assets"] = fake_global_assets

    fake_models = types.ModuleType("models.schemas")

    class FolderNode:
        kind = "folder"

        def __init__(self, **data) -> None:
            self.id = data.get("id", f"folder-{data.get('name', 'x')}")
            self.name = data.get("name", "")
            self.parent_id = data.get("parent_id")
            self.order = data.get("order", 0)
            self.group_type = data.get("group_type")

    class Project:
        pass

    fake_models.FolderNode = FolderNode
    fake_models.Project = Project
    sys.modules["models.schemas"] = fake_models

    spec = importlib.util.spec_from_file_location(
        "test_project_tree_service_module",
        "/home/alpraline/Projects/Python/ALine/core/project_tree_service.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


module = _load_project_tree_service_module()
ProjectTreeService = module.ProjectTreeService
global_assets = module.global_assets


class _Node:
    def __init__(self, kind: str, node_id: str, name: str, parent_id=None, **attrs) -> None:
        self.kind = kind
        self.id = node_id
        self.name = name
        self.parent_id = parent_id
        self.order = attrs.get("order", 0)
        self.group_type = attrs.get("group_type")
        for key, value in attrs.items():
            setattr(self, key, value)


class _Tree:
    def __init__(self, nodes=None) -> None:
        self.nodes = list(nodes or [])

    def get_siblings_max_order(self, _parent_id):
        return len(self.nodes)

    def get_node(self, node_id: str):
        return next((item for item in self.nodes if item.id == node_id), None)

    def get_children(self, parent_id):
        return [item for item in self.nodes if getattr(item, "parent_id", None) == parent_id]


class _Project:
    def __init__(self) -> None:
        self.id = "project-1"
        self.tree = _Tree()
        self.data_files = []
        self.source_files = []
        self.images = []
        self.pictures = []
        self.analyses = []
        self.is_modified = False

    def find_data_file(self, data_file_id: str):
        return next((item for item in self.data_files if item.id == data_file_id), None)

    def find_analysis(self, analysis_id: str):
        return next((item for item in self.analyses if item.id == analysis_id), None)


class TestProjectTreeService(unittest.TestCase):
    def setUp(self) -> None:
        global_assets.calls.clear()
        self.project = _Project()
        self.calls: list[object] = []

    def _make_service(self, **overrides):
        defaults = dict(
            get_current_project=lambda: self.project,
            clear_last_error=lambda: self.calls.append("clear"),
            ensure_project_tree=lambda project: self.calls.append(("ensure_tree", project.id)),
            canonical_group_type=lambda value: value,
            ensure_unique_tree_child_name=lambda *_args, **_kwargs: True,
            rename_source_file=lambda *_args: True,
            rename_image=lambda *_args: True,
            rename_picture=lambda *_args: True,
            delete_backup_if_managed=lambda *_args: self.calls.append("delete_image_backup"),
            delete_picture_backup_if_managed=lambda *_args: self.calls.append("delete_picture_backup"),
            delete_source_file_backup_if_managed=lambda *_args: self.calls.append("delete_source_backup"),
            node_collection_group_type=lambda _node_id: None,
            sync_picture_storage=lambda: self.calls.append("sync_picture"),
            sync_source_file_storage=lambda: self.calls.append("sync_source"),
        )
        defaults.update(overrides)
        return ProjectTreeService(**defaults)

    def test_add_folder_appends_node(self) -> None:
        service = self._make_service()

        node = service.add_folder("A", group_type="datasets")

        self.assertIsNotNone(node)
        self.assertEqual(1, len(self.project.tree.nodes))
        self.assertTrue(self.project.is_modified)

    def test_rename_node_updates_data_file_name(self) -> None:
        data_file = types.SimpleNamespace(id="df-1", name="old")
        self.project.data_files.append(data_file)
        self.project.tree.nodes.append(_Node("data_file", "node-1", "old", data_file_id="df-1"))
        service = self._make_service()

        changed = service.rename_node("node-1", "new")

        self.assertTrue(changed)
        self.assertEqual("new", data_file.name)
        self.assertEqual("new", self.project.tree.nodes[0].name)

    def test_delete_node_prunes_tree_and_asset(self) -> None:
        data_file = types.SimpleNamespace(id="df-1", name="old")
        self.project.data_files.append(data_file)
        root = _Node("folder", "root", "Root")
        child = _Node("data_file", "node-1", "old", parent_id="root", data_file_id="df-1")
        self.project.tree.nodes.extend([root, child])
        service = self._make_service()

        changed = service.delete_node("root")

        self.assertTrue(changed)
        self.assertEqual([], self.project.tree.nodes)
        self.assertEqual([], self.project.data_files)

    def test_move_node_reparents_child(self) -> None:
        folder_a = _Node("folder", "a", "A", group_type="datasets")
        folder_b = _Node("folder", "b", "B", group_type="datasets")
        child = _Node("data_file", "node-1", "f.csv", parent_id="a")
        self.project.tree.nodes.extend([folder_a, folder_b, child])
        service = self._make_service()

        changed = service.move_node(
            "node-1",
            "b",
            3,
            group_type_aliases={"datasets": {"datasets"}, "source_files": {"source_files"}, "images": {"images"}, "pictures": {"pictures"}, "pipeline_group": {"pipeline_group"}, "prompt_group": {"prompt_group"}, "skill_group": {"skill_group"}, "agent_group": {"agent_group"}},
            tool_node_parent_group={"pipeline": "pipeline_group"},
        )

        self.assertTrue(changed)
        self.assertEqual("b", child.parent_id)
        self.assertEqual(3, child.order)


if __name__ == "__main__":
    unittest.main()
