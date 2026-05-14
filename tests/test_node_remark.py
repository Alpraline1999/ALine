from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.project_serializer import ProjectSerializer
from models.schemas import FolderNode, Project, ProjectTree


class TestNodeRemarkPersistence(unittest.TestCase):
    def test_tree_node_remark_survives_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Project(
                name="demo",
                tree=ProjectTree(nodes=[FolderNode(name="Folder", remark="实验备注")]),
            )
            path = Path(tmp) / "demo.aline"

            serializer = ProjectSerializer()
            serializer.save(project, str(path))

            loaded = serializer.load(str(path))
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertIsNotNone(loaded.tree)
            assert loaded.tree is not None
            self.assertEqual(loaded.tree.nodes[0].remark, "实验备注")
