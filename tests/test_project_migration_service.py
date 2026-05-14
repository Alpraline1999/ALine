from __future__ import annotations

import importlib.util
import sys
import types
import unittest


def _load_project_tree_init_service_module():
    original_models = sys.modules.get("models.schemas")
    fake_models = types.ModuleType("models.schemas")

    class _Node:
        kind = "node"

        def __init__(self, **data) -> None:
            self.id = data.get("id", f"{self.kind}-1")
            self.name = data.get("name", "")
            self.parent_id = data.get("parent_id")
            self.order = data.get("order", 0)

    class ProjectTree:
        def __init__(self, nodes=None):
            self.nodes = nodes or []

    class Project:
        def __init__(self):
            self.tree = None
            self.aline_version = None
            self.is_modified = False

        @classmethod
        def create_new(cls, name: str) -> "Project":
            return cls()

    fake_models.ProjectTree = ProjectTree
    fake_models.Project = Project
    sys.modules["models.schemas"] = fake_models

    spec = importlib.util.spec_from_file_location(
        "core.project_migration_service",
        "core/project_migration_service.py",
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if original_models is None:
            sys.modules.pop("models.schemas", None)
        else:
            sys.modules["models.schemas"] = original_models
    return module


module = _load_project_tree_init_service_module()
ProjectTreeInitService = module.ProjectTreeInitService
Project = module.Project


class TestProjectTreeInitService(unittest.TestCase):
    def _make_service(self, calls: dict[str, list[object]]) -> ProjectTreeInitService:
        return ProjectTreeInitService(
            ensure_project_tree_groups=lambda project: calls.setdefault("ensure_groups", []).append(id(project)),
        )

    def test_init_new_project_tree_sets_up_v03_structure(self) -> None:
        calls: dict[str, list[object]] = {}
        service = self._make_service(calls)
        project = Project.create_new("New Project")

        service.init_new_project_tree(project)

        self.assertIsNotNone(project.tree)
        self.assertIsNotNone(project.aline_version)
        self.assertEqual(len(calls["ensure_groups"]), 1)


if __name__ == "__main__":
    unittest.main()
