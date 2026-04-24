"""
后端综合测试
══════════════════════════════════════════════════════════════════
覆盖范围：
  1. models/schemas.py          — 模型创建、序列化、v0.2 树节点
  2. core/project_manager.py    — 完整 CRUD、migrate_to_v2、save/load
  3. processing/data_engine.py  — 全部 8 种操作
  4. core/analysis_engine.py    — 曲线拟合、峰值检测、统计、相关性
  5. core/data_operations.py    — CSV / JSON / NumPy 导入
  6. ai/command_layer.py        — 全部 10 条命令
  7. core/ai_client.py          — AIConfig 存取
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _patch_global_assets():
    from core.global_assets import GlobalAssets, global_assets

    temp_dir = tempfile.TemporaryDirectory()
    old_path = global_assets._asset_path
    old_cache = global_assets._cache
    global_assets._asset_path = Path(temp_dir.name) / "global_assets.json"
    global_assets._cache = GlobalAssets()
    global_assets.save()

    def restore():
        global_assets._asset_path = old_path
        global_assets._cache = old_cache
        temp_dir.cleanup()

    return restore


# ══════════════════════════════════════════════════════════════════
# 1. models/schemas.py
# ══════════════════════════════════════════════════════════════════

class TestSchemas(unittest.TestCase):

    def test_data_series_defaults(self):
        from models.schemas import DataSeries
        s = DataSeries(name="test")
        self.assertEqual(s.x, [])
        self.assertEqual(s.y, [])
        self.assertIsNone(s.y_err)
        self.assertEqual(s.source, "manual")

    def test_dataset_contains_series(self):
        from models.schemas import Dataset, DataSeries
        ds = Dataset(name="my_ds")
        s = DataSeries(name="s1", x=[1, 2], y=[3, 4])
        ds.series.append(s)
        self.assertEqual(len(ds.series), 1)
        self.assertEqual(ds.series[0].name, "s1")

    def test_project_create_new(self):
        from models.schemas import Project
        p = Project.create_new("exp_1")
        self.assertEqual(p.aline_version, "0.3")
        self.assertEqual(p.name, "exp_1")

    def test_project_backward_compat_extra_fields_ignored(self):
        """旧文件中有 ALine 不认识的字段时应静默忽略。"""
        from models.schemas import Project
        data = {"id": "abc", "name": "old", "unknown_field_xyz": 999,
                "created_at": "2024", "updated_at": "2024"}
        p = Project(**data)
        self.assertEqual(p.name, "old")

    def test_tree_node_discriminated_union_folder(self):
        from models.schemas import FolderNode, ProjectTree
        node = FolderNode(name="datasets")
        tree = ProjectTree(nodes=[node])
        # Pydantic v2 round-trip
        data = tree.model_dump()
        tree2 = ProjectTree(**data)
        self.assertEqual(tree2.nodes[0].kind, "folder")
        self.assertEqual(tree2.nodes[0].name, "datasets")

    def test_tree_node_discriminated_union_all_kinds(self):
        from models.schemas import (
            FolderNode, DataFileNode, SourceFileNode, ImageWorkNode,
            PipelineNode, FigureTemplateNode, ReportTemplateNode,
            AIToolNode, ProjectTree,
        )
        nodes = [
            FolderNode(name="f"),
            DataFileNode(name="df", data_file_id="x1"),
            SourceFileNode(name="src", source_file_id="x_src"),
            ImageWorkNode(name="img", image_work_id="x2"),
            PipelineNode(name="pipe", pipeline_id="x3"),
            FigureTemplateNode(name="fig", figure_id="x4"),
            ReportTemplateNode(name="report", template_id="x5"),
            AIToolNode(name="ai", tool_id="x6"),
        ]
        tree = ProjectTree(nodes=nodes)
        data = tree.model_dump()
        tree2 = ProjectTree(**data)
        kinds = [n.kind for n in tree2.nodes]
        self.assertEqual(kinds, ["folder", "data_file", "source_file", "image_work", "pipeline",
                                  "figure_template", "report_template", "ai_tool"])

    def test_project_tree_get_children(self):
        from models.schemas import FolderNode, DataFileNode, ProjectTree
        root = FolderNode(name="root", order=0)
        child1 = DataFileNode(name="a", parent_id=root.id, order=0, data_file_id="df1")
        child2 = DataFileNode(name="b", parent_id=root.id, order=1, data_file_id="df2")
        orphan = FolderNode(name="top", order=0)
        tree = ProjectTree(nodes=[root, child1, child2, orphan])
        children = tree.get_children(root.id)
        self.assertEqual([n.name for n in children], ["a", "b"])

    def test_project_tree_query_helpers_cover_name_link_and_path(self):
        from models.schemas import FolderNode, DataFileNode, ProjectTree

        root = FolderNode(name="数据集", group_type="datasets", order=0)
        folder = FolderNode(name="批次A", parent_id=root.id, order=0)
        child = DataFileNode(name="demo.csv", parent_id=folder.id, order=0, data_file_id="df-demo")
        tree = ProjectTree(nodes=[root, folder, child])

        self.assertIs(tree.find_first(kind="folder", name="批次A", parent_id=root.id), folder)
        self.assertEqual([node.name for node in tree.find_nodes(kind="folder", parent_id=root.id)], ["批次A"])
        self.assertIs(tree.find_linked_node("data_file", "data_file_id", "df-demo"), child)
        self.assertEqual([node.name for node in tree.path_to_root(child.id)], ["demo.csv", "批次A", "数据集"])

    def test_data_file_find_series(self):
        from models.schemas import DataFile, DataSeries
        df = DataFile(name="data.csv")
        s1 = DataSeries(name="col1", x=[1], y=[2])
        df.series.append(s1)
        found = df.find_series(s1.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "col1")
        self.assertIsNone(df.find_series("nonexistent"))

    def test_saved_pipeline_model(self):
        from models.schemas import SavedPipeline
        ops = [{"type": "smooth", "params": {"window": 5}}]
        sp = SavedPipeline(name="my_pipe", ops=ops)
        data = sp.model_dump()
        sp2 = SavedPipeline(**data)
        self.assertEqual(sp2.ops[0]["type"], "smooth")

    def test_figure_state_model(self):
        from models.schemas import FigureState
        state = FigureState(
            theme="Nature",
            x_label="Time",
            y_label="Value",
            show_errbar=True,
            font_family="DejaVu Sans",
            line_width=2.2,
            marker_size=6.5,
            dpi=220,
        )
        data = state.model_dump()
        restored = FigureState(**data)
        self.assertEqual(restored.theme, "Nature")
        self.assertEqual(restored.x_label, "Time")
        self.assertTrue(restored.show_errbar)
        self.assertEqual(restored.font_family, "DejaVu Sans")
        self.assertEqual(restored.line_width, 2.2)
        self.assertEqual(restored.marker_size, 6.5)
        self.assertEqual(restored.dpi, 220)

    def test_analysis_result_model(self):
        from models.schemas import AnalysisResult
        ar = AnalysisResult(name="fit1", analysis_type="curve_fit",
                            summary={"r2": 0.99})
        self.assertEqual(ar.analysis_type, "curve_fit")
        self.assertEqual(ar.summary["r2"], 0.99)

    def test_project_find_series_across_datasets(self):
        from models.schemas import Project, Dataset, DataSeries
        p = Project.create_new("test")
        ds = Dataset(name="ds1")
        s = DataSeries(name="s1", x=[1], y=[2])
        ds.series.append(s)
        p.datasets.append(ds)
        found = p.find_series(s.id)
        self.assertIsNotNone(found)
        self.assertIsNone(p.find_series("bad_id"))


# ══════════════════════════════════════════════════════════════════
# 2. core/project_manager.py
# ══════════════════════════════════════════════════════════════════

class TestProjectManager(unittest.TestCase):

    def setUp(self):
        # 每次测试前重置全局单例状态
        from core.project_manager import ProjectManager
        self._restore_assets = _patch_global_assets()
        self.pm = ProjectManager()

    def tearDown(self):
        self._restore_assets()

    def test_create_new_project(self):
        p = self.pm.create_new("test_proj")
        self.assertEqual(p.name, "test_proj")
        self.assertEqual(p.aline_version, "0.3")
        self.assertEqual(self.pm.current_project_id, p.id)

    def test_migrate_to_v2_idempotent(self):
        p = self.pm.create_new("mp")
        from models.schemas import Dataset, DataSeries
        ds = Dataset(name="ds1")
        ds.series.append(DataSeries(name="s1", x=[1, 2], y=[3, 4]))
        p.datasets.append(ds)
        self.pm.migrate_to_v2(p)
        node_count = len(p.tree.nodes)
        self.pm.migrate_to_v2(p)  # 幂等：第二次调用不应改变
        self.assertEqual(len(p.tree.nodes), node_count)

    def test_migrate_creates_folder_nodes(self):
        from models.schemas import Dataset, DataSeries, ImageWork
        p = self.pm.create_new("m2")
        p.datasets.append(Dataset(name="ds1"))
        p.images.append(ImageWork(name="img1", image_path=""))
        self.pm.migrate_to_v2(p)
        kinds = [n.kind for n in p.tree.nodes]
        # At minimum, folder nodes should be created
        self.assertIn("folder", kinds)

    def test_new_project_tree_contains_only_business_root_groups(self):
        p = self.pm.create_new("grouped_tree")
        self.pm.migrate_to_v3(p)
        folder_map = {
            (node.name, getattr(node, "group_type", None), node.parent_id)
            for node in p.tree.nodes
            if node.kind == "folder"
        }
        self.assertIn(("数据集", "datasets", None), folder_map)
        self.assertIn(("源文件", "source_files", None), folder_map)
        self.assertIn(("数字化", "images", None), folder_map)
        self.assertIn(("图片集", "pictures", None), folder_map)
        self.assertIn(("分析结果", "analysis_result_group", None), folder_map)
        self.assertEqual(len(folder_map), 5)

    def test_add_source_files_creates_managed_nodes_under_source_group(self):
        p = self.pm.create_new("source_files")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_file = Path(temp_dir) / "source_files.aline"
            self.pm.save(str(project_file))
            source_root = self.pm._find_folder_by_group_type("source_files")
            self.assertIsNotNone(source_root)
            target_folder = self.pm.add_folder("原始记录", parent_id=source_root.id, group_type="source_files")
            self.assertIsNotNone(target_folder)

            file_a = Path(temp_dir) / "raw_a.csv"
            file_b = Path(temp_dir) / "raw_b.txt"
            file_a.write_text("x,y\n1,2\n", encoding="utf-8")
            file_b.write_text("hello", encoding="utf-8")

            nodes = self.pm.add_source_files([str(file_a), str(file_b)], parent_id=target_folder.id)

            self.assertEqual(len(nodes), 2)
            self.assertEqual(len(p.source_files), 2)
            self.assertTrue(all(node.parent_id == target_folder.id for node in nodes))
            managed_paths = [self.pm.get_source_file_path(node.source_file_id) for node in nodes]
            self.assertTrue(all(Path(path).exists() for path in managed_paths))
            self.assertTrue(all("files/source_files/原始记录" in path for path in managed_paths))
            self.assertTrue(file_a.exists())
            self.assertTrue(file_b.exists())

    def test_move_source_file_tracks_managed_storage(self):
        p = self.pm.create_new("source_move")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_file = Path(temp_dir) / "source_move.aline"
            self.pm.save(str(project_file))
            source_root = self.pm._find_folder_by_group_type("source_files")
            self.assertIsNotNone(source_root)
            folder_a = self.pm.add_folder("批次A", parent_id=source_root.id, group_type="source_files")
            folder_b = self.pm.add_folder("批次B", parent_id=source_root.id, group_type="source_files")
            self.assertIsNotNone(folder_a)
            self.assertIsNotNone(folder_b)

            raw_file = Path(temp_dir) / "sample.dat"
            raw_file.write_text("raw-data", encoding="utf-8")
            node = self.pm.add_source_file(str(raw_file), parent_id=folder_a.id)
            self.assertIsNotNone(node)

            source_asset = p.source_files[0]
            self.assertIn("files/source_files/批次A/sample.dat", self.pm.get_source_file_path(source_asset.id))

            moved = self.pm.move_node(node.id, folder_b.id, 0)

            self.assertTrue(moved)
            target_path = self.pm.get_source_file_path(source_asset.id)
            self.assertTrue(Path(target_path).exists())
            self.assertIn("files/source_files/批次B/sample.dat", target_path)

    def test_source_file_origin_path_survives_save_and_reopen(self):
        p = self.pm.create_new("source_origin")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_file = Path(temp_dir) / "source_origin.aline"
            self.pm.save(str(project_file))

            raw_file = Path(temp_dir) / "raw_origin.csv"
            raw_file.write_text("x,y\n1,2\n", encoding="utf-8")

            node = self.pm.add_source_file(str(raw_file))
            self.assertIsNotNone(node)

            asset = p.source_files[0]
            expected_origin = str(raw_file.resolve())
            self.assertEqual(asset.source_file_path, expected_origin)

            self.pm.save(str(project_file))
            self.assertEqual(asset.source_file_path, expected_origin)

            self.pm.close_current_project()
            reopened = self.pm.open(str(project_file))
            reopened_asset = reopened.source_files[0]
            self.assertEqual(reopened_asset.source_file_path, expected_origin)

    def test_picture_plot_snapshot_survives_save_and_reopen(self):
        from models.schemas import FigureState, PicturePlotExtensionSnapshot, PicturePlotSeriesSnapshot, PicturePlotSnapshot

        p = self.pm.create_new("picture_snapshot")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_file = Path(temp_dir) / "picture_snapshot.aline"
            self.pm.save(str(project_file))

            picture_path = Path(temp_dir) / "chart.png"
            picture_path.write_bytes(b"png")
            snapshot = PicturePlotSnapshot(
                figure_state=FigureState(x_label="Time", y_label="Value"),
                series=[
                    PicturePlotSeriesSnapshot(
                        curve_key="curve-1",
                        curve_identity="curve-1",
                        name="series-a",
                        display_name="series-a",
                        x=[1.0, 2.0],
                        y=[3.0, 4.0],
                    )
                ],
                applied_extensions=[
                    PicturePlotExtensionSnapshot(
                        id="plot-extension-1",
                        type="probe-extension",
                        sequence=1,
                        options={"factor": 2},
                        extension_version="1.2.3",
                    )
                ],
            )

            node = self.pm.add_picture(str(picture_path), name="chart.png", plot_snapshot=snapshot)

            self.assertIsNotNone(node)
            self.assertIsNotNone(p.pictures[0].plot_snapshot)

            self.pm.save(str(project_file))
            self.pm.close_current_project()
            reopened = self.pm.open(str(project_file))

            reopened_picture = reopened.pictures[0]
            self.assertIsNotNone(reopened_picture.plot_snapshot)
            self.assertEqual(reopened_picture.plot_snapshot.figure_state.x_label, "Time")
            self.assertEqual(len(reopened_picture.plot_snapshot.series), 1)
            self.assertEqual(reopened_picture.plot_snapshot.series[0].name, "series-a")
            self.assertEqual(reopened_picture.plot_snapshot.applied_extensions[0].extension_version, "1.2.3")

    def test_migrate_to_v3_removes_legacy_tools_folder(self):
        from models.schemas import FolderNode, ProjectTree

        p = self.pm.create_new("legacy_tools")
        ds = FolderNode(name="数据集", group_type="datasets", order=0)
        imgs = FolderNode(name="图片集", group_type="images", order=1)
        tools = FolderNode(name="工具集", group_type="tools", order=2)
        pipelines = FolderNode(name="Pipelines", group_type="pipeline_group", parent_id=tools.id, order=0)
        reports = FolderNode(name="报告模板组", group_type="report_template_group", parent_id=tools.id, order=1)
        ai_group = FolderNode(name="AI 工具", group_type="ai_group", parent_id=tools.id, order=2)
        p.tree = ProjectTree(nodes=[ds, imgs, tools, pipelines, reports, ai_group])

        self.pm.migrate_to_v3(p)

        root_map = {
            (node.name, getattr(node, "group_type", None), node.parent_id)
            for node in p.tree.nodes
            if node.kind == "folder"
        }
        self.assertNotIn(("工具集", "tools", None), root_map)
        self.assertNotIn(("Pipelines", "pipeline_group", None), root_map)
        self.assertNotIn(("报告模板组", "report_template_group", None), root_map)
        self.assertNotIn(("AI 工具", "ai_group", None), root_map)

    def test_add_folder(self):
        self.pm.create_new("test")
        self.pm.migrate_to_v2()
        node = self.pm.add_folder("my_folder")
        self.assertIsNotNone(node)
        self.assertEqual(node.kind, "folder")
        self.assertEqual(node.name, "my_folder")

    def test_add_data_file(self):
        from models.schemas import DataFile, DataSeries
        p = self.pm.create_new("test")
        self.pm.migrate_to_v2(p)
        folder = self.pm.add_folder("data_folder")
        df = DataFile(name="exp.csv", series=[DataSeries(name="x", x=[1,2], y=[3,4])])
        node = self.pm.add_data_file(df, folder.id)
        self.assertIsNotNone(node)
        self.assertEqual(node.kind, "data_file")
        self.assertIn(df, p.data_files)

    def test_add_data_file_rejects_duplicate_name_in_same_folder(self):
        from models.schemas import DataFile

        p = self.pm.create_new("dup_df")
        self.pm.migrate_to_v2(p)
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)

        first = self.pm.add_data_file(DataFile(name="same.csv"), datasets_root.id)
        second = self.pm.add_data_file(DataFile(name="same.csv"), datasets_root.id)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(p.data_files), 1)
        self.assertIn("已存在名为", self.pm.get_last_error_message())

    def test_dataset_folder_and_data_file_can_share_same_name(self):
        from models.schemas import DataFile

        p = self.pm.create_new("mixed_kind_dup")
        self.pm.migrate_to_v2(p)
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)

        folder = self.pm.add_folder("same.csv", parent_id=datasets_root.id, group_type="datasets")
        node = self.pm.add_data_file(DataFile(name="same.csv"), datasets_root.id)

        self.assertIsNotNone(folder)
        self.assertIsNotNone(node)
        self.assertEqual(len(p.data_files), 1)

    def test_add_data_file_auto_renames_duplicate_name_when_requested(self):
        from models.schemas import DataFile

        p = self.pm.create_new("dup_df_auto")
        self.pm.migrate_to_v2(p)
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)

        first = self.pm.add_data_file(DataFile(name="same.csv"), datasets_root.id)
        second_df = DataFile(name="same.csv")
        second = self.pm.add_data_file(second_df, datasets_root.id, auto_rename_on_conflict=True)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(second_df.name, "same_1.csv")
        self.assertEqual(len(p.data_files), 2)

    def test_add_source_file_rejects_duplicate_name_in_same_folder(self):
        p = self.pm.create_new("dup_source")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_file = Path(temp_dir) / "dup_source.aline"
            self.pm.save(str(project_file))
            source_root = self.pm._find_folder_by_group_type("source_files")
            self.assertIsNotNone(source_root)

            dir_a = Path(temp_dir) / "a"
            dir_b = Path(temp_dir) / "b"
            dir_a.mkdir()
            dir_b.mkdir()
            file_a = dir_a / "raw.csv"
            file_b = dir_b / "raw.csv"
            file_a.write_text("x,y\n1,2\n", encoding="utf-8")
            file_b.write_text("x,y\n3,4\n", encoding="utf-8")

            first = self.pm.add_source_file(str(file_a), parent_id=source_root.id)
            second = self.pm.add_source_file(str(file_b), parent_id=source_root.id)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(p.source_files), 1)
        self.assertIn("已存在名为", self.pm.get_last_error_message())

    def test_add_source_file_auto_renames_duplicate_name_when_requested(self):
        p = self.pm.create_new("dup_source_auto")
        with tempfile.TemporaryDirectory() as temp_dir:
            project_file = Path(temp_dir) / "dup_source_auto.aline"
            self.pm.save(str(project_file))
            source_root = self.pm._find_folder_by_group_type("source_files")
            self.assertIsNotNone(source_root)

            dir_a = Path(temp_dir) / "a"
            dir_b = Path(temp_dir) / "b"
            dir_a.mkdir()
            dir_b.mkdir()
            file_a = dir_a / "raw.csv"
            file_b = dir_b / "raw.csv"
            file_a.write_text("x,y\n1,2\n", encoding="utf-8")
            file_b.write_text("x,y\n3,4\n", encoding="utf-8")

            first = self.pm.add_source_file(str(file_a), parent_id=source_root.id)
            second = self.pm.add_source_file(
                str(file_b),
                parent_id=source_root.id,
                auto_rename_on_conflict=True,
            )

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(sorted(item.name for item in p.source_files), ["raw.csv", "raw_1.csv"])

    def test_move_node_rejects_duplicate_target_sibling_name(self):
        from models.schemas import DataFile

        self.pm.create_new("move_conflict")
        self.pm.migrate_to_v2()
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder_a = self.pm.add_folder("A", parent_id=datasets_root.id, group_type="datasets")
        folder_b = self.pm.add_folder("B", parent_id=datasets_root.id, group_type="datasets")
        self.assertIsNotNone(folder_a)
        self.assertIsNotNone(folder_b)
        source = self.pm.add_data_file(DataFile(name="dup.csv"), folder_a.id)
        target = self.pm.add_data_file(DataFile(name="dup.csv"), folder_b.id)

        moved = self.pm.move_node(source.id, folder_b.id, 0)

        self.assertIsNotNone(target)
        self.assertFalse(moved)
        self.assertIn("已存在名为", self.pm.get_last_error_message())

    def test_series_and_curve_name_conflicts_are_blocked(self):
        from models.schemas import DataFile, DataSeries

        self.pm.create_new("dup_virtual")
        self.pm.migrate_to_v2()

        data_file = self.pm.add_data_file(DataFile(name="dup.csv", series=[
            DataSeries(name="s1", x=[1.0], y=[2.0]),
            DataSeries(name="s2", x=[2.0], y=[3.0]),
        ]))
        other_file = self.pm.add_data_file(DataFile(name="other.csv", series=[
            DataSeries(name="s1", x=[4.0], y=[5.0]),
        ]))
        self.assertIsNotNone(data_file)
        self.assertIsNotNone(other_file)

        first_df = self.pm.get_data_file(data_file.data_file_id)
        other_df = self.pm.get_data_file(other_file.data_file_id)
        self.assertIsNotNone(first_df)
        self.assertIsNotNone(other_df)

        self.assertFalse(self.pm.rename_series(first_df.series[1].id, "s1"))
        self.assertIn("数据系列", self.pm.get_last_error_message())
        self.assertFalse(self.pm.move_series_to_data_file(other_df.series[0].id, first_df.id))
        self.assertIn("数据系列", self.pm.get_last_error_message())

        image = self.pm.add_image("fake.png", "img")
        first_curve = self.pm.add_curve_to_image(image.id, [1.0], [2.0], name="c1")
        second_curve = self.pm.add_curve_to_image(image.id, [2.0], [3.0], name="c2")

        self.assertIsNotNone(first_curve)
        self.assertIsNotNone(second_curve)
        self.assertFalse(self.pm.rename_curve(second_curve.id, "c1"))
        self.assertIn("曲线", self.pm.get_last_error_message())

    def test_rename_node(self):
        p = self.pm.create_new("test")
        self.pm.migrate_to_v2(p)
        folder = self.pm.add_folder("original")
        result = self.pm.rename_node(folder.id, "renamed")
        self.assertTrue(result)
        node = p.tree.get_node(folder.id)
        self.assertEqual(node.name, "renamed")

    def test_rename_figure_template_updates_figure_name(self):
        from models.schemas import FigureConfig
        from core.global_assets import global_assets

        self.pm.create_new("test")
        fig = self.pm.add_figure_template(FigureConfig(name="old_template"))
        self.assertIsNotNone(fig)
        self.assertTrue(global_assets.update_figure_template(fig.id, name="renamed_template"))
        fig = global_assets.get_figure_template(fig.id)
        self.assertEqual(fig.name, "renamed_template")

    def test_delete_node_with_cascade(self):
        p = self.pm.create_new("test")
        self.pm.migrate_to_v2(p)
        parent = self.pm.add_folder("parent")
        child = self.pm.add_folder("child", parent.id)
        # Add a data_file under child
        from models.schemas import DataFile
        df = DataFile(name="d.csv")
        self.pm.add_data_file(df, child.id)
        self.assertIn(df, p.data_files)
        # Delete parent → cascade
        self.pm.delete_node(parent.id)
        ids = [n.id for n in p.tree.nodes]
        self.assertNotIn(parent.id, ids)
        self.assertNotIn(child.id, ids)
        self.assertNotIn(df, p.data_files)

    def test_remove_empty_folders_prunes_nested_user_folders(self):
        from models.schemas import DataFile

        p = self.pm.create_new("test")
        self.pm.migrate_to_v2(p)
        root = self.pm.add_folder("root")
        empty_child = self.pm.add_folder("empty_child", root.id)
        nested_parent = self.pm.add_folder("nested_parent", root.id)
        nested_leaf = self.pm.add_folder("nested_leaf", nested_parent.id)
        kept_folder = self.pm.add_folder("kept_folder", root.id)
        self.pm.add_data_file(DataFile(name="kept.csv"), kept_folder.id)

        removed_ids = self.pm.remove_empty_folders(root.id)
        remaining_ids = {node.id for node in p.tree.nodes}

        self.assertIn(root.id, remaining_ids)
        self.assertIn(kept_folder.id, remaining_ids)
        self.assertNotIn(empty_child.id, remaining_ids)
        self.assertNotIn(nested_leaf.id, remaining_ids)
        self.assertNotIn(nested_parent.id, remaining_ids)
        self.assertGreaterEqual(len(removed_ids), 3)

    def test_remove_empty_folders_prunes_managed_group_subfolders(self):
        p = self.pm.create_new("managed_empty_cleanup")
        self.pm.migrate_to_v2(p)
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)

        folder = self.pm.add_folder("批次A", parent_id=datasets_root.id, group_type="datasets")
        nested = self.pm.add_folder("批次B", parent_id=folder.id, group_type="datasets")
        self.assertIsNotNone(folder)
        self.assertIsNotNone(nested)

        removed_ids = self.pm.remove_empty_folders(datasets_root.id)
        remaining_ids = {node.id for node in p.tree.nodes}

        self.assertIn(datasets_root.id, remaining_ids)
        self.assertNotIn(folder.id, remaining_ids)
        self.assertNotIn(nested.id, remaining_ids)
        self.assertGreaterEqual(len(removed_ids), 2)

    def test_add_and_load_pipeline(self):
        from core.global_assets import global_assets

        self.pm.create_new("test")
        ops = [{"type": "smooth", "params": {"window": 5}},
               {"type": "normalize", "params": {"mode": "minmax"}}]
        sp = self.pm.add_saved_pipeline("my_pipe", ops)
        self.assertIsNotNone(sp)
        loaded = self.pm.load_pipeline(sp.id)
        self.assertEqual(loaded, ops)
        self.assertEqual(global_assets.get_saved_pipeline(sp.id).name, "my_pipe")

    def test_move_node_rejects_folder_move(self):
        p = self.pm.create_new("move_guard")
        self.pm.migrate_to_v3(p)
        folder = self.pm.add_folder("user_folder")
        datasets_folder = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(folder)
        self.assertIsNotNone(datasets_folder)
        moved = self.pm.move_node(folder.id, datasets_folder.id, 0)
        self.assertFalse(moved)

    def test_delete_pipeline(self):
        from core.global_assets import global_assets

        self.pm.create_new("test")
        sp = self.pm.add_saved_pipeline("pipe1", [])
        self.assertIsNotNone(sp)
        result = self.pm.delete_saved_pipeline(sp.id)
        self.assertTrue(result)
        self.assertIsNone(global_assets.get_saved_pipeline(sp.id))

    def test_save_and_reload(self):
        from models.schemas import DataFile, DataSeries
        p = self.pm.create_new("save_test")
        self.pm.migrate_to_v2(p)
        df = DataFile(name="file.csv", series=[DataSeries(name="s1", x=[1,2,3], y=[4,5,6])])
        self.pm.add_data_file(df)
        with tempfile.NamedTemporaryFile(suffix=".pyline", delete=False) as f:
            path = f.name
        try:
            self.pm.save(path)
            p2 = self.pm.open_file(path)
            self.assertIsNotNone(p2.tree)
            names = [n.name for n in p2.tree.nodes]
            self.assertIn("file.csv", names)
            self.assertTrue(any(df.name == "file.csv" for df in p2.data_files))
        finally:
            os.unlink(path)

    def test_sync_legacy_datasets_on_save(self):
        """v0.2 DataFile 应在保存时同步到 datasets 保证兼容。"""
        from models.schemas import DataFile, DataSeries
        p = self.pm.create_new("sync_test")
        self.pm.migrate_to_v2(p)
        df = DataFile(name="compat.csv",
                      series=[DataSeries(name="s1", x=[1], y=[2])])
        self.pm.add_data_file(df)
        with tempfile.NamedTemporaryFile(suffix=".pyline", delete=False) as f:
            path = f.name
        try:
            self.pm.save(path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # datasets 应存在（旧 PyLine 兼容）
            self.assertIn("datasets", data)
        finally:
            os.unlink(path)

    def test_add_series_to_dataset(self):
        p = self.pm.create_new("t")
        from models.schemas import DataSeries
        ds = self.pm.add_dataset("ds1")
        s = DataSeries(name="s1", x=[1, 2], y=[3, 4])
        result = self.pm.add_series_to_dataset(ds.id, s)
        self.assertTrue(result)
        found = p.find_series(s.id)
        self.assertIsNotNone(found)

    def test_dataset_crud(self):
        p = self.pm.create_new("t")
        ds = self.pm.add_dataset("ds1")
        self.assertIsNotNone(ds)
        self.assertTrue(self.pm.rename_dataset(ds.id, "renamed_ds"))
        self.assertEqual(p.find_dataset(ds.id).name, "renamed_ds")
        self.assertTrue(self.pm.remove_dataset(ds.id))
        self.assertIsNone(p.find_dataset(ds.id))

    def test_collect_all_series(self):
        from models.schemas import DataSeries, Dataset
        p = self.pm.create_new("t")
        ds = self.pm.add_dataset("ds1")
        s = DataSeries(name="s1", x=[1], y=[2])
        self.pm.add_series_to_dataset(ds.id, s)
        all_s = self.pm.collect_all_series(p)
        ids = [item["id"] for item in all_s]
        self.assertIn(s.id, ids)


# ══════════════════════════════════════════════════════════════════
# 3. processing/data_engine.py
# ══════════════════════════════════════════════════════════════════

class TestDataEngine(unittest.TestCase):

    def _make_wave(self, n=50):
        xs = [i * 0.1 for i in range(n)]
        ys = [math.sin(x) for x in xs]
        return xs, ys

    def test_apply_pipeline_empty_ops(self):
        from processing.data_engine import apply_pipeline
        xs, ys = [1, 2, 3], [4, 5, 6]
        nx, ny = apply_pipeline(xs, ys, [])
        self.assertEqual(nx, xs)
        self.assertEqual(ny, ys)

    def test_pipeline_nondestructive(self):
        from processing.data_engine import apply_pipeline
        xs, ys = [1.0, 2.0, 3.0], [4.0, 5.0, 6.0]
        original_xs, original_ys = list(xs), list(ys)
        apply_pipeline(xs, ys, [{"type": "normalize", "params": {"mode": "minmax"}}])
        self.assertEqual(xs, original_xs)
        self.assertEqual(ys, original_ys)

    def test_op_crop(self):
        from processing.data_engine import apply_operation
        xs = [0.0, 1.0, 2.0, 3.0, 4.0]
        ys = [0.0, 1.0, 4.0, 9.0, 16.0]
        nx, ny = apply_operation(xs, ys, {"type": "crop", "params": {"x_min": 1.0, "x_max": 3.0}})
        self.assertEqual(nx, [1.0, 2.0, 3.0])
        self.assertEqual(ny, [1.0, 4.0, 9.0])

    def test_op_crop_empty_result(self):
        from processing.data_engine import apply_operation
        nx, ny = apply_operation([1, 2, 3], [4, 5, 6],
                                  {"type": "crop", "params": {"x_min": 10, "x_max": 20}})
        self.assertEqual(nx, [])
        self.assertEqual(ny, [])

    def test_crop_extension_ignores_empty_bounds(self):
        from extensions.processing.crop import crop_handler

        handler = crop_handler
        xs = [0.0, 1.0, 2.0, 3.0]
        ys = [2.0, 3.0, 4.0, 5.0]

        nx, ny = handler(xs, ys, {"x_min": None, "x_max": ""})

        self.assertEqual(nx, xs)
        self.assertEqual(ny, ys)

    def test_op_normalize_minmax(self):
        from processing.data_engine import apply_operation
        xs, ys = [0.0, 1.0, 2.0], [0.0, 5.0, 10.0]
        nx, ny = apply_operation(xs, ys, {"type": "normalize", "params": {"mode": "minmax"}})
        self.assertAlmostEqual(ny[0], 0.0)
        self.assertAlmostEqual(ny[-1], 1.0)

    def test_op_normalize_zscore(self):
        from processing.data_engine import apply_operation
        xs, ys = [0.0, 1.0, 2.0], [1.0, 2.0, 3.0]
        nx, ny = apply_operation(xs, ys, {"type": "normalize", "params": {"mode": "zscore"}})
        mean = sum(ny) / len(ny)
        self.assertAlmostEqual(mean, 0.0, places=10)

    def test_op_smooth_savgol(self):
        from processing.data_engine import apply_operation
        xs, ys = self._make_wave()
        nx, ny = apply_operation(xs, ys, {"type": "smooth",
                                           "params": {"method": "savgol", "window": 7, "poly": 2}})
        self.assertEqual(len(nx), len(xs))
        self.assertEqual(len(ny), len(ys))

    def test_op_smooth_moving_avg(self):
        from processing.data_engine import apply_operation
        xs, ys = self._make_wave()
        nx, ny = apply_operation(xs, ys, {"type": "smooth",
                                           "params": {"method": "moving_avg", "window": 5}})
        self.assertEqual(len(nx), len(xs))

    def test_op_resample(self):
        from processing.data_engine import apply_operation
        xs, ys = self._make_wave()
        nx, ny = apply_operation(xs, ys, {"type": "resample", "params": {"n": 100}})
        self.assertEqual(len(nx), 100)
        self.assertEqual(len(ny), 100)

    def test_op_resample_by_spacing(self):
        from processing.data_engine import apply_operation

        xs = [0.0, 1.0, 2.0, 3.0, 4.0]
        ys = [0.0, 1.0, 2.0, 3.0, 4.0]
        nx, ny = apply_operation(xs, ys, {"type": "resample", "params": {"mode": "spacing", "step": 0.5}})

        self.assertEqual(nx, [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0])
        self.assertEqual(ny, nx)

    def test_op_resample_align_accepts_target_line(self):
        from processing.data_engine import apply_pipeline_to_lines

        lines = [
            {"name": "A", "x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 2.0]},
            {"name": "B", "x": [0.0, 0.5, 1.0, 1.5, 2.0], "y": [0.0, 0.5, 1.0, 1.5, 2.0]},
        ]

        rebuilt, warnings = apply_pipeline_to_lines(
            lines,
            [{"type": "resample", "params": {"mode": "align", "target_line": 2}}],
            selected_lines=lines,
        )

        self.assertEqual(warnings, [])
        self.assertEqual(rebuilt[0]["x"], [0.0, 0.5, 1.0, 1.5, 2.0])
        self.assertEqual(rebuilt[1]["x"], [0.0, 0.5, 1.0, 1.5, 2.0])

    def test_op_resample_align_keeps_legacy_target_index_compatible(self):
        from processing.data_engine import apply_pipeline_to_lines

        lines = [
            {"name": "A", "x": [0.0, 1.0, 2.0], "y": [0.0, 1.0, 2.0]},
            {"name": "B", "x": [0.0, 0.5, 1.0, 1.5, 2.0], "y": [0.0, 0.5, 1.0, 1.5, 2.0]},
        ]

        rebuilt, warnings = apply_pipeline_to_lines(
            lines,
            [{"type": "resample", "params": {"mode": "align", "target_index": 2}}],
            selected_lines=lines,
        )

        self.assertEqual(warnings, [])
        self.assertEqual(rebuilt[0]["x"], [0.0, 0.5, 1.0, 1.5, 2.0])

    def test_op_resample_by_spacing_rejects_non_positive_step(self):
        from processing.data_engine import apply_operation

        with self.assertRaisesRegex(ValueError, "坐标间距必须大于 0"):
            apply_operation([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], {"type": "resample", "params": {"mode": "spacing", "step": 0.0}})

    def test_op_derivative(self):
        from processing.data_engine import apply_operation
        # y = x² → dy/dx = 2x
        n = 20
        xs = [float(i) for i in range(n)]
        ys = [x ** 2 for x in xs]
        nx, ny = apply_operation(xs, ys, {"type": "derivative", "params": {}})
        self.assertEqual(len(nx), n)
        # Check interior points: dy/dx ≈ 2x
        for i in range(2, n - 2):
            self.assertAlmostEqual(ny[i], 2 * xs[i], delta=0.5)

    def test_op_integral(self):
        from processing.data_engine import apply_operation
        # y = 1, integral from 0 to N should be N
        n = 11
        xs = [float(i) for i in range(n)]
        ys = [1.0] * n
        nx, ny = apply_operation(xs, ys, {"type": "integral", "params": {"cumulative": True}})
        self.assertEqual(len(nx), n)
        self.assertAlmostEqual(ny[-1], float(n - 1), places=5)

    def test_op_transform_y_expr(self):
        from processing.data_engine import apply_operation
        xs = [1.0, 2.0, 3.0]
        ys = [1.0, 2.0, 3.0]
        nx, ny = apply_operation(xs, ys, {"type": "transform",
                                           "params": {"x_expr": "", "y_expr": "y * 2"}})
        self.assertEqual(ny, [2.0, 4.0, 6.0])

    def test_op_transform_x_expr(self):
        from processing.data_engine import apply_operation
        xs = [1.0, 2.0, 3.0]
        ys = [1.0, 2.0, 3.0]
        nx, ny = apply_operation(xs, ys, {"type": "transform",
                                           "params": {"x_expr": "x * 10", "y_expr": ""}})
        self.assertEqual(nx, [10.0, 20.0, 30.0])

    def test_op_filter(self):
        from processing.data_engine import apply_operation
        xs, ys = self._make_wave(100)
        # Add high-freq noise
        import math as m
        noisy_ys = [y + 0.5 * m.sin(100 * x) for x, y in zip(xs, ys)]
        nx, ny = apply_operation(xs, noisy_ys, {"type": "filter",
                                                  "params": {"cutoff": 0.1, "order": 4}})
        self.assertEqual(len(nx), len(xs))
        self.assertEqual(len(ny), len(ys))

    def test_op_fft_supports_sampling_rate_override(self):
        from processing.data_engine import apply_operation
        import math as m

        sample_rate = 100.0
        xs = [index / sample_rate for index in range(100)]
        ys = [m.sin(2 * m.pi * 5 * x) for x in xs]

        freq, amp = apply_operation(xs, ys, {"type": "fft", "params": {"sampling_rate": sample_rate}})

        peak_index = max(range(1, len(amp)), key=lambda index: amp[index])
        self.assertAlmostEqual(freq[peak_index], 5.0, delta=0.25)

    def test_op_filter_supports_actual_cutoff_frequency(self):
        from processing.data_engine import apply_operation
        import math as m

        sample_rate = 100.0
        xs = [index / sample_rate for index in range(200)]
        ys = [m.sin(2 * m.pi * 2 * x) + 0.4 * m.sin(2 * m.pi * 20 * x) for x in xs]

        _, normalized = apply_operation(xs, ys, {"type": "filter", "params": {"cutoff": 0.1, "order": 4, "mode": "low"}})
        _, actual = apply_operation(xs, ys, {"type": "filter", "params": {"cutoff": 5.0, "cutoff_mode": "actual", "sampling_rate": sample_rate, "order": 4, "mode": "low"}})

        self.assertEqual(len(normalized), len(actual))
        for norm_value, actual_value in zip(normalized, actual):
            self.assertAlmostEqual(norm_value, actual_value, delta=1e-6)

    def test_pipeline_chain(self):
        from processing.data_engine import apply_pipeline
        xs, ys = self._make_wave(50)
        ops = [
            {"type": "crop",      "params": {"x_min": 1.0, "x_max": 4.0}},
            {"type": "smooth",    "params": {"method": "moving_avg", "window": 3}},
            {"type": "normalize", "params": {"mode": "minmax"}},
        ]
        nx, ny = apply_pipeline(xs, ys, ops)
        self.assertGreater(len(nx), 0)
        if len(ny) > 0:
            self.assertAlmostEqual(min(ny), 0.0, places=5)
            self.assertAlmostEqual(max(ny), 1.0, places=5)

    def test_unknown_op_passthrough(self):
        from processing.data_engine import apply_operation
        xs, ys = [1.0, 2.0], [3.0, 4.0]
        nx, ny = apply_operation(xs, ys, {"type": "unknown_op", "params": {}})
        self.assertEqual(nx, xs)
        self.assertEqual(ny, ys)

    def test_custom_processing_extension_executes(self):
        from core.extension_api import ProcessingExtension, extension_registry
        from processing.data_engine import apply_operation

        def _scale(xs, ys, params):
            factor = float(params.get("factor", 1.0))
            return list(xs), [value * factor for value in ys]

        extension_registry.register_processing(
            ProcessingExtension(type="test_scale", name="测试缩放", handler=_scale)
        )
        try:
            nx, ny = apply_operation([0.0, 1.0], [2.0, 3.0], {"type": "test_scale", "params": {"factor": 4}})
            self.assertEqual(nx, [0.0, 1.0])
            self.assertEqual(ny, [8.0, 12.0])
        finally:
            extension_registry.unregister_processing("test_scale")

    def test_pairwise_compute_requires_prealigned_x(self):
        from processing.data_engine import apply_pipeline_to_lines

        with self.assertRaisesRegex(ValueError, "需进行坐标间距重采样"):
            apply_pipeline_to_lines(
                [
                    {"name": "left", "x": [0.0, 1.0, 2.0], "y": [1.0, 3.0, 5.0]},
                    {"name": "right", "x": [0.0, 0.5, 1.0, 1.5, 2.0], "y": [1.0, 2.0, 3.0, 4.0, 5.0]},
                ],
                [{"type": "pairwise_compute", "params": {"operator": "subtract", "align_mode": "auto", "n": 3}}],
            )

    def test_pairwise_compute_accepts_count_resample_before_pairing(self):
        from processing.data_engine import apply_pipeline_to_lines

        lines, warnings = apply_pipeline_to_lines(
            [
                {"name": "left", "x": [0.0, 1.0, 2.0], "y": [1.0, 3.0, 5.0]},
                {"name": "right", "x": [0.5, 1.0, 1.5, 2.0], "y": [1.0, 2.0, 3.0, 4.0]},
            ],
            [
                {"type": "resample", "params": {"mode": "spacing", "spacing_mode": "point", "n": 3}},
                {"type": "pairwise_compute", "params": {"operator": "subtract", "align_mode": "auto", "n": 3}},
            ],
        )

        self.assertEqual(warnings, [])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["x"], [0.5, 1.25, 2.0])
        self.assertEqual(len(lines[0]["y"]), 3)

    def test_pairwise_compute_accepts_coord_spacing_resample_before_pairing(self):
        from processing.data_engine import apply_pipeline_to_lines

        lines, warnings = apply_pipeline_to_lines(
            [
                {"name": "left", "x": [0.0, 1.0, 2.0], "y": [1.0, 3.0, 5.0]},
                {"name": "right", "x": [0.5, 1.0, 1.5, 2.0], "y": [1.0, 2.0, 3.0, 4.0]},
            ],
            [
                {"type": "resample", "params": {"mode": "spacing", "spacing_mode": "coord", "step": 0.5}},
                {"type": "pairwise_compute", "params": {"operator": "subtract", "align_mode": "auto", "n": 3}},
            ],
        )

        self.assertEqual(warnings, [])
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["x"], [0.5, 1.0, 1.5, 2.0])
        self.assertEqual(len(lines[0]["y"]), 4)

    def test_custom_processing_extension_receives_lines(self):
        from core.extension_api import ProcessingExtension, extension_registry
        from processing.data_engine import align_lines_to_common_x, apply_pipeline_to_lines

        def _mean(xs, ys, params, lines=None):
            aligned_lines, warnings = align_lines_to_common_x(lines or [], params)
            point_count = len(aligned_lines[0].get("x", [])) if aligned_lines else 0
            averaged = []
            for index in range(point_count):
                averaged.append(sum(line["y"][index] for line in aligned_lines) / len(aligned_lines))
            return {
                "name": "mean",
                "x": aligned_lines[0].get("x", []),
                "y": averaged,
                "warnings": warnings,
            }

        extension_registry.register_processing(
            ProcessingExtension(
                type="test_mean",
                name="测试均值",
                handler=_mean,
                lines_number=(2, -1),
            )
        )
        try:
            lines, warnings = apply_pipeline_to_lines(
                [
                    {"name": "a", "x": [0.0, 1.0, 2.0], "y": [2.0, 4.0, 6.0]},
                    {"name": "b", "x": [0.0, 0.5, 1.0, 1.5, 2.0], "y": [0.0, 1.0, 2.0, 3.0, 4.0]},
                ],
                [{"type": "test_mean", "params": {"align_mode": "auto", "n": 3}}],
            )
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["name"], "mean")
            self.assertEqual(lines[0]["y"], [1.0, 3.0, 5.0])
            self.assertTrue(warnings)
        finally:
            extension_registry.unregister_processing("test_mean")


# ══════════════════════════════════════════════════════════════════
# 4. core/analysis_engine.py
# ══════════════════════════════════════════════════════════════════

class TestAnalysisEngine(unittest.TestCase):

    def _linear_data(self, n=30, a=2.0, b=1.0, noise=0.0):
        import math
        xs = [float(i) / (n - 1) * 10 for i in range(n)]
        ys = [a * x + b + noise * (i % 3 - 1) for i, x in enumerate(xs)]
        return xs, ys

    def _sine_data(self, n=60):
        import math
        xs = [i * 0.1 for i in range(n)]
        ys = [math.sin(x) for x in xs]
        return xs, ys

    def test_fit_linear(self):
        from core.analysis_engine import fit_curve
        xs, ys = self._linear_data(a=2.0, b=1.0)
        r = fit_curve(xs, ys, "linear")
        self.assertAlmostEqual(r["params"][0], 2.0, delta=0.1)
        self.assertAlmostEqual(r["params"][1], 1.0, delta=0.1)
        self.assertGreater(r["r2"], 0.99)
        self.assertEqual(r["model"], "linear")
        self.assertIn("fit_x", r)
        self.assertIn("fit_y", r)
        self.assertEqual(len(r["fit_x"]), 300)

    def test_fit_poly2(self):
        from core.analysis_engine import fit_curve
        xs = [float(i) for i in range(20)]
        ys = [x ** 2 + 2 * x + 1 for x in xs]
        r = fit_curve(xs, ys, "poly2")
        self.assertGreater(r["r2"], 0.999)

    def test_fit_poly3(self):
        from core.analysis_engine import fit_curve
        xs = [float(i) for i in range(20)]
        ys = [x ** 3 - x for x in xs]
        r = fit_curve(xs, ys, "poly3")
        self.assertGreater(r["r2"], 0.999)

    def test_fit_exponential(self):
        from core.analysis_engine import fit_curve
        import math
        xs = [float(i) * 0.5 for i in range(20)]
        ys = [2.0 * math.exp(0.3 * x) for x in xs]
        r = fit_curve(xs, ys, "exponential")
        self.assertGreater(r["r2"], 0.99)

    def test_fit_unknown_model_raises(self):
        from core.analysis_engine import fit_curve
        with self.assertRaises(ValueError):
            fit_curve([1, 2, 3], [1, 2, 3], "bad_model")

    def test_fit_insufficient_data_raises(self):
        from core.analysis_engine import fit_curve
        with self.assertRaises(ValueError):
            fit_curve([1, 2], [1, 2], "linear")

    def test_detect_peaks(self):
        from core.analysis_engine import detect_peaks
        xs, ys = self._sine_data()
        r = detect_peaks(xs, ys, min_distance=5)
        self.assertGreater(r["count"], 0)
        self.assertEqual(r["count"], len(r["peaks"]))
        for peak in r["peaks"]:
            self.assertIn("x", peak)
            self.assertIn("y", peak)
            self.assertIn("index", peak)

    def test_detect_peaks_with_height_filter(self):
        from core.analysis_engine import detect_peaks
        xs, ys = self._sine_data()
        r = detect_peaks(xs, ys, min_height=0.9)
        for peak in r["peaks"]:
            self.assertGreater(peak["y"], 0.9)

    def test_detect_peaks_with_x_distance_filter(self):
        from core.analysis_engine import detect_peaks

        xs = [0.0, 0.2, 0.4, 0.6, 1.0, 1.2, 1.4, 1.6]
        ys = [0.0, 1.0, 0.0, 0.9, 0.0, 0.0, 0.8, 0.0]
        r = detect_peaks(xs, ys, min_distance=None, min_distance_x=0.7)

        self.assertEqual(r["count"], 2)
        self.assertEqual([round(peak["x"], 1) for peak in r["peaks"]], [0.2, 1.4])

    def test_detect_peaks_empty(self):
        from core.analysis_engine import detect_peaks
        xs = [float(i) for i in range(10)]
        ys = [1.0] * 10  # flat signal
        r = detect_peaks(xs, ys, min_height=2.0)
        self.assertEqual(r["count"], 0)

    def test_compute_statistics(self):
        from core.analysis_engine import compute_statistics
        xs = [1.0, 2.0, 3.0, 4.0, 5.0]
        ys = [2.0, 4.0, 6.0, 8.0, 10.0]
        r = compute_statistics(xs, ys)
        self.assertEqual(r["n"], 5)
        self.assertAlmostEqual(r["y_mean"], 6.0)
        self.assertAlmostEqual(r["y_min"], 2.0)
        self.assertAlmostEqual(r["y_max"], 10.0)
        self.assertAlmostEqual(r["x_mean"], 3.0)

    def test_compute_statistics_median(self):
        from core.analysis_engine import compute_statistics
        xs = [1.0, 2.0, 3.0]
        ys = [1.0, 2.0, 100.0]
        r = compute_statistics(xs, ys)
        self.assertAlmostEqual(r["y_median"], 2.0)

    def test_compute_correlation_pearson(self):
        from core.analysis_engine import compute_correlation
        # Perfect positive correlation
        y1 = [float(i) for i in range(20)]
        y2 = [2.0 * v + 1.0 for v in y1]
        r = compute_correlation(y1, y2, "pearson")
        self.assertAlmostEqual(r["r"], 1.0, places=10)
        self.assertEqual(r["method"], "pearson")

    def test_compute_correlation_negative(self):
        from core.analysis_engine import compute_correlation
        y1 = [float(i) for i in range(20)]
        y2 = [-v for v in y1]
        r = compute_correlation(y1, y2, "pearson")
        self.assertAlmostEqual(r["r"], -1.0, places=10)

    def test_compute_correlation_insufficient_data(self):
        from core.analysis_engine import compute_correlation
        with self.assertRaises(ValueError):
            compute_correlation([1, 2], [1, 2], "pearson")

    def test_compute_error_metrics(self):
        from core.analysis_engine import compute_error_metrics

        xs = [0.0, 1.0, 2.0]
        y1 = [1.0, 2.0, 3.0]
        y2 = [0.5, 2.5, 2.0]
        result = compute_error_metrics(xs, y1, xs, y2)
        self.assertEqual(result["analysis_type"], "error_compare")
        self.assertEqual(result["n"], 3)
        self.assertEqual(result["error_y"], [0.5, -0.5, 1.0])
        self.assertAlmostEqual(result["mae"], (0.5 + 0.5 + 1.0) / 3)

    def test_fit_equation_format(self):
        from core.analysis_engine import fit_curve
        xs, ys = self._linear_data()
        r = fit_curve(xs, ys, "linear")
        self.assertIn("equation", r)
        self.assertIn("=", r["equation"])

    def test_custom_analysis_extension_executes(self):
        from core.analysis_engine import run_analysis
        from core.extension_api import AnalysisExtension, extension_registry

        def _span(inputs, params):
            values = list(inputs[0].get("y", []))
            return {
                "analysis_type": "test_span",
                "source_name": inputs[0].get("name", ""),
                "span": (max(values) - min(values)) if values else 0.0,
                "scale": params.get("scale", 1),
            }

        extension_registry.register_analysis(
            AnalysisExtension(type="test_span", name="测试跨度", handler=_span)
        )
        try:
            result = run_analysis(
                "test_span",
                [{"x": [0.0, 1.0], "y": [2.0, 6.0], "name": "s1"}],
                {"scale": 3},
            )
            self.assertEqual(result["analysis_type"], "test_span")
            self.assertEqual(result["span"], 4.0)
            self.assertEqual(result["scale"], 3)
        finally:
            extension_registry.unregister_analysis("test_span")

    def test_custom_analysis_extension_receives_lines_list(self):
        from core.analysis_engine import run_analysis
        from core.extension_api import AnalysisExtension, extension_registry

        def _summary(inputs, params, lines_list=None):
            return {
                "analysis_type": "test_lines_list",
                "input_count": len(lines_list or []),
                "primary_name": (lines_list or [{}])[0].get("name", ""),
                "flag": params.get("flag", ""),
            }

        extension_registry.register_analysis(
            AnalysisExtension(type="test_lines_list", name="测试多输入", handler=_summary)
        )
        try:
            result = run_analysis(
                "test_lines_list",
                [
                    {"x": [0.0, 1.0], "y": [1.0, 2.0], "name": "main"},
                    {"x": [0.0, 1.0], "y": [2.0, 3.0], "name": "other"},
                ],
                {"flag": "ok"},
            )
            self.assertEqual(result["input_count"], 2)
            self.assertEqual(result["primary_name"], "main")
            self.assertEqual(result["flag"], "ok")
        finally:
            extension_registry.unregister_analysis("test_lines_list")

    def test_extension_registry_loads_directory_module(self):
        from core.analysis_engine import run_analysis
        from core.extension_api import extension_registry

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "demo_extension.py"
            path.write_text(textwrap.dedent(
                """
                from core.extension_api import AnalysisExtension, ProcessingExtension

                def _scale(xs, ys, params):
                    factor = float(params.get('factor', 1.0))
                    return list(xs), [value * factor for value in ys]

                def _span(inputs, params):
                    values = list(inputs[0].get('y', []))
                    return {
                        'analysis_type': 'dir_span',
                        'source_name': inputs[0].get('name', ''),
                        'span': (max(values) - min(values)) if values else 0.0,
                    }

                def register_extensions(registry):
                    registry.register_processing(ProcessingExtension(type='dir_scale', name='目录缩放', handler=_scale))
                    registry.register_analysis(AnalysisExtension(type='dir_span', name='目录跨度', handler=_span))
                """
            ), encoding="utf-8")

            report = extension_registry.load_from_directory(temp_dir)
            try:
                self.assertEqual(report["errors"], [])
                self.assertEqual(len(report["loaded"]), 1)
                result = run_analysis(
                    "dir_span",
                    [{"x": [0.0, 1.0], "y": [1.0, 5.0], "name": "demo"}],
                    {},
                )
                self.assertEqual(result["span"], 4.0)
            finally:
                extension_registry.unregister_processing("dir_scale")
                extension_registry.unregister_analysis("dir_span")

    def test_load_builtin_extensions_helper_uses_target_directory(self):
        from core.extension_api import extension_registry, load_builtin_extensions

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "helper_extension.py"
            path.write_text(textwrap.dedent(
                """
                from core.extension_api import ProcessingExtension

                def _shift(xs, ys, params):
                    offset = float(params.get('offset', 0.0))
                    return list(xs), [value + offset for value in ys]

                def register_extensions(registry):
                    registry.register_processing(
                        ProcessingExtension(type='helper_shift', name='目录平移', handler=_shift)
                    )
                """
            ), encoding="utf-8")

            report = load_builtin_extensions(temp_dir)
            try:
                self.assertEqual(report["errors"], [])
                self.assertEqual(len(report["loaded"]), 1)
                self.assertIsNotNone(extension_registry.get_processing("helper_shift"))
            finally:
                extension_registry.unregister_processing("helper_shift")

    def test_load_configured_extensions_reports_duplicate_type_conflicts(self):
        from core.extension_api import (
            default_extensions_directory,
            extension_registry,
            load_configured_extensions,
        )
        from core.extension_settings import set_external_extensions_directory

        extension_registry.clear()
        try:
            with tempfile.TemporaryDirectory() as builtin_dir, tempfile.TemporaryDirectory() as external_dir, tempfile.TemporaryDirectory() as config_dir:
                builtin_path = Path(builtin_dir) / "builtin_extension.py"
                external_path = Path(external_dir) / "external_extension.py"
                config_path = Path(config_dir) / "extension_settings.json"

                builtin_path.write_text(textwrap.dedent(
                    """
                    from core.extension_api import ProcessingExtension

                    def _builtin(xs, ys, params):
                        return list(xs), [value + 1 for value in ys]

                    def register_extensions(registry):
                        registry.register_processing(
                            ProcessingExtension(type='shared_probe', name='内置探针', handler=_builtin)
                        )
                    """
                ), encoding="utf-8")
                external_path.write_text(textwrap.dedent(
                    """
                    from core.extension_api import AnalysisExtension, ProcessingExtension

                    def _external(xs, ys, params):
                        return list(xs), [value + 2 for value in ys]

                    def _summary(inputs, params):
                        return {'analysis_type': 'external_probe', 'count': len(inputs)}

                    def register_extensions(registry):
                        registry.register_processing(
                            ProcessingExtension(type='shared_probe', name='外部探针', handler=_external)
                        )
                        registry.register_analysis(
                            AnalysisExtension(type='external_probe', name='外部分析', handler=_summary)
                        )
                    """
                ), encoding="utf-8")

                with mock.patch("core.extension_settings._CONFIG_PATH", config_path):
                    set_external_extensions_directory(external_dir)
                    report = load_configured_extensions(builtin_dir)

                self.assertEqual(len(report["loaded"]), 1)
                self.assertEqual(len(report["errors"]), 1)
                self.assertIn("重复的 processing 扩展 type: shared_probe", report["errors"][0])
                self.assertEqual(extension_registry.get_processing("shared_probe").name, "内置探针")
                self.assertIsNone(extension_registry.get_analysis("external_probe"))
        finally:
            extension_registry.clear()
            extension_registry.load_from_directory(default_extensions_directory())

    def test_extension_registry_rejects_duplicate_processing_name(self):
        from core.extension_api import ExtensionRegistry, ProcessingExtension

        registry = ExtensionRegistry()

        def _first(xs, ys, params):
            return list(xs), list(ys)

        def _second(xs, ys, params):
            return list(xs), list(ys)

        registry.register_processing(ProcessingExtension(type="name_probe_a", name="重复名称", handler=_first))
        with self.assertRaisesRegex(ValueError, "重复的 processing 扩展 name: 重复名称"):
            registry.register_processing(ProcessingExtension(type="name_probe_b", name="重复名称", handler=_second))

    def test_load_configured_extensions_respects_builtin_extension_settings(self):
        from core.extension_api import (
            default_extensions_directory,
            extension_registry,
            list_builtin_extension_specs,
            load_configured_extensions,
        )
        from core.extension_settings import set_builtin_extension_settings, set_external_extensions_directory

        extension_registry.clear()
        try:
            with tempfile.TemporaryDirectory() as builtin_dir, tempfile.TemporaryDirectory() as external_dir, tempfile.TemporaryDirectory() as config_dir:
                config_path = Path(config_dir) / "extension_settings.json"

                (Path(builtin_dir) / "builtin_enabled.py").write_text(textwrap.dedent(
                    """
                    from core.extension_api import ProcessingExtension

                    def _enabled(xs, ys, params):
                        return list(xs), [value + 1 for value in ys]

                    def register_extensions(registry):
                        registry.register_processing(
                            ProcessingExtension(type='builtin_enabled', name='启用内置扩展', handler=_enabled)
                        )
                    """
                ), encoding="utf-8")
                (Path(builtin_dir) / "builtin_disabled.py").write_text(textwrap.dedent(
                    """
                    from core.extension_api import ProcessingExtension

                    def _disabled(xs, ys, params):
                        return list(xs), [value + 2 for value in ys]

                    def register_extensions(registry):
                        registry.register_processing(
                            ProcessingExtension(type='builtin_disabled', name='禁用内置扩展', handler=_disabled)
                        )
                    """
                ), encoding="utf-8")
                (Path(external_dir) / "external_extension.py").write_text(textwrap.dedent(
                    """
                    from core.extension_api import AnalysisExtension

                    def _summary(inputs, params):
                        return {'analysis_type': 'external_summary', 'count': len(inputs)}

                    def register_extensions(registry):
                        registry.register_analysis(
                            AnalysisExtension(type='external_summary', name='外部分析', handler=_summary)
                        )
                    """
                ), encoding="utf-8")

                with mock.patch("core.extension_settings._CONFIG_PATH", config_path):
                    set_external_extensions_directory(external_dir)
                    set_builtin_extension_settings(True, ["builtin_disabled"])
                    report = load_configured_extensions(builtin_dir)
                    specs = list_builtin_extension_specs(builtin_dir)

                self.assertEqual(report["errors"], [])
                self.assertEqual(len(report["loaded"]), 2)
                self.assertIsNotNone(extension_registry.get_processing("builtin_enabled"))
                self.assertIsNone(extension_registry.get_processing("builtin_disabled"))
                self.assertIsNotNone(extension_registry.get_analysis("external_summary"))
                self.assertEqual(
                    {item["id"]: item["enabled"] for item in specs},
                    {"builtin_disabled": False, "builtin_enabled": True},
                )
        finally:
            extension_registry.clear()
            extension_registry.load_from_directory(default_extensions_directory())

    def test_extension_registry_exposes_last_load_report(self):
        from core.extension_api import (
            extension_registry,
            get_last_extension_load_report,
            load_builtin_extensions,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            good_path = Path(temp_dir) / "good_extension.py"
            bad_path = Path(temp_dir) / "bad_extension.py"
            good_path.write_text(textwrap.dedent(
                """
                from core.extension_api import ProcessingExtension

                def _noop(xs, ys, params):
                    return list(xs), list(ys)

                def register_extensions(registry):
                    registry.register_processing(
                        ProcessingExtension(type='report_probe', name='报告探针', handler=_noop)
                    )
                """
            ), encoding="utf-8")
            bad_path.write_text("raise RuntimeError('boom')\n", encoding="utf-8")

            report = load_builtin_extensions(temp_dir)
            snapshot = get_last_extension_load_report()
            try:
                self.assertEqual(snapshot, report)
                self.assertEqual(len(snapshot["loaded"]), 1)
                self.assertEqual(len(snapshot["errors"]), 1)
                self.assertIn("bad_extension.py", snapshot["errors"][0])

                snapshot["loaded"].append("mutated")
                self.assertNotIn("mutated", get_last_extension_load_report()["loaded"])
            finally:
                extension_registry.unregister_processing("report_probe")

    def test_extension_load_details_are_available_by_category(self):
        from core.extension_api import (
            extension_registry,
            get_extension_load_status,
            get_last_extension_load_details,
            load_builtin_extensions,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            good_path = Path(temp_dir) / "processing_probe.py"
            bad_path = Path(temp_dir) / "analysis_probe.py"
            good_path.write_text(textwrap.dedent(
                """
                from core.extension_api import ProcessingExtension

                def _noop(xs, ys, params):
                    return list(xs), list(ys)

                def register_extensions(registry):
                    registry.register_processing(
                        ProcessingExtension(type='processing_probe', name='处理探针', handler=_noop)
                    )
                """
            ), encoding="utf-8")
            bad_path.write_text(textwrap.dedent(
                """
                from core.extension_api import AnalysisExtension

                raise RuntimeError('analysis boom')
                """
            ), encoding="utf-8")

            load_builtin_extensions(temp_dir)
            processing_details = get_last_extension_load_details("processing")
            analysis_details = get_last_extension_load_details("analysis")
            processing_status = get_extension_load_status("processing")
            analysis_status = get_extension_load_status("analysis")
            try:
                self.assertEqual(len(processing_details["loaded"]), 1)
                self.assertEqual(processing_details["loaded"][0]["categories"], ["processing"])
                self.assertEqual(processing_details["loaded"][0]["source"], "builtin")
                self.assertEqual(len(analysis_details["errors"]), 1)
                self.assertIn("analysis", analysis_details["errors"][0]["categories"])
                self.assertEqual(analysis_details["errors"][0]["source"], "builtin")
                self.assertEqual(processing_status["registered_count"], 1)
                self.assertEqual(processing_status["source_summary"]["loaded_extension_counts"]["builtin"], 1)
                self.assertEqual(analysis_status["error_count"], 1)
            finally:
                extension_registry.unregister_processing("processing_probe")

    def test_extension_load_report_shows_builtin_and_external_sources(self):
        from core.extension_api import extension_registry, format_extension_load_report

        with tempfile.TemporaryDirectory() as builtin_dir, tempfile.TemporaryDirectory() as external_dir:
            builtin_path = Path(builtin_dir) / "builtin_probe.py"
            external_path = Path(external_dir) / "external_probe.py"
            broken_path = Path(external_dir) / "broken_analysis.py"

            builtin_path.write_text(textwrap.dedent(
                """
                from core.extension_api import ProcessingExtension

                def _noop(xs, ys, params):
                    return list(xs), list(ys)

                def register_extensions(registry):
                    registry.register_processing(
                        ProcessingExtension(type='builtin_probe', name='内置探针', handler=_noop)
                    )
                """
            ), encoding="utf-8")
            external_path.write_text(textwrap.dedent(
                """
                from core.extension_api import AnalysisExtension

                def _analyze(inputs, params):
                    return {"analysis_type": "external_probe", "value": 1}

                def register_extensions(registry):
                    registry.register_analysis(
                        AnalysisExtension(type='external_probe', name='外部探针', handler=_analyze)
                    )
                """
            ), encoding="utf-8")
            broken_path.write_text("raise RuntimeError('external boom')\n", encoding="utf-8")

            extension_registry.clear()
            extension_registry.load_from_sources(
                file_paths=[builtin_path],
                directories=[external_dir],
                file_source_kind="builtin",
                directory_source_kind="external",
            )
            report = format_extension_load_report()
            try:
                self.assertIn("已注册扩展: 2（内置 1 / 外部 1）", report)
                self.assertIn("builtin_probe.py [内置]", report)
                self.assertIn("external_probe.py [外部]", report)
                self.assertIn("broken_analysis.py [外部]", report)
            finally:
                extension_registry.unregister_processing("builtin_probe")
                extension_registry.unregister_analysis("external_probe")

    def test_configured_external_extension_files_respect_saved_enable_and_disable_state(self):
        from core.extension_api import configured_external_extension_files, list_external_extension_specs
        from core.extension_settings import set_external_extension_settings, set_external_extensions_directory

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "extension_settings.json"
            external_dir = Path(temp_dir) / "external_extensions"
            external_dir.mkdir()
            (external_dir / "external_enabled.py").write_text(textwrap.dedent(
                """
                from core.extension_api import PlotExtension

                def _plot(axis, lines, params):
                    return None

                def register_extensions(registry):
                    registry.register_plot(
                        PlotExtension(type='external_enabled', name='外部已启用', handler=_plot)
                    )
                """
            ), encoding="utf-8")
            (external_dir / "external_disabled.py").write_text(textwrap.dedent(
                """
                from core.extension_api import PlotExtension

                def _plot(axis, lines, params):
                    return None

                def register_extensions(registry):
                    registry.register_plot(
                        PlotExtension(type='external_disabled', name='外部已禁用', handler=_plot)
                    )
                """
            ), encoding="utf-8")

            with mock.patch("core.extension_settings._CONFIG_PATH", config_path):
                set_external_extensions_directory(external_dir)
                set_external_extension_settings(True, ["external_disabled"])
                files = configured_external_extension_files()
                specs = list_external_extension_specs()

                self.assertEqual([path.stem for path in files], ["external_enabled"])
                self.assertEqual(
                    {item["id"]: item["enabled"] for item in specs},
                    {"external_disabled": False, "external_enabled": True},
                )

    def test_reload_builtin_extensions_replaces_previous_registry_entries(self):
        from core.extension_api import default_extensions_directory, extension_registry, reload_builtin_extensions

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reload_extension.py"
            path.write_text(textwrap.dedent(
                """
                from core.extension_api import ProcessingExtension

                def _first(xs, ys, params):
                    return list(xs), list(ys)

                def register_extensions(registry):
                    registry.register_processing(
                        ProcessingExtension(type='reload_first', name='第一次加载', handler=_first)
                    )
                """
            ), encoding="utf-8")

            report = reload_builtin_extensions(temp_dir)
            self.assertEqual(report["errors"], [])
            self.assertIsNotNone(extension_registry.get_processing("reload_first"))

            path.write_text(textwrap.dedent(
                """
                from core.extension_api import ProcessingExtension

                def _second(xs, ys, params):
                    return list(xs), list(ys)

                def register_extensions(registry):
                    registry.register_processing(
                        ProcessingExtension(type='reload_second', name='第二次加载', handler=_second)
                    )
                """
            ), encoding="utf-8")

            report = reload_builtin_extensions(temp_dir)
            self.assertEqual(report["errors"], [])
            self.assertIsNone(extension_registry.get_processing("reload_first"))
            self.assertIsNotNone(extension_registry.get_processing("reload_second"))

        extension_registry.clear()
        extension_registry.load_from_directory(default_extensions_directory())

    def test_extension_registry_rejects_invalid_version_format(self):
        from core.extension_api import ProcessingExtension, extension_registry

        def _noop(xs, ys, params):
            return list(xs), list(ys)

        with self.assertRaisesRegex(ValueError, "x.x.x"):
            extension_registry.register_processing(
                ProcessingExtension(type="invalid_version_probe", name="非法版本", handler=_noop, version="1.0")
            )

    def test_builtin_extensions_declare_explicit_versions(self):
        from core.extension_api import extension_registry, reload_builtin_extensions

        report = reload_builtin_extensions()
        self.assertEqual(report["errors"], [])

        builtin_extensions = [
            *extension_registry.list_plot(),
            *extension_registry.list_processing(),
            *extension_registry.list_analysis(),
        ]
        self.assertTrue(builtin_extensions)
        for extension in builtin_extensions:
            self.assertEqual(extension.version, "0.1.0", extension.type)

    def test_core_builtin_analysis_wrappers_expose_extension_metadata(self):
        from core.builtin_extensions import register_core_builtin_extensions
        from core.extension_api import ExtensionRegistry, build_extension_entry

        registry = ExtensionRegistry()
        register_core_builtin_extensions(registry)

        curve_fit_entry = build_extension_entry(registry.get_analysis("curve_fit"))
        peak_detect_entry = build_extension_entry(registry.get_analysis("peak_detect"))
        correlation_entry = build_extension_entry(registry.get_analysis("correlation"))

        self.assertEqual(curve_fit_entry["source_kind"], "builtin")
        self.assertTrue(curve_fit_entry["listed"])
        self.assertEqual(curve_fit_entry["resolved_options"]["model"], "linear")
        self.assertTrue(any(field.get("key") == "model" for field in curve_fit_entry["config_fields"]))
        self.assertTrue(any(field.get("key") == "p0" for field in curve_fit_entry["config_fields"]))
        self.assertIn("拟合", curve_fit_entry["description"])

        peak_field_keys = [field.get("key") for field in peak_detect_entry["config_fields"]]
        self.assertEqual(peak_detect_entry["resolved_options"]["min_distance"], 1)
        self.assertIn("min_height", peak_field_keys)
        self.assertIn("min_distance", peak_field_keys)
        self.assertIn("min_distance_x", peak_field_keys)
        self.assertIn("min_depth", peak_field_keys)
        self.assertIn("prominence", peak_field_keys)

        corr_fields = {field.get("key"): field for field in correlation_entry["config_fields"]}
        self.assertEqual(correlation_entry["resolved_options"]["method"], "pearson")
        self.assertEqual(list(corr_fields["method"].get("choices") or []), ["pearson", "spearman"])

    def test_build_extension_entry_exposes_normalized_metadata_and_resolved_options(self):
        from core.extension_api import ExtensionConfigField, ProcessingExtension, build_extension_entry

        def _noop(xs, ys, params):
            return list(xs), list(ys)

        entry = build_extension_entry(
            ProcessingExtension(
                type="schema_probe",
                name="Schema Probe",
                handler=_noop,
                config_fields=[
                    ExtensionConfigField(
                        key="factor",
                        field_type="number",
                        default=2.5,
                    )
                ],
            )
        )

        self.assertEqual(entry["id"], "schema_probe")
        self.assertEqual(entry["function_category"], "processing")
        self.assertEqual(entry["function_label"], "处理扩展")
        self.assertEqual(entry["source_kind"], "builtin")
        self.assertEqual(entry["origin_label"], "内置")
        self.assertEqual(entry["resolved_options"], {"factor": 2.5})
        self.assertNotIn("default_options", entry)
        self.assertFalse(any(field.get("key") == "lines_list" for field in entry["config_fields"]))
        self.assertFalse(any(field.get("key") == "lines_list" for field in entry["normalized_config_fields"]))

    def test_build_extension_entry_normalizes_legacy_all_lines_default(self):
        from core.extension_api import ProcessingExtension, build_extension_entry

        with self.assertRaises(ValueError):
            build_extension_entry(
                ProcessingExtension(
                    type="legacy_lines_all",
                    name="Legacy All",
                    handler=lambda xs, ys, params: (list(xs), list(ys)),
                    default_options={"lines": {"number": -1, "lines_list": "all"}},
                )
            )

    def test_extension_registry_supports_digitize_extensions(self):
        from core.extension_api import DigitizeExtension, ExtensionRegistry, build_extension_entry

        def _digitize(image, params=None, mask=None):
            return {"x": [1.0], "y": [2.0], "image": image, "params": params, "mask": mask}

        registry = ExtensionRegistry()
        registry.register_digitize(
            DigitizeExtension(
                type="digitize_probe",
                name="数字化探针",
                handler=_digitize,
            )
        )

        extension = registry.get_digitize("digitize_probe")
        self.assertIsNotNone(extension)
        self.assertEqual([item.type for item in registry.list_digitize()], ["digitize_probe"])

        entry = build_extension_entry(extension)
        self.assertEqual(entry["id"], "digitize_probe")
        self.assertEqual(entry["function_category"], "digitize")
        self.assertEqual(entry["function_label"], "数字化扩展")
        self.assertEqual(entry["resolved_options"], {})
        self.assertNotIn("default_options", entry)

    def test_reload_configured_extensions_registers_listed_builtin_wrappers(self):
        from core.extension_api import build_extension_entry, extension_registry, reload_configured_extensions

        reload_configured_extensions()

        processing_entry = build_extension_entry(extension_registry.get_processing("crop"))
        analysis_entry = build_extension_entry(extension_registry.get_analysis("statistics"))

        self.assertEqual(processing_entry["source_kind"], "builtin")
        self.assertTrue(processing_entry["listed"])
        self.assertEqual(analysis_entry["source_kind"], "builtin")
        self.assertTrue(analysis_entry["listed"])

    def test_global_asset_extension_configs_preserve_extension_version(self):
        from core.global_assets import GlobalAssetManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = GlobalAssetManager(Path(temp_dir) / "global_assets.json")
            default_config = manager.ensure_extension_default_config(
                "processing",
                "version_probe",
                "版本探针",
                {"factor": 2},
                extension_version="1.2.3",
            )
            saved = manager.add_extension_config(
                category="processing",
                extension_type="version_probe",
                extension_name="版本探针",
                extension_version="1.2.3",
                name="方案A",
                options={"factor": 8},
            )

            self.assertEqual(default_config.extension_version, "1.2.3")
            self.assertEqual(saved.extension_version, "1.2.3")

            updated = manager.update_extension_config(
                saved.id,
                options={"factor": 9},
                extension_version="1.3.0",
            )

            self.assertIsNotNone(updated)
            self.assertEqual(updated.extension_version, "1.3.0")

    def test_repository_demo_extensions_and_json_samples_are_valid(self):
        from core.extension_api import ExtensionRegistry, default_extensions_directory

        directory = default_extensions_directory()
        expected = {
            "processing_kalman_filter_demo.py": ("processing", "kalman_filter", {"lines_list", "process_variance", "measurement_variance", "initial_estimate", "initial_error_covariance"}),
            "processing_multi_curve_mean_demo.py": ("processing", "multi_curve_mean", {"lines_list"}),
            "analysis_spectrum_demo.py": ("analysis", "spectrum_analysis", {"lines_list", "sampling_rate", "window", "detrend", "max_frequency", "line_color"}),
            "analysis_multi_curve_correlation_demo.py": ("analysis", "multi_curve_correlation", {"lines_list", "method", "line_color"}),
            "plot_reference_line_demo.py": ("plot", "demo_plot_reference_line", {"show_reference_line", "line_color", "line_style", "line_width", "offset", "label", "annotate_peak"}),
            "plot_dual_curve_band_demo.py": ("plot", "plot_dual_curve_band", {"lines_list", "align_mode", "resample_mode", "n", "step", "fill_color", "fill_alpha", "label", "annotate_max_gap"}),
            "plot_arrow_annotation_demo.py": ("plot", "plot_arrow_annotation", {"coordinate_mode", "start_x", "start_y", "end_x", "end_y", "text"}),
            "plot_rectangle_annotation_demo.py": ("plot", "plot_rectangle_annotation", {"coordinate_mode", "x", "y", "width", "height", "edge_color"}),
            "plot_circle_annotation_demo.py": ("plot", "plot_circle_annotation", {"coordinate_mode", "center_x", "center_y", "radius", "edge_color"}),
            "plot_text_annotation_demo.py": ("plot", "plot_text_annotation", {"coordinate_mode", "x", "y", "text", "color"}),
        }

        registry = ExtensionRegistry()
        report = registry.load_from_directory(directory)

        self.assertEqual(report["errors"], [])
        self.assertTrue(set(expected).issubset({Path(path).name for path in report["loaded"]}))

        getters = {
            "processing": registry.get_processing,
            "analysis": registry.get_analysis,
            "plot": registry.get_plot,
        }

        self.assertEqual(sorted(path.name for path in directory.glob("*.json")), [])

        for _py_name, (kind, type_id, required_keys) in expected.items():
            extension = getters[kind](type_id)
            self.assertIsNotNone(extension)
            resolved_defaults = extension.resolved_default_options
            self.assertTrue(required_keys.issubset(set(resolved_defaults.keys())))

    def test_repository_demo_plot_extensions_all_support_settings(self):
        from core.extension_api import ExtensionRegistry, default_extensions_directory

        registry = ExtensionRegistry()
        report = registry.load_from_directory(default_extensions_directory())

        self.assertEqual(report["errors"], [])
        self.assertTrue(registry.list_plot())
        self.assertTrue(all(bool(getattr(extension, "settings", False)) for extension in registry.list_plot()))


# ══════════════════════════════════════════════════════════════════
# 5. core/data_operations.py
# ══════════════════════════════════════════════════════════════════

class TestDataOperations(unittest.TestCase):

    def _write_temp(self, content: str, suffix=".csv") -> str:
        f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix,
                                        delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return f.name

    def test_import_csv_two_columns(self):
        from core.data_operations import import_csv
        content = "x,y\n1.0,2.0\n2.0,4.0\n3.0,6.0\n"
        path = self._write_temp(content)
        try:
            series_list = import_csv(path)
            self.assertEqual(len(series_list), 1)
            self.assertEqual(series_list[0].x, [1.0, 2.0, 3.0])
            self.assertEqual(series_list[0].y, [2.0, 4.0, 6.0])
        finally:
            os.unlink(path)

    def test_import_csv_multi_column(self):
        from core.data_operations import import_csv
        content = "x,y1,y2\n1,10,100\n2,20,200\n3,30,300\n"
        path = self._write_temp(content)
        try:
            series_list = import_csv(path)
            self.assertEqual(len(series_list), 2)  # 2 Y columns
        finally:
            os.unlink(path)

    def test_import_csv_tab_separated(self):
        from core.data_operations import import_csv
        content = "x\ty\n1.0\t10.0\n2.0\t20.0\n"
        path = self._write_temp(content, ".txt")
        try:
            series_list = import_csv(path)
            self.assertEqual(len(series_list), 1)
            self.assertEqual(series_list[0].x[0], 1.0)
        finally:
            os.unlink(path)

    def test_import_csv_no_header(self):
        from core.data_operations import import_csv
        content = "1.0,2.0\n3.0,4.0\n5.0,6.0\n"
        path = self._write_temp(content)
        try:
            series_list = import_csv(path)
            self.assertEqual(len(series_list), 1)
            self.assertEqual(len(series_list[0].x), 3)
        finally:
            os.unlink(path)

    def test_import_json_list_format(self):
        from core.data_operations import import_json
        data = [{"x": 1, "y": 2}, {"x": 3, "y": 4}, {"x": 5, "y": 6}]
        path = self._write_temp(json.dumps(data), ".json")
        try:
            series_list = import_json(path)
            self.assertEqual(len(series_list), 1)
            self.assertEqual(series_list[0].x, [1.0, 3.0, 5.0])
            self.assertEqual(series_list[0].y, [2.0, 4.0, 6.0])
        finally:
            os.unlink(path)

    def test_import_json_dict_format(self):
        from core.data_operations import import_json
        data = {"time": [0.0, 1.0, 2.0], "force": [0.0, 10.0, 20.0]}
        path = self._write_temp(json.dumps(data), ".json")
        try:
            series_list = import_json(path)
            self.assertGreater(len(series_list), 0)
        finally:
            os.unlink(path)

    def test_import_file_dispatch_csv(self):
        from core.data_operations import import_file
        content = "x,y\n1,2\n3,4\n"
        path = self._write_temp(content, ".csv")
        try:
            result = import_file(path)
            self.assertGreater(len(result), 0)
        finally:
            os.unlink(path)

    def test_import_file_dispatch_json(self):
        from core.data_operations import import_file
        data = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
        path = self._write_temp(json.dumps(data), ".json")
        try:
            result = import_file(path)
            self.assertGreater(len(result), 0)
        finally:
            os.unlink(path)

    def test_import_numpy(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("NumPy not available")
        from core.data_operations import import_numpy
        arr = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        path = tempfile.mktemp(suffix=".npy")
        try:
            np.save(path, arr)
            series_list = import_numpy(path)
            self.assertGreater(len(series_list), 0)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_curve_to_series(self):
        from core.data_operations import curve_to_series
        from models.schemas import Curve
        curve = Curve(name="test_curve",
                      x_actual=[1.0, 2.0], y_actual=[3.0, 4.0])
        s = curve_to_series(curve)
        self.assertEqual(s.name, "test_curve")
        self.assertEqual(s.x, [1.0, 2.0])
        self.assertEqual(s.y, [3.0, 4.0])
        self.assertEqual(s.source, "pyline_curve_copy")


# ══════════════════════════════════════════════════════════════════
# 6. ai/command_layer.py
# ══════════════════════════════════════════════════════════════════

class TestCommandLayer(unittest.TestCase):

    def setUp(self):
        from core.project_manager import ProjectManager
        self._restore_assets = _patch_global_assets()
        self.pm = ProjectManager()
        self.p = self.pm.create_new("ai_test")
        self.pm.migrate_to_v2(self.p)
        from models.schemas import DataFile, DataSeries
        s = DataSeries(name="col1", x=[float(i) for i in range(20)],
                       y=[float(i) ** 2 for i in range(20)])
        df = DataFile(name="data.csv", series=[s])
        self.pm.add_data_file(df)
        self.series_id = s.id

        # Patch global project_manager reference in both modules
        import core.project_manager as pm_module
        import ai.command_layer as cl_module
        self._orig_pm = pm_module.project_manager
        self._orig_cl_pm = cl_module.project_manager
        pm_module.project_manager = self.pm
        cl_module.project_manager = self.pm
        self._cl = cl_module

    def tearDown(self):
        import core.project_manager as pm_module
        import ai.command_layer as cl_module
        pm_module.project_manager = self._orig_pm
        cl_module.project_manager = self._orig_cl_pm
        self._restore_assets()

    def test_get_project_summary(self):
        from ai.command_layer import cmd_get_project_summary
        r = cmd_get_project_summary({})
        self.assertTrue(r.success)
        self.assertEqual(r.data["name"], "ai_test")

    def test_list_data_files(self):
        from ai.command_layer import cmd_list_data_files
        r = cmd_list_data_files({})
        self.assertTrue(r.success)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["name"], "data.csv")

    def test_create_folder(self):
        from ai.command_layer import cmd_create_folder
        r = cmd_create_folder({"name": "new_folder"})
        self.assertTrue(r.success)
        self.assertIn("id", r.data)

    def test_apply_pipeline(self):
        from ai.command_layer import cmd_apply_pipeline
        ops = [{"type": "normalize", "params": {"mode": "minmax"}}]
        r = cmd_apply_pipeline({"series_id": self.series_id, "ops": ops})
        self.assertTrue(r.success)
        self.assertIn("n", r.data)
        self.assertGreater(r.data["n"], 0)

    def test_save_and_list_pipeline(self):
        from ai.command_layer import cmd_save_pipeline, cmd_list_saved_pipelines
        ops = [{"type": "smooth", "params": {}}]
        r = cmd_save_pipeline({"name": "my_pipe", "ops": ops})
        self.assertTrue(r.success)
        r2 = cmd_list_saved_pipelines({})
        self.assertTrue(r2.success)
        names = [item["name"] for item in r2.data]
        self.assertIn("my_pipe", names)

    def test_fit_curve_command(self):
        from ai.command_layer import cmd_fit_curve
        r = cmd_fit_curve({"series_id": self.series_id, "model": "poly2"})
        self.assertTrue(r.success)
        self.assertIn("r2", r.data)
        self.assertGreater(r.data["r2"], 0.99)

    def test_detect_peaks_command(self):
        from ai.command_layer import cmd_detect_peaks
        r = cmd_detect_peaks({"series_id": self.series_id, "min_distance": 2})
        self.assertTrue(r.success)

    def test_detect_peaks_command_accepts_series_name(self):
        from ai.command_layer import cmd_detect_peaks

        self.pm.current_project.data_files[0].series[0].name = "eta2_crop_resample_fft"
        r = cmd_detect_peaks({"series_id": "eta2_crop_resample_fft", "min_distance": 2})

        self.assertTrue(r.success)

    def test_detect_peaks_command_supports_x_distance(self):
        from ai.command_layer import cmd_detect_peaks

        series = self.pm.current_project.data_files[0].series[0]
        series.x = [0.0, 0.2, 0.4, 0.6, 1.0, 1.2, 1.4, 1.6]
        series.y = [0.0, 1.0, 0.0, 0.9, 0.0, 0.0, 0.8, 0.0]
        r = cmd_detect_peaks({"series_id": self.series_id, "min_distance_x": 0.7})

        self.assertTrue(r.success)
        self.assertEqual(r.data["count"], 2)

    def test_compute_statistics_command(self):
        from ai.command_layer import cmd_compute_statistics
        r = cmd_compute_statistics({"series_id": self.series_id})
        self.assertTrue(r.success)
        self.assertIn("y_mean", r.data)

    def test_compute_correlation_command(self):
        from ai.command_layer import cmd_compute_correlation
        from models.schemas import DataFile, DataSeries
        s2 = DataSeries(name="col2",
                        x=[float(i) for i in range(20)],
                        y=[float(i) * 3 for i in range(20)])
        df2 = DataFile(name="d2.csv", series=[s2])
        self.pm.add_data_file(df2)
        # Must also be reachable via find_series; add to datasets too
        ds = self.pm.add_dataset("ds_corr")
        self.pm.add_series_to_dataset(ds.id, s2)
        # Also add first series
        ds2 = self.pm.add_series_to_dataset(ds.id, self.p.data_files[0].series[0])
        r = cmd_compute_correlation({
            "series_id1": self.series_id,
            "series_id2": s2.id,
        })
        self.assertTrue(r.success)
        self.assertIn("r", r.data)

    def test_command_dispatcher_execute(self):
        from ai.command_layer import CommandDispatcher
        d = CommandDispatcher()
        r = d.execute({"action": "get_project_summary", "params": {}})
        self.assertTrue(r.success)

    def test_command_dispatcher_unknown_action(self):
        from ai.command_layer import CommandDispatcher
        d = CommandDispatcher()
        r = d.execute({"action": "does_not_exist", "params": {}})
        self.assertFalse(r.success)
        self.assertIn("未知命令", r.error)

    def test_get_tools_schema_format(self):
        from ai.command_layer import CommandDispatcher, COMMANDS
        d = CommandDispatcher()
        tools = d.get_tools_schema()
        self.assertEqual(len(tools), len(COMMANDS))
        for tool in tools:
            self.assertEqual(tool["type"], "function")
            self.assertIn("name", tool["function"])
            self.assertIn("description", tool["function"])
            self.assertIn("parameters", tool["function"])


# ══════════════════════════════════════════════════════════════════
# 7. core/ai_client.py
# ══════════════════════════════════════════════════════════════════

class TestAIClient(unittest.TestCase):

    def test_config_defaults(self):
        from core.ai_client import AIConfig
        cfg = AIConfig()
        self.assertEqual(cfg.provider, "openai_compatible")
        self.assertEqual(cfg.model, "gpt-4o-mini")
        self.assertEqual(cfg.timeout, 60)
        self.assertAlmostEqual(cfg.top_p, 1.0)
        self.assertEqual(cfg.system_prompt, "")

    def test_config_save_load(self):
        from core.ai_client import AIConfig
        import unittest.mock as mock
        cfg = AIConfig(
            model="test-model",
            api_key="sk-test",
            timeout=30,
            top_p=0.8,
            system_prompt="请使用中文回答",
            ollama_keep_alive="10m",
            ollama_num_ctx=8192,
        )
        path = tempfile.mktemp(suffix=".json")
        try:
            with mock.patch("core.ai_client._CONFIG_PATH", __import__("pathlib").Path(path)):
                cfg.save()
                cfg2 = AIConfig.load()
            self.assertEqual(cfg2.model, "test-model")
            self.assertEqual(cfg2.api_key, "sk-test")
            self.assertEqual(cfg2.timeout, 30)
            self.assertAlmostEqual(cfg2.top_p, 0.8)
            self.assertEqual(cfg2.system_prompt, "请使用中文回答")
            self.assertEqual(cfg2.ollama_keep_alive, "10m")
            self.assertEqual(cfg2.ollama_num_ctx, 8192)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_config_load_missing_file(self):
        from core.ai_client import AIConfig
        import unittest.mock as mock
        with mock.patch("core.ai_client._CONFIG_PATH",
                        __import__("pathlib").Path("/nonexistent/path.json")):
            cfg = AIConfig.load()
        self.assertEqual(cfg.provider, "openai_compatible")

    def test_config_load_corrupt_file(self):
        from core.ai_client import AIConfig
        import unittest.mock as mock
        path = tempfile.mktemp(suffix=".json")
        try:
            with open(path, "w") as f:
                f.write("{bad json}")
            with mock.patch("core.ai_client._CONFIG_PATH",
                            __import__("pathlib").Path(path)):
                cfg = AIConfig.load()
            self.assertEqual(cfg.provider, "openai_compatible")  # returns default
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_ai_response_model(self):
        from core.ai_client import AIResponse
        r = AIResponse(content="hello", tool_calls=[])
        self.assertEqual(r.content, "hello")
        self.assertIsNone(r.error)

    def test_config_temperature_default(self):
        from core.ai_client import AIConfig
        cfg = AIConfig()
        self.assertAlmostEqual(cfg.temperature, 0.7)

    def test_config_max_tokens_default(self):
        from core.ai_client import AIConfig
        cfg = AIConfig()
        self.assertEqual(cfg.max_tokens, 2048)

    def test_config_temperature_custom(self):
        from core.ai_client import AIConfig
        cfg = AIConfig(temperature=0.2, top_p=0.6, max_tokens=512)
        self.assertAlmostEqual(cfg.temperature, 0.2)
        self.assertAlmostEqual(cfg.top_p, 0.6)
        self.assertEqual(cfg.max_tokens, 512)

    def test_config_save_load_temperature(self):
        from core.ai_client import AIConfig
        import unittest.mock as mock
        cfg = AIConfig(temperature=0.1, top_p=0.5, max_tokens=1024)
        path = tempfile.mktemp(suffix=".json")
        try:
            with mock.patch("core.ai_client._CONFIG_PATH", __import__("pathlib").Path(path)):
                cfg.save()
                cfg2 = AIConfig.load()
            self.assertAlmostEqual(cfg2.temperature, 0.1)
            self.assertAlmostEqual(cfg2.top_p, 0.5)
            self.assertEqual(cfg2.max_tokens, 1024)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_provider_presets_expose_models(self):
        from core.ai.providers import get_provider_preset, list_builtin_models

        preset = get_provider_preset("ollama")
        self.assertTrue(preset["supports_model_discovery"])
        self.assertFalse(preset["api_key_required"])
        self.assertIn("llama3.1:8b", list_builtin_models("ollama"))

    def test_ai_client_injects_system_prompt(self):
        from core.ai_client import AIClient, AIConfig

        client = AIClient(AIConfig(system_prompt="请使用中文回答"))
        messages = client._with_global_system_prompt([
            {"role": "system", "content": "保持回答精炼"},
            {"role": "user", "content": "ping"},
        ])

        self.assertTrue(messages[0]["content"].startswith("请使用中文回答"))
        self.assertIn("保持回答精炼", messages[0]["content"])

    def test_list_available_models_sync_reads_ollama_tags(self):
        from core.ai_client import AIClient, AIConfig
        import unittest.mock as mock

        class _FakeResponse:
            def __init__(self, payload: bytes):
                self._payload = payload

            def read(self) -> bytes:
                return self._payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        payload = json.dumps({
            "models": [
                {"name": "qwen2.5:7b"},
                {"model": "llama3.1:8b"},
            ]
        }).encode("utf-8")
        client = AIClient(AIConfig(provider="ollama", base_url="http://localhost:11434/v1"))

        with mock.patch("core.ai_client.urlopen", return_value=_FakeResponse(payload)) as mocked:
            models = client.list_available_models_sync()

        self.assertEqual(models, ["qwen2.5:7b", "llama3.1:8b"])
        request = mocked.call_args.args[0]
        self.assertIn("/api/tags", request.full_url)

    def test_list_available_models_sync_passes_ollama_api_key(self):
        from core.ai_client import AIClient, AIConfig
        import unittest.mock as mock

        class _FakeResponse:
            def read(self) -> bytes:
                return json.dumps({"models": []}).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        client = AIClient(AIConfig(provider="ollama", base_url="http://localhost:11434/v1", api_key="sk-ollama"))

        with mock.patch("core.ai_client.urlopen", return_value=_FakeResponse()) as mocked:
            client.list_available_models_sync()

        request = mocked.call_args.args[0]
        self.assertEqual(request.headers.get("Authorization"), "Bearer sk-ollama")

    def test_ollama_chat_payload_uses_openai_v1_shape(self):
        from core.ai_client import AIClient, AIConfig

        client = AIClient(AIConfig(provider="ollama", base_url="http://localhost:11434/v1"))
        payload = client._build_chat_payload([{"role": "user", "content": "ping"}], tools=[])

        self.assertNotIn("options", payload)
        self.assertNotIn("keep_alive", payload)
        self.assertEqual(payload["model"], client.config.model)


class TestMainEntry(unittest.TestCase):

    def test_infer_linux_input_method_from_xmodifiers(self):
        from main import _infer_linux_input_method

        env = {"XMODIFIERS": "@im=fcitx"}
        self.assertEqual(_infer_linux_input_method(env), "fcitx")

    def test_configure_linux_environment_sets_qt_im_module(self):
        from main import _configure_linux_environment
        import unittest.mock as mock

        env = {"GTK_IM_MODULE": "ibus"}
        with mock.patch("main.sys.platform", "linux"):
            _configure_linux_environment(env)
        self.assertEqual(env.get("QT_IM_MODULE"), "ibus")

    def test_configure_linux_environment_preserves_existing_qt_im_module(self):
        from main import _configure_linux_environment
        import unittest.mock as mock

        env = {"QT_IM_MODULE": "fcitx", "GTK_IM_MODULE": "ibus"}
        with mock.patch("main.sys.platform", "linux"):
            _configure_linux_environment(env)
        self.assertEqual(env.get("QT_IM_MODULE"), "fcitx")


# ══════════════════════════════════════════════════════════════════
# 8. v0.3 schema 新增节点类型和字段
# ══════════════════════════════════════════════════════════════════

class TestSchemasV3(unittest.TestCase):

    def test_folder_node_group_type_default_none(self):
        from models.schemas import FolderNode
        node = FolderNode(name="test")
        self.assertIsNone(node.group_type)

    def test_folder_node_group_type_datasets(self):
        from models.schemas import FolderNode
        node = FolderNode(name="数据集", group_type="datasets")
        self.assertEqual(node.group_type, "datasets")

    def test_folder_node_group_type_images(self):
        from models.schemas import FolderNode
        node = FolderNode(name="图片集", group_type="images")
        self.assertEqual(node.group_type, "images")

    def test_folder_node_group_type_tools(self):
        from models.schemas import FolderNode
        node = FolderNode(name="工具集", group_type="tools")
        self.assertEqual(node.group_type, "tools")

    def test_folder_node_group_type_pipeline_group(self):
        from models.schemas import FolderNode
        node = FolderNode(name="Pipelines", group_type="pipeline_group")
        self.assertEqual(node.group_type, "pipeline_group")

    def test_folder_node_group_type_user(self):
        from models.schemas import FolderNode
        node = FolderNode(name="用户文件夹", group_type="user")
        self.assertEqual(node.group_type, "user")

    def test_ai_prompt_node_kind(self):
        from models.schemas import AIPromptNode
        node = AIPromptNode(name="my_prompt", prompt_id="pid1")
        self.assertEqual(node.kind, "ai_prompt")
        self.assertEqual(node.prompt_id, "pid1")

    def test_ai_skill_node_kind(self):
        from models.schemas import AISkillNode
        node = AISkillNode(name="my_skill", skill_id="sid1")
        self.assertEqual(node.kind, "ai_skill")
        self.assertEqual(node.skill_id, "sid1")

    def test_ai_agent_node_kind(self):
        from models.schemas import AIAgentNode
        node = AIAgentNode(name="my_agent", agent_id="agid1")
        self.assertEqual(node.kind, "ai_agent")
        self.assertEqual(node.agent_id, "agid1")

    def test_ai_nodes_roundtrip(self):
        from models.schemas import AIPromptNode, AISkillNode, AIAgentNode, ProjectTree
        nodes = [
            AIPromptNode(name="p1", prompt_id="p1id"),
            AISkillNode(name="s1", skill_id="s1id"),
            AIAgentNode(name="a1", agent_id="a1id"),
        ]
        tree = ProjectTree(nodes=nodes)
        data = tree.model_dump()
        tree2 = ProjectTree(**data)
        kinds = [n.kind for n in tree2.nodes]
        self.assertEqual(kinds, ["ai_prompt", "ai_skill", "ai_agent"])

    def test_report_template_model(self):
        from models.schemas import ReportTemplate
        t = ReportTemplate(name="tmpl1", content="# Hello {{date}}")
        self.assertFalse(t.is_builtin)
        self.assertEqual(t.content, "# Hello {{date}}")

    def test_report_template_builtin_flag(self):
        from models.schemas import ReportTemplate
        t = ReportTemplate(name="default", content="", is_builtin=True)
        self.assertTrue(t.is_builtin)

    def test_project_v3_fields_exist(self):
        from models.schemas import Project
        p = Project.create_new("p")
        self.assertIsInstance(p.ai_prompts, list)
        self.assertIsInstance(p.ai_skills, list)
        self.assertIsInstance(p.ai_agents, list)
        self.assertIsInstance(p.report_templates, list)


# ══════════════════════════════════════════════════════════════════
# 9. ProjectManager v0.3 新增功能
# ══════════════════════════════════════════════════════════════════

class TestProjectManagerV3(unittest.TestCase):

    def setUp(self):
        from core.project_manager import ProjectManager
        self._restore_assets = _patch_global_assets()
        self.pm = ProjectManager()
        self.p = self.pm.create_new("v3_test")

    def tearDown(self):
        self._restore_assets()

    def test_new_project_has_tree(self):
        """v0.3 新建项目应立即有树（不需要 migrate）"""
        self.assertIsNotNone(self.p.tree)
        self.assertGreater(len(self.p.tree.nodes), 0)

    def test_create_new_with_structure_uses_aline_suffix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self.pm.create_new("aline_suffix_demo", parent_dir=temp_dir, create_structure=True)

            self.assertIsNotNone(project.file_path)
            self.assertTrue(project.file_path.endswith(".aline"))
            self.assertTrue(Path(project.file_path).exists())

    def test_system_folders_have_group_type(self):
        """系统文件夹应携带 group_type"""
        group_types = [n.group_type for n in self.p.tree.nodes
                       if n.kind == "folder" and n.group_type is not None]
        self.assertGreater(len(group_types), 0)

    def test_migrate_to_v3_infers_group_type(self):
        """旧 v0.2 文件迁移到 v0.3 后，系统文件夹应有 group_type"""
        from core.project_manager import ProjectManager
        pm2 = ProjectManager()
        p2 = pm2.create_new("old")
        p2.tree = None  # 模拟旧 v0.2 无树
        pm2.migrate_to_v2(p2)
        pm2.migrate_to_v3(p2)
        group_types = [n.group_type for n in p2.tree.nodes
                       if n.kind == "folder" and n.group_type is not None]
        self.assertGreater(len(group_types), 0)

    def test_add_ai_prompt(self):
        from core.global_assets import global_assets

        obj = self.pm.add_ai_prompt("test_prompt", "System: you are a helper", "Test prompt")
        self.assertIsNotNone(obj)
        self.assertEqual(obj.name, "test_prompt")
        self.assertEqual(global_assets.get_ai_prompt(obj.id).name, "test_prompt")

    def test_delete_ai_prompt(self):
        from core.global_assets import global_assets

        obj = self.pm.add_ai_prompt("to_delete", "content", "")
        self.assertIsNotNone(global_assets.get_ai_prompt(obj.id))
        result = self.pm.delete_ai_prompt(obj.id)
        self.assertTrue(result)
        self.assertIsNone(global_assets.get_ai_prompt(obj.id))

    def test_add_ai_skill(self):
        from core.global_assets import global_assets

        obj = self.pm.add_ai_skill("my_skill", "result = 42", "A skill")
        self.assertIsNotNone(obj)
        self.assertEqual(obj.name, "my_skill")
        self.assertEqual(global_assets.get_ai_skill(obj.id).name, "my_skill")

    def test_delete_ai_skill(self):
        from core.global_assets import global_assets

        obj = self.pm.add_ai_skill("to_del_skill", "result = 1", "")
        result = self.pm.delete_ai_skill(obj.id)
        self.assertTrue(result)
        self.assertIsNone(global_assets.get_ai_skill(obj.id))

    def test_add_ai_agent(self):
        from core.global_assets import global_assets

        obj = self.pm.add_ai_agent("data_agent", "You analyze data.", "Data agent")
        self.assertIsNotNone(obj)
        self.assertEqual(global_assets.get_ai_agent(obj.id).name, "data_agent")

    def test_delete_ai_agent(self):
        from core.global_assets import global_assets

        obj = self.pm.add_ai_agent("to_del_agent", "content", "")
        result = self.pm.delete_ai_agent(obj.id)
        self.assertTrue(result)
        self.assertIsNone(global_assets.get_ai_agent(obj.id))

    def test_add_report_template(self):
        from core.global_assets import global_assets

        tmpl = self.pm.add_report_template("my_tmpl", "# Report\n{{date}}")
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl.name, "my_tmpl")
        self.assertEqual(global_assets.get_report_template(tmpl.id).name, "my_tmpl")

    def test_delete_report_template(self):
        from core.global_assets import global_assets

        tmpl = self.pm.add_report_template("del_tmpl", "content")
        result = self.pm.delete_report_template(tmpl.id)
        self.assertTrue(result)
        self.assertIsNone(global_assets.get_report_template(tmpl.id))

    def test_new_project_has_only_root_system_groups(self):
        root_groups = [
            getattr(n, "group_type", None)
            for n in self.p.tree.nodes
            if n.kind == "folder" and getattr(n, "parent_id", None) is None
        ]
        self.assertEqual(root_groups, ["source_files", "datasets", "pictures", "images", "analysis_result_group"])

    def test_rename_series(self):
        from models.schemas import DataFile, DataSeries

        series = DataSeries(name="old_series", x=[1.0], y=[2.0])
        self.pm.add_data_file(DataFile(name="a.csv", series=[series]))
        result = self.pm.rename_series(series.id, "new_series")
        self.assertTrue(result)
        self.assertEqual(self.p.find_series(series.id).name, "new_series")

    def test_delete_series(self):
        from models.schemas import DataFile, DataSeries

        series = DataSeries(name="drop_series", x=[1.0], y=[2.0])
        df = DataFile(name="a.csv", series=[series])
        self.pm.add_data_file(df)
        result = self.pm.delete_series(series.id)
        self.assertTrue(result)
        self.assertIsNone(self.p.find_series(series.id))

    def test_move_series_to_other_data_file(self):
        from models.schemas import DataFile, DataSeries

        series = DataSeries(name="move_series", x=[1.0], y=[2.0])
        df1 = DataFile(name="a.csv", series=[series])
        df2 = DataFile(name="b.csv", series=[])
        self.pm.add_data_file(df1)
        self.pm.add_data_file(df2)
        result = self.pm.move_series_to_data_file(series.id, df2.id)
        self.assertTrue(result)
        self.assertEqual(len(df1.series), 0)
        self.assertEqual(df2.series[0].id, series.id)

    def test_rename_curve(self):
        img = self.pm.add_image("fake.png", "img_a")
        curve = self.pm.add_curve_to_image(img.id, [1.0, 2.0], [3.0, 4.0], name="old_curve")
        result = self.pm.rename_curve(curve.id, "new_curve")
        self.assertTrue(result)
        self.assertEqual(self.pm.get_curve(curve.id).name, "new_curve")

    def test_delete_curve(self):
        img = self.pm.add_image("fake.png", "img_a")
        curve = self.pm.add_curve_to_image(img.id, [1.0, 2.0], [3.0, 4.0], name="drop_curve")
        result = self.pm.delete_curve(curve.id)
        self.assertTrue(result)
        self.assertIsNone(self.pm.get_curve(curve.id))

    def test_move_curve_to_other_image(self):
        img1 = self.pm.add_image("fake_1.png", "img_a")
        img2 = self.pm.add_image("fake_2.png", "img_b")
        curve = self.pm.add_curve_to_image(img1.id, [1.0, 2.0], [3.0, 4.0], name="move_curve")
        result = self.pm.move_curve_to_image(curve.id, img2.id)
        self.assertTrue(result)
        self.assertEqual(len(img1.curves), 0)
        self.assertEqual(img2.curves[0].id, curve.id)

    def test_get_series_from_node_series_kind(self):
        from models.schemas import DataFile, DataSeries
        s = DataSeries(name="s1", x=[1.0, 2.0], y=[3.0, 4.0])
        df = DataFile(name="d.csv", series=[s])
        self.pm.add_data_file(df)
        found = self.pm.get_series_from_node("series", s.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.id, s.id)

    def test_get_all_series_from_node_data_file(self):
        from models.schemas import DataFile, DataSeries
        s1 = DataSeries(name="a", x=[1.0], y=[2.0])
        s2 = DataSeries(name="b", x=[3.0], y=[4.0])
        df = DataFile(name="multi.csv", series=[s1, s2])
        node = self.pm.add_data_file(df)
        series_list = self.pm.get_all_series_from_node("data_file", node.id)
        self.assertEqual(len(series_list), 2)

    def test_find_folder_by_group_type(self):
        folder = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(folder)
        self.assertEqual(folder.group_type, "datasets")

    def test_add_data_file_goes_to_datasets_folder(self):
        from models.schemas import DataFile, DataSeries
        df = DataFile(name="placed.csv", series=[DataSeries(name="s1", x=[1.0], y=[2.0])])
        node = self.pm.add_data_file(df)
        self.assertIsNotNone(node)
        # Parent should be datasets folder
        datasets_folder = self.pm._find_folder_by_group_type("datasets")
        self.assertEqual(node.parent_id, datasets_folder.id)

    def test_update_saved_pipeline_updates_tree_node_name(self):
        from core.global_assets import global_assets

        sp = self.pm.add_saved_pipeline("旧流程", [{"type": "smooth", "params": {}}])
        self.assertIsNotNone(sp)
        updated = self.pm.update_saved_pipeline(sp.id, name="新流程", ops=[{"type": "normalize", "params": {"mode": "minmax"}}])
        self.assertTrue(updated)
        saved = global_assets.get_saved_pipeline(sp.id)
        self.assertEqual(saved.name, "新流程")
        self.assertEqual(saved.ops[0]["type"], "normalize")


# ══════════════════════════════════════════════════════════════════
# 10. render_report 测试
# ══════════════════════════════════════════════════════════════════

class TestRenderReport(unittest.TestCase):

    def test_empty_template_returns_empty(self):
        from core.analysis_engine import render_report
        self.assertEqual(render_report("", {}), "")

    def test_date_placeholder_replaced(self):
        from core.analysis_engine import render_report
        result = render_report("Date: {{date}}", {})
        self.assertNotIn("{{date}}", result)
        self.assertIn("Date:", result)

    def test_analysis_type_placeholder(self):
        from core.analysis_engine import render_report
        result = render_report("Type: {{analysis_type}}", {"analysis_type": "curve_fit"})
        self.assertIn("曲线拟合", result)

    def test_equation_placeholder(self):
        from core.analysis_engine import render_report
        result = render_report("Eq: {{equation}}", {"equation": "y = 2x + 1"})
        self.assertIn("y = 2x + 1", result)

    def test_r2_placeholder(self):
        from core.analysis_engine import render_report
        result = render_report("R2: {{r2}}", {"r2": 0.9812})
        self.assertIn("0.9812", result)

    def test_r2_custom_format(self):
        from core.analysis_engine import render_report
        result = render_report("R2: {{r2:.2f}}", {"r2": 0.9812})
        self.assertIn("0.98", result)

    def test_table_params_with_data(self):
        from core.analysis_engine import render_report
        r = render_report("{{table:params}}",
                          {"params": [2.0, 1.0], "param_names": ["a", "b"]})
        self.assertIn("参数", r)
        self.assertIn("| a |", r)

    def test_table_params_without_data(self):
        from core.analysis_engine import render_report
        r = render_report("{{table:params}}", {})
        self.assertNotIn("{{table:params}}", r)  # placeholder replaced

    def test_table_peaks_with_data(self):
        from core.analysis_engine import render_report
        peaks = [{"x": 1.5, "y": 0.9}, {"x": 4.7, "y": 0.8}]
        r = render_report("{{table:peaks}}", {"peaks": peaks})
        self.assertIn("1.5", r)
        self.assertIn("0.9", r)

    def test_table_peaks_without_data(self):
        from core.analysis_engine import render_report
        r = render_report("{{table:peaks}}", {})
        self.assertNotIn("{{table:peaks}}", r)

    def test_unmatched_placeholder_cleaned(self):
        from core.analysis_engine import render_report
        r = render_report("Value: {{unknown_key}}", {})
        self.assertNotIn("{{unknown_key}}", r)

    def test_source_name_placeholder(self):
        from core.analysis_engine import render_report
        r = render_report("Source: {{source_name}}", {"source_name": "exp1.csv"})
        self.assertIn("exp1.csv", r)

    def test_peak_count_placeholder(self):
        from core.analysis_engine import render_report
        r = render_report("Peaks: {{peak_count}}", {"count": 5})
        self.assertIn("5", r)

    def test_custom_scalar_placeholder_can_be_rendered(self):
        from core.analysis_engine import render_report

        rendered = render_report(
            "主频: {{dominant_frequency:.2f}} Hz",
            {"analysis_type": "spectrum_analysis", "dominant_frequency": 12.3456},
        )

        self.assertIn("12.35", rendered)

    def test_placeholder_list_includes_custom_scalar_keys(self):
        from core.analysis_engine import list_report_template_placeholders

        placeholders = list_report_template_placeholders(
            {"analysis_type": "spectrum_analysis", "dominant_frequency": 12.5}
        )

        self.assertTrue(any(item["token"] == "{{dominant_frequency}}" for item in placeholders))

    def test_builtin_placeholder_groups_are_not_all_common(self):
        from core.analysis_engine import list_report_template_placeholders

        placeholders = list_report_template_placeholders()
        group_by_token = {item["token"]: item["group"] for item in placeholders}

        self.assertEqual(group_by_token["{{date}}"], "通用")
        self.assertEqual(group_by_token["{{r2}}"], "曲线拟合")
        self.assertEqual(group_by_token["{{peak_count}}"], "峰值检测")
        self.assertEqual(group_by_token["{{mae}}"], "误差比较")

    def test_placeholder_list_includes_declared_extension_fields_before_run(self):
        from core.analysis_engine import list_report_template_placeholders
        from core.extension_api import AnalysisExtension, extension_registry

        extension_registry.register_analysis(
            AnalysisExtension(
                type="declared_placeholder_probe",
                name="声明占位符探针",
                handler=lambda inputs, params: {"analysis_type": "declared_placeholder_probe", "dominant_frequency": 9.9},
                report_placeholders=[
                    {"key": "dominant_frequency", "label": "主频", "description": "主频字段"},
                ],
            )
        )
        try:
            placeholders = list_report_template_placeholders()
            entry = next((item for item in placeholders if item["token"] == "{{dominant_frequency}}"), None)
            self.assertIsNotNone(entry)
            self.assertEqual(entry["group"], "声明占位符探针")
        finally:
            extension_registry.unregister_analysis("declared_placeholder_probe")


# ══════════════════════════════════════════════════════════════════
# 11. ai/command_layer.py — 8 new commands
# ══════════════════════════════════════════════════════════════════

class TestCommandLayerV3(unittest.TestCase):

    def setUp(self):
        from core.project_manager import ProjectManager
        self._restore_assets = _patch_global_assets()
        self.pm = ProjectManager()
        self.p = self.pm.create_new("cmd_v3")
        from models.schemas import DataFile, DataSeries
        self.s = DataSeries(name="col1",
                            x=[float(i) for i in range(10)],
                            y=[float(i) * 2 for i in range(10)])
        self.df = DataFile(name="test.csv", series=[self.s])
        self.pm.add_data_file(self.df)

        import core.project_manager as pm_module
        import ai.command_layer as cl_module
        self._orig_pm = pm_module.project_manager
        self._orig_cl = cl_module.project_manager
        pm_module.project_manager = self.pm
        cl_module.project_manager = self.pm

    def tearDown(self):
        import core.project_manager as pm_module
        import ai.command_layer as cl_module
        pm_module.project_manager = self._orig_pm
        cl_module.project_manager = self._orig_cl
        self._restore_assets()

    def test_list_image_works_empty(self):
        from ai.command_layer import cmd_list_image_works
        r = cmd_list_image_works({})
        self.assertTrue(r.success)
        self.assertIsInstance(r.data, list)
        self.assertEqual(len(r.data), 0)

    def test_list_report_templates_empty(self):
        from ai.command_layer import cmd_list_report_templates
        r = cmd_list_report_templates({})
        self.assertTrue(r.success)
        self.assertIsInstance(r.data, list)

    def test_list_report_templates_after_add(self):
        self.pm.add_report_template("report_template_demo", "# Template")
        from ai.command_layer import cmd_list_report_templates
        r = cmd_list_report_templates({})
        self.assertTrue(r.success)
        names = [t["name"] for t in r.data]
        self.assertIn("report_template_demo", names)

    def test_save_figure_template_command(self):
        from ai.command_layer import cmd_save_figure_template
        r = cmd_save_figure_template({
            "name": "my_fig_tmpl",
            "theme": "默认",
            "x_label": "Time (s)",
            "y_label": "Force (N)",
        })
        self.assertTrue(r.success)
        self.assertIn("name", r.data)

    def test_manage_ai_tool_create_prompt(self):
        from ai.command_layer import cmd_manage_ai_tool
        r = cmd_manage_ai_tool({
            "action": "create",
            "tool_type": "prompt",
            "name": "test_p",
            "content": "You are a test prompt.",
            "description": "For test",
        })
        self.assertTrue(r.success)
        self.assertEqual(r.data["type"], "prompt")

    def test_manage_ai_tool_create_skill(self):
        from ai.command_layer import cmd_manage_ai_tool
        r = cmd_manage_ai_tool({
            "action": "create",
            "tool_type": "skill",
            "name": "test_skill",
            "content": "result = 42",
        })
        self.assertTrue(r.success)

    def test_manage_ai_tool_delete_prompt(self):
        from ai.command_layer import cmd_manage_ai_tool
        obj = self.pm.add_ai_prompt("to_del_cmd", "content", "")
        r = cmd_manage_ai_tool({
            "action": "delete",
            "tool_type": "prompt",
            "tool_id": obj.id,
        })
        self.assertTrue(r.success)
        self.assertTrue(r.data["deleted"])

    def test_manage_ai_tool_unknown_type(self):
        from ai.command_layer import cmd_manage_ai_tool
        r = cmd_manage_ai_tool({
            "action": "create",
            "tool_type": "unknown_type",
            "name": "x",
        })
        self.assertFalse(r.success)

    def test_dispatcher_includes_global_ai_tools(self):
        from ai.command_layer import CommandDispatcher, COMMANDS

        prompt = self.pm.add_ai_prompt("prompt_tool", "hello", "desc")
        skill = self.pm.add_ai_skill("skill_tool", "result = {'ok': True}", "desc")
        agent = self.pm.add_ai_agent("agent_tool", "你是一个测试 agent。", "desc")

        dispatcher = CommandDispatcher(runtime_context={"context_text": "ctx"})
        tools = dispatcher.get_tools_schema()
        names = [tool["function"]["name"] for tool in tools]

        self.assertEqual(len(tools), len(COMMANDS) + 3)
        self.assertIn(dispatcher._global_tool_name("global_prompt", prompt.id), names)
        self.assertIn(dispatcher._global_tool_name("global_skill", skill.id), names)
        self.assertIn(dispatcher._global_tool_name("global_agent", agent.id), names)

    def test_dispatcher_executes_global_prompt_tool(self):
        from ai.command_layer import CommandDispatcher

        prompt = self.pm.add_ai_prompt("prompt_tool", "hello", "desc")
        dispatcher = CommandDispatcher()
        action = dispatcher._global_tool_name("global_prompt", prompt.id)
        result = dispatcher.execute({"action": action, "params": {}})

        self.assertTrue(result.success)
        self.assertEqual(result.data["content"], "hello")

    def test_generate_report_default_template(self):
        from ai.command_layer import cmd_generate_report
        r = cmd_generate_report({})
        self.assertTrue(r.success)
        self.assertIn("markdown", r.data)

    def test_export_series_command(self):
        from ai.command_layer import cmd_export_series
        path = tempfile.mktemp(suffix=".csv")
        try:
            r = cmd_export_series({
                "series_id": self.s.id,
                "output_path": path,
            })
            self.assertTrue(r.success)
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("x", content.lower())
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_export_series_missing_params(self):
        from ai.command_layer import cmd_export_series
        r = cmd_export_series({})
        self.assertFalse(r.success)

    def test_commands_dict_has_18_entries(self):
        from ai.command_layer import COMMANDS
        self.assertEqual(len(COMMANDS), 18)


# ══════════════════════════════════════════════════════════════════
# 12. ai/skill_runner.py
# ══════════════════════════════════════════════════════════════════

class TestSkillRunner(unittest.TestCase):

    def setUp(self):
        from ai.skill_runner import SkillRunner
        self.runner = SkillRunner()

    def test_basic_result_captured(self):
        r = self.runner.run("result = 42")
        self.assertTrue(r.success)
        self.assertEqual(r.output, 42)

    def test_arithmetic_expression(self):
        r = self.runner.run("result = 2 ** 10")
        self.assertTrue(r.success)
        self.assertEqual(r.output, 1024)

    def test_stdout_captured(self):
        r = self.runner.run("print('hello_stdout')\nresult = 0")
        self.assertTrue(r.success)
        self.assertIn("hello_stdout", r.stdout)

    def test_error_returns_failure(self):
        r = self.runner.run("result = 1 / 0")
        self.assertFalse(r.success)
        self.assertIn("ZeroDivisionError", r.error)

    def test_undefined_variable_error(self):
        r = self.runner.run("result = undefined_var")
        self.assertFalse(r.success)

    def test_no_result_variable(self):
        r = self.runner.run("x = 5")
        self.assertTrue(r.success)
        self.assertIsNone(r.output)

    def test_math_available(self):
        # math is pre-injected in safe_globals, so can be used directly
        r = self.runner.run("result = math.pi")
        self.assertTrue(r.success)
        self.assertAlmostEqual(r.output, math.pi)

    def test_to_dict_success(self):
        r = self.runner.run("result = 'ok'")
        d = r.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["output"], "ok")

    def test_to_dict_failure(self):
        # Trigger a NameError (result = undefined_var) since ValueError isn't in sandbox
        r = self.runner.run("result = undefined_var")
        d = r.to_dict()
        self.assertFalse(d["success"])
        self.assertIn("NameError", d["error"])


# ══════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
