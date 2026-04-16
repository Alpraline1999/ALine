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
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
            FolderNode, DataFileNode, ImageWorkNode,
            PipelineNode, FigureTemplateNode, ReportTemplateNode,
            AIToolNode, ProjectTree,
        )
        nodes = [
            FolderNode(name="f"),
            DataFileNode(name="df", data_file_id="x1"),
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
        self.assertEqual(kinds, ["folder", "data_file", "image_work", "pipeline",
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
        state = FigureState(theme="Nature", x_label="Time", y_label="Value", show_errbar=True)
        data = state.model_dump()
        restored = FigureState(**data)
        self.assertEqual(restored.theme, "Nature")
        self.assertEqual(restored.x_label, "Time")
        self.assertTrue(restored.show_errbar)

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
        self.pm = ProjectManager()

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

    def test_rename_node(self):
        p = self.pm.create_new("test")
        self.pm.migrate_to_v2(p)
        folder = self.pm.add_folder("original")
        result = self.pm.rename_node(folder.id, "renamed")
        self.assertTrue(result)
        node = p.tree.get_node(folder.id)
        self.assertEqual(node.name, "renamed")

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

    def test_add_and_load_pipeline(self):
        p = self.pm.create_new("test")
        self.pm.migrate_to_v2(p)
        ops = [{"type": "smooth", "params": {"window": 5}},
               {"type": "normalize", "params": {"mode": "minmax"}}]
        sp = self.pm.add_saved_pipeline("my_pipe", ops)
        self.assertIsNotNone(sp)
        loaded = self.pm.load_pipeline(sp.id)
        self.assertEqual(loaded, ops)

    def test_delete_pipeline(self):
        p = self.pm.create_new("test")
        self.pm.migrate_to_v2(p)
        sp = self.pm.add_saved_pipeline("pipe1", [])
        self.assertIsNotNone(sp)
        result = self.pm.delete_saved_pipeline(sp.id)
        self.assertTrue(result)
        self.assertNotIn(sp, p.saved_pipelines)

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

    def test_fit_equation_format(self):
        from core.analysis_engine import fit_curve
        xs, ys = self._linear_data()
        r = fit_curve(xs, ys, "linear")
        self.assertIn("equation", r)
        self.assertIn("=", r["equation"])


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

    def test_config_save_load(self):
        from core.ai_client import AIConfig
        import unittest.mock as mock
        cfg = AIConfig(model="test-model", api_key="sk-test", timeout=30)
        path = tempfile.mktemp(suffix=".json")
        try:
            with mock.patch("core.ai_client._CONFIG_PATH", __import__("pathlib").Path(path)):
                cfg.save()
                cfg2 = AIConfig.load()
            self.assertEqual(cfg2.model, "test-model")
            self.assertEqual(cfg2.api_key, "sk-test")
            self.assertEqual(cfg2.timeout, 30)
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
        cfg = AIConfig(temperature=0.2, max_tokens=512)
        self.assertAlmostEqual(cfg.temperature, 0.2)
        self.assertEqual(cfg.max_tokens, 512)

    def test_config_save_load_temperature(self):
        from core.ai_client import AIConfig
        import unittest.mock as mock
        cfg = AIConfig(temperature=0.1, max_tokens=1024)
        path = tempfile.mktemp(suffix=".json")
        try:
            with mock.patch("core.ai_client._CONFIG_PATH", __import__("pathlib").Path(path)):
                cfg.save()
                cfg2 = AIConfig.load()
            self.assertAlmostEqual(cfg2.temperature, 0.1)
            self.assertEqual(cfg2.max_tokens, 1024)
        finally:
            if os.path.exists(path):
                os.unlink(path)


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
        self.pm = ProjectManager()
        self.p = self.pm.create_new("v3_test")

    def test_new_project_has_tree(self):
        """v0.3 新建项目应立即有树（不需要 migrate）"""
        self.assertIsNotNone(self.p.tree)
        self.assertGreater(len(self.p.tree.nodes), 0)

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
        obj = self.pm.add_ai_prompt("test_prompt", "System: you are a helper", "Test prompt")
        self.assertIsNotNone(obj)
        self.assertEqual(obj.name, "test_prompt")
        self.assertIn(obj, self.p.ai_prompts)

    def test_delete_ai_prompt(self):
        obj = self.pm.add_ai_prompt("to_delete", "content", "")
        self.assertIn(obj, self.p.ai_prompts)
        result = self.pm.delete_ai_prompt(obj.id)
        self.assertTrue(result)
        self.assertNotIn(obj, self.p.ai_prompts)

    def test_add_ai_skill(self):
        obj = self.pm.add_ai_skill("my_skill", "result = 42", "A skill")
        self.assertIsNotNone(obj)
        self.assertEqual(obj.name, "my_skill")
        self.assertIn(obj, self.p.ai_skills)

    def test_delete_ai_skill(self):
        obj = self.pm.add_ai_skill("to_del_skill", "result = 1", "")
        result = self.pm.delete_ai_skill(obj.id)
        self.assertTrue(result)
        self.assertNotIn(obj, self.p.ai_skills)

    def test_add_ai_agent(self):
        obj = self.pm.add_ai_agent("data_agent", "You analyze data.", "Data agent")
        self.assertIsNotNone(obj)
        self.assertIn(obj, self.p.ai_agents)

    def test_delete_ai_agent(self):
        obj = self.pm.add_ai_agent("to_del_agent", "content", "")
        result = self.pm.delete_ai_agent(obj.id)
        self.assertTrue(result)
        self.assertNotIn(obj, self.p.ai_agents)

    def test_add_report_template(self):
        tmpl = self.pm.add_report_template("my_tmpl", "# Report\n{{date}}")
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl.name, "my_tmpl")
        self.assertIn(tmpl, self.p.report_templates)
        self.assertTrue(any(
            n.kind == "report_template" and n.template_id == tmpl.id
            for n in self.p.tree.nodes
        ))

    def test_delete_report_template(self):
        tmpl = self.pm.add_report_template("del_tmpl", "content")
        result = self.pm.delete_report_template(tmpl.id)
        self.assertTrue(result)
        self.assertNotIn(tmpl, self.p.report_templates)
        self.assertFalse(any(
            n.kind == "report_template" and n.template_id == tmpl.id
            for n in self.p.tree.nodes
        ))

    def test_new_project_has_report_template_group(self):
        groups = [
            getattr(n, "group_type", None)
            for n in self.p.tree.nodes
            if n.kind == "folder"
        ]
        self.assertIn("report_template_group", groups)

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
        sp = self.pm.add_saved_pipeline("旧流程", [{"type": "smooth", "params": {}}])
        self.assertIsNotNone(sp)
        updated = self.pm.update_saved_pipeline(sp.id, name="新流程", ops=[{"type": "normalize", "params": {"mode": "minmax"}}])
        self.assertTrue(updated)
        saved = self.p.find_saved_pipeline(sp.id)
        self.assertEqual(saved.name, "新流程")
        self.assertEqual(saved.ops[0]["type"], "normalize")
        node = next((n for n in self.p.tree.nodes if n.kind == "pipeline" and n.pipeline_id == sp.id), None)
        self.assertIsNotNone(node)
        self.assertEqual(node.name, "新流程")


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


# ══════════════════════════════════════════════════════════════════
# 11. ai/command_layer.py — 8 new commands
# ══════════════════════════════════════════════════════════════════

class TestCommandLayerV3(unittest.TestCase):

    def setUp(self):
        from core.project_manager import ProjectManager
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
        self.pm.add_report_template("tmpl1", "# Template")
        from ai.command_layer import cmd_list_report_templates
        r = cmd_list_report_templates({})
        self.assertTrue(r.success)
        names = [t["name"] for t in r.data]
        self.assertIn("tmpl1", names)

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
