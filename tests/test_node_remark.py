from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.project_manager import ProjectManager
from core.project_serializer import ProjectSerializer
from models.schemas import AnalysisResult, FolderNode, Project, ProjectTree


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

    def test_analysis_result_remark_syncs_between_tree_and_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pm = ProjectManager()
            project = pm.create_new("remark-sync")
            pm.migrate_to_v2(project)
            analysis = AnalysisResult(name="结果A", analysis_type="statistics", summary={})
            self.assertTrue(pm.add_analysis(analysis))

            assert project.tree is not None
            node = next(node for node in project.tree.nodes if node.kind == "analysis_result")
            self.assertTrue(pm.set_analysis_result_remark(node.id, "同步备注"))
            self.assertEqual(pm.get_analysis_result_remark(node.id), "同步备注")
            self.assertEqual(project.find_analysis(analysis.id).remark, "同步备注")
            self.assertEqual(getattr(node, "remark", ""), "同步备注")

            path = Path(tmp) / "remark-sync.aline"
            serializer = ProjectSerializer()
            serializer.save(project, str(path))
            loaded = serializer.load(str(path))

            self.assertIsNotNone(loaded)
            assert loaded is not None
            assert loaded.tree is not None
            loaded_node = next(node for node in loaded.tree.nodes if node.kind == "analysis_result")
            self.assertEqual(loaded.find_analysis(analysis.id).remark, "同步备注")
            self.assertEqual(getattr(loaded_node, "remark", ""), "同步备注")
