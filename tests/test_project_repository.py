from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _load_project_repository_module():
    original_models = sys.modules.get("models.schemas")
    fake_models = types.ModuleType("models.schemas")

    class Project:
        def __init__(self, **data) -> None:
            self.id = data.get("id", "project-1")
            self.name = data.get("name", "Project")
            self.file_path = data.get("file_path")
            self.is_modified = data.get("is_modified", True)
            self.aline_version = data.get("aline_version")
            self.updated_at = data.get("updated_at", "")
            self.data_files = data.get("data_files", [])
            self.datasets = data.get("datasets", [])
            self.images = data.get("images", [])
            self.imported_curves = data.get("imported_curves", [])
            self.analyses = data.get("analyses", [])

        @classmethod
        def create_new(cls, name: str):
            return cls(id=f"id-{name}", name=name, is_modified=True)

        def model_dump(self):
            return {
                "id": self.id,
                "name": self.name,
                "aline_version": self.aline_version,
                "updated_at": self.updated_at,
                "file_path": self.file_path,
                "is_modified": self.is_modified,
            }

    fake_models.Project = Project
    sys.modules["models.schemas"] = fake_models

    spec = importlib.util.spec_from_file_location(
        "test_project_repository_module",
        "/home/alpraline/Projects/Python/ALine/core/project_repository.py",
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
    return module


module = _load_project_repository_module()
ProjectRepository = module.ProjectRepository
Project = module.Project


class TestProjectRepository(unittest.TestCase):
    def _make_repository(self, calls: dict[str, list[object]]) -> ProjectRepository:
        return ProjectRepository(
            project_file_suffix=".aline",
            aline_version="0.1.0",
            normalize_path=lambda path: str(Path(path).resolve()),
            
            sync_project_backups=lambda project, path, previous: calls.setdefault("sync_backups", []).append((project.id, path, previous)),
            add_recent_project=lambda path, name: calls.setdefault("recent", []).append((path, name)),
        )

    def test_save_project_sets_version_and_persists_file(self) -> None:
        calls: dict[str, list[object]] = {}
        repository = self._make_repository(calls)
        project = Project.create_new("Repo Save")

        with tempfile.TemporaryDirectory() as tmpdir:
            saved_path = repository.save_project(project, str(Path(tmpdir) / "repo-save"))

            self.assertTrue(saved_path.endswith(".aline"))
            self.assertEqual("0.1.0", project.aline_version)
            self.assertFalse(project.is_modified)
            self.assertEqual([(saved_path, "Repo Save")], calls["recent"])
            self.assertEqual([(project.id, saved_path, None)], calls["sync_backups"])
            self.assertTrue(Path(saved_path).exists())

    def test_open_project_restores_project_and_marks_clean(self) -> None:
        calls: dict[str, list[object]] = {}
        repository = self._make_repository(calls)
        project = Project.create_new("Repo Open")

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "repo-open.aline"
            data = project.model_dump()
            data.pop("file_path", None)
            data.pop("is_modified", None)
            file_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            loaded = repository.open_project(str(file_path))

            self.assertEqual(project.id, loaded.id)
            self.assertEqual(str(file_path.resolve()), loaded.file_path)
            self.assertFalse(loaded.is_modified)
            self.assertEqual([(str(file_path.resolve()), "Repo Open")], calls["recent"])


if __name__ == "__main__":
    unittest.main()
