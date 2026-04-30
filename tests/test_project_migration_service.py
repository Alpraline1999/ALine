from __future__ import annotations

import importlib.util
import sys
import types
import unittest


def _load_project_migration_service_module():
    original_models = sys.modules.get("models.schemas")
    fake_models = types.ModuleType("models.schemas")

    class _BaseNode:
        kind = "node"

        def __init__(self, **data) -> None:
            self.id = data.get("id", f"{self.kind}-1")
            self.name = data.get("name", "")
            self.parent_id = data.get("parent_id")
            self.order = data.get("order", 0)
            self.group_type = data.get("group_type")
            self.tool_type = data.get("tool_type")
            self.tool_id = data.get("tool_id")

    class FolderNode(_BaseNode):
        kind = "folder"

    class DataFileNode(_BaseNode):
        kind = "data_file"

        def __init__(self, **data) -> None:
            super().__init__(**data)
            self.data_file_id = data.get("data_file_id", "df-1")

    class ImageWorkNode(_BaseNode):
        kind = "image_work"

        def __init__(self, **data) -> None:
            super().__init__(**data)
            self.image_work_id = data.get("image_work_id", "img-1")

    class PictureNode(_BaseNode):
        kind = "picture"

        def __init__(self, **data) -> None:
            super().__init__(**data)
            self.picture_id = data.get("picture_id", "pic-1")

    class AIToolNode(_BaseNode):
        kind = "ai_tool"

    class AIPromptNode(_BaseNode):
        kind = "ai_prompt"

        def __init__(self, **data) -> None:
            super().__init__(**data)
            self.prompt_id = data.get("prompt_id")

    class AISkillNode(_BaseNode):
        kind = "ai_skill"

        def __init__(self, **data) -> None:
            super().__init__(**data)
            self.skill_id = data.get("skill_id")

    class AIAgentNode(_BaseNode):
        kind = "ai_agent"

        def __init__(self, **data) -> None:
            super().__init__(**data)
            self.agent_id = data.get("agent_id")

    class DataSeries:
        def __init__(self, **data) -> None:
            self.name = data.get("name", "")
            self.x = data.get("x", [])
            self.y = data.get("y", [])

    class Dataset:
        def __init__(self, **data) -> None:
            self.name = data.get("name", "")
            self.series = list(data.get("series", []))

    class DataFile:
        def __init__(self, **data) -> None:
            self.id = data.get("id", "df-1")
            self.name = data.get("name", "")
            self.series = list(data.get("series", []))

    class _Image:
        def __init__(self, name: str) -> None:
            self.id = f"image-{name}"
            self.name = name

    class _Picture:
        def __init__(self, name: str) -> None:
            self.id = f"picture-{name}"
            self.name = name

    class ProjectTree:
        def __init__(self) -> None:
            self.nodes: list[object] = []

    class Project:
        def __init__(self, **data) -> None:
            self.id = data.get("id", "project-1")
            self.name = data.get("name", "Project")
            self.tree = data.get("tree", ProjectTree())
            self.datasets = list(data.get("datasets", []))
            self.data_files = list(data.get("data_files", []))
            self.images = list(data.get("images", []))
            self.pictures = list(data.get("pictures", []))
            self.aline_version = data.get("aline_version")
            self.is_modified = data.get("is_modified", False)

        @classmethod
        def create_new(cls, name: str):
            return cls(id=f"id-{name}", name=name)

    fake_models.AIAgentNode = AIAgentNode
    fake_models.AIPromptNode = AIPromptNode
    fake_models.AISkillNode = AISkillNode
    fake_models.DataFile = DataFile
    fake_models.DataFileNode = DataFileNode
    fake_models.DataSeries = DataSeries
    fake_models.Dataset = Dataset
    fake_models.FolderNode = FolderNode
    fake_models.ImageWorkNode = ImageWorkNode
    fake_models.PictureNode = PictureNode
    fake_models.Project = Project
    fake_models.ProjectTree = ProjectTree
    sys.modules["models.schemas"] = fake_models

    spec = importlib.util.spec_from_file_location(
        "test_project_migration_service_module",
        "/home/alpraline/Projects/Python/ALine/core/project_migration_service.py",
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
    module.AIToolNode = AIToolNode
    module.Dataset = Dataset
    module.DataSeries = DataSeries
    module.FolderNode = FolderNode
    module.Project = Project
    module.FakeImage = _Image
    module.FakePicture = _Picture
    return module


module = _load_project_migration_service_module()
ProjectMigrationService = module.ProjectMigrationService
AIToolNode = module.AIToolNode
DataSeries = module.DataSeries
Dataset = module.Dataset
FolderNode = module.FolderNode
Project = module.Project
FakeImage = module.FakeImage
FakePicture = module.FakePicture


class TestProjectMigrationService(unittest.TestCase):
    def _make_service(self, calls: dict[str, list[object]]) -> ProjectMigrationService:
        return ProjectMigrationService(
            ensure_project_tree_groups=lambda project: calls.setdefault("ensure_groups", []).append(project.id),
            migrate_project_assets_to_global=lambda project: calls.setdefault("migrate_assets", []).append(project.id) or True,
        )

    def test_migrate_to_v2_creates_tree_and_data_file_nodes(self) -> None:
        calls: dict[str, list[object]] = {}
        service = self._make_service(calls)
        project = Project.create_new("Legacy V1")
        project.tree = None
        project.datasets.append(Dataset(name="Old Data", series=[DataSeries(name="s1", x=[1.0], y=[2.0])]))
        project.images.append(FakeImage("Image A"))
        project.pictures.append(FakePicture("Picture A"))

        service.migrate_to_v2(project)

        self.assertIsNotNone(project.tree)
        self.assertEqual("0.2", project.aline_version)
        self.assertTrue(project.is_modified)
        self.assertEqual(1, len(project.data_files))
        self.assertEqual("Old Data", project.data_files[0].name)
        self.assertEqual([project.id], calls["ensure_groups"])

    def test_migrate_to_v3_converts_ai_tool_nodes(self) -> None:
        calls: dict[str, list[object]] = {}
        service = self._make_service(calls)
        project = Project.create_new("Legacy V2")
        project.tree.nodes = [
            FolderNode(name="AI 工具", group_type=None),
            AIToolNode(name="Prompt A", tool_type="prompt", tool_id="prompt-1"),
        ]

        service.migrate_to_v3(project)

        self.assertEqual("0.3", project.aline_version)
        self.assertTrue(project.is_modified)
        self.assertEqual("ai_group", project.tree.nodes[0].group_type)
        self.assertEqual("ai_prompt", project.tree.nodes[1].kind)
        self.assertEqual([project.id], calls["migrate_assets"])
        self.assertEqual([project.id], calls["ensure_groups"])


if __name__ == "__main__":
    unittest.main()
