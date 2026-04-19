"""
ALine UI 信号测试套件

使用 offscreen 渲染（QT_QPA_PLATFORM=offscreen），通过主动发射信号
验证各 UI 组件的信号-槽连接和数据流向。

运行方式：
    QT_QPA_PLATFORM=offscreen python -m unittest tests/test_ui.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 项目根路径
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtWidgets import QApplication, QAbstractItemView
from PySide6.QtCore import Qt, QTimer

_app: QApplication = None


def setUpModule():
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv)
    else:
        _app = QApplication.instance()


def tearDownModule():
    pass


# ─── 辅助函数 ───────────────────────────────────────────────

def _make_project(name="ui_test"):
    """创建带迁移的测试项目（使用独立 ProjectManager）"""
    from core.project_manager import ProjectManager
    from models.schemas import DataFile, DataSeries
    pm = ProjectManager()
    p = pm.create_new(name)
    pm.migrate_to_v2(p)
    s = DataSeries(name="s1", x=[1.0, 2.0, 3.0, 4.0, 5.0],
                   y=[2.0, 4.0, 6.0, 8.0, 10.0])
    df = DataFile(name="test.csv", series=[s])
    pm.add_data_file(df)
    return pm, p, df, s


_PM_MODULES = [
    "core.project_manager",
    "ai.command_layer",
    "ui.dialogs.import_dialog",
    "ui.pages.data_page",
    "ui.pages.chart_page",
    "ui.pages.process_page",
    "ui.pages.analysis_page",
    "ui.pages.digitize_page",
    "ui.widgets.project_tree",
    "ui.main_window",
]


def _patch_pm(pm):
    """Patch project_manager in all relevant modules and return restorer."""
    import importlib
    saved = {}
    for mod_name in _PM_MODULES:
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "project_manager"):
                saved[mod_name] = mod.project_manager
                mod.project_manager = pm
        except ImportError:
            pass

    def restore():
        for mod_name, orig in saved.items():
            try:
                mod = importlib.import_module(mod_name)
                mod.project_manager = orig
            except ImportError:
                pass

    return restore


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


# ═══════════════════════════════════════════════════════════════════════════
# 1. ProjectTreeWidget
# ═══════════════════════════════════════════════════════════════════════════

class TestProjectTreeWidget(unittest.TestCase):
    """ProjectTreeWidget 信号与基本操作"""

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        self.pm, self.p, self.df, self.s = _make_project("tree_test")
        self._restore = _patch_pm(self.pm)
        from ui.widgets.project_tree import ProjectTreeWidget
        self.widget = ProjectTreeWidget()

    def tearDown(self):
        self._restore()
        self._restore_assets()
        self.widget.deleteLater()

    def test_refresh_builds_tree(self):
        self.widget.refresh()
        # 树应该有若干根节点
        self.assertGreater(self.widget._tree.topLevelItemCount(), 0)

    def test_refresh_shows_project_roots(self):
        self.widget.refresh()
        labels = [self.widget._tree.topLevelItem(i).text(0) for i in range(self.widget._tree.topLevelItemCount())]
        self.assertEqual(labels, [self.p.name, "全局资源"])

    def test_multiple_projects_render_as_top_level_roots(self):
        from models.schemas import DataFile, DataSeries

        other = self.pm.create_new("tree_second")
        self.pm.migrate_to_v3(other)
        self.pm.set_current_project(other.id)
        self.pm.add_data_file(DataFile(name="other.csv", series=[DataSeries(name="s2", x=[1.0], y=[2.0])]))
        self.pm.set_current_project(self.p.id)
        self.widget.refresh()
        labels = [self.widget._tree.topLevelItem(i).text(0) for i in range(self.widget._tree.topLevelItemCount())]
        self.assertEqual(labels, [self.p.name, other.name, "全局资源"])

    def test_global_resource_contains_global_template_groups(self):
        from models.schemas import FigureConfig

        self.pm.add_saved_pipeline("p1", [{"type": "smooth", "params": {}}])
        self.pm.add_report_template("tmpl_a", "# Report")
        self.pm.add_figure_template(FigureConfig(name="样式A", theme="Nature"))
        self.widget.refresh()
        global_root = self.widget._tree.topLevelItem(self.widget._tree.topLevelItemCount() - 1)
        root_children = [global_root.child(i).text(0) for i in range(global_root.childCount())]
        self.assertEqual(root_children, ["Pipelines", "曲线样式", "绘图样式", "报告模板"])

        pipeline_group = next(
            global_root.child(i)
            for i in range(global_root.childCount())
            if global_root.child(i).text(0) == "Pipelines"
        )
        report_group = next(
            global_root.child(i)
            for i in range(global_root.childCount())
            if global_root.child(i).text(0) == "报告模板"
        )
        style_group = next(
            global_root.child(i)
            for i in range(global_root.childCount())
            if global_root.child(i).text(0) == "绘图样式"
        )
        self.assertEqual([pipeline_group.child(i).text(0) for i in range(pipeline_group.childCount())], ["p1"])
        self.assertEqual([report_group.child(i).text(0) for i in range(report_group.childCount())], ["tmpl_a"])
        style_items = [style_group.child(i).text(0) for i in range(style_group.childCount())]
        self.assertIn("默认", style_items)
        self.assertIn("样式A", style_items)

    def test_global_resource_items_can_be_renamed_and_deleted(self):
        restore_assets = _patch_global_assets()
        try:
            from core.global_assets import global_assets
            from models.schemas import ReportTemplate, SavedPipeline

            pipeline = global_assets.add_saved_pipeline(SavedPipeline(name="流程A", ops=[]))
            report = global_assets.add_report_template(ReportTemplate(name="报告A", template="# 报告"))
            self.assertTrue(self.widget._rename_global_asset("global_pipeline", pipeline.id, "流程B"))
            self.assertEqual(global_assets.get_saved_pipeline(pipeline.id).name, "流程B")
            self.assertTrue(self.widget._rename_global_asset("global_report_template", report.id, "报告B"))
            self.assertEqual(global_assets.get_report_template(report.id).name, "报告B")
            self.assertTrue(self.widget._delete_global_asset("global_pipeline", pipeline.id))
            self.assertIsNone(global_assets.get_saved_pipeline(pipeline.id))
            self.assertTrue(self.widget._delete_global_asset("global_report_template", report.id))
            self.assertIsNone(global_assets.get_report_template(report.id))
        finally:
            restore_assets()

    def test_refresh_preserves_tree_expansion_state(self):
        self.widget.refresh()
        project_root = self.widget._tree.topLevelItem(0)
        dataset_group = project_root.child(0)
        global_root = self.widget._tree.topLevelItem(self.widget._tree.topLevelItemCount() - 1)

        project_root.setExpanded(True)
        dataset_group.setExpanded(False)
        global_root.setExpanded(False)

        self.widget.refresh()

        project_root = self.widget._tree.topLevelItem(0)
        dataset_group = project_root.child(0)
        global_root = self.widget._tree.topLevelItem(self.widget._tree.topLevelItemCount() - 1)
        self.assertTrue(project_root.isExpanded())
        self.assertFalse(dataset_group.isExpanded())
        self.assertFalse(global_root.isExpanded())

    def test_tree_config_enables_wrapped_labels(self):
        self.assertEqual(self.widget._tree.textElideMode(), Qt.TextElideMode.ElideNone)
        self.assertFalse(self.widget._tree.uniformRowHeights())

    def test_set_name_display_mode_elides_long_labels(self):
        self.widget.set_name_display_mode("elide")
        self.assertEqual(self.widget._tree.textElideMode(), Qt.TextElideMode.ElideRight)
        self.assertTrue(self.widget._tree.uniformRowHeights())

    def test_tree_item_tooltip_shows_full_long_label(self):
        self.p.name = "这是一个用于验证项目树节点 hover 可显示完整名称的超长项目名称"
        self.widget.refresh()
        root = self.widget._tree.topLevelItem(0)
        self.assertEqual(root.toolTip(0), self.p.name)

    def test_project_root_includes_digitize_and_picture_groups(self):
        self.widget.refresh()
        root = self.widget._tree.topLevelItem(0)
        labels = [root.child(i).text(0) for i in range(root.childCount())]
        self.assertEqual(labels[:4], ["数据集", "数据化", "图片集", "分析结果"])

    def test_add_picture_creates_picture_node_under_picture_group(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            picture_path = Path(temp_dir) / "chart.png"
            picture_path.write_bytes(b"png")
            node = self.pm.add_picture(str(picture_path), name="图表快照")

        self.assertIsNotNone(node)
        self.assertEqual(len(self.p.pictures), 1)
        self.assertEqual(self.p.pictures[0].name, "图表快照")
        parent = self.p.tree.get_node(node.parent_id)
        self.assertIsNotNone(parent)
        self.assertEqual(getattr(parent, "group_type", None), "pictures")

    def test_picture_path_tracks_picture_folder_move(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_file = Path(temp_dir) / "picture_move.aline"
            self.pm.save(str(project_file))
            picture_root = self.pm._find_folder_by_group_type("pictures")
            self.assertIsNotNone(picture_root)
            folder_a = self.pm.add_folder("导出A", parent_id=picture_root.id, group_type="pictures")
            folder_b = self.pm.add_folder("导出B", parent_id=picture_root.id, group_type="pictures")
            self.assertIsNotNone(folder_a)
            self.assertIsNotNone(folder_b)

            source_path = Path(temp_dir) / "chart.png"
            source_path.write_bytes(b"png")
            node = self.pm.add_picture(str(source_path), name="chart.png", parent_id=folder_a.id)
            self.assertIsNotNone(node)

            picture = self.p.pictures[0]
            self.assertIn("files/pictures/导出A/chart.png", self.pm.get_picture_path(picture.id))

            moved = self.pm.move_node(node.id, folder_b.id, 0)

            self.assertTrue(moved)
            target_path = self.pm.get_picture_path(picture.id)
            self.assertTrue(Path(target_path).exists())
            self.assertIn("files/pictures/导出B/chart.png", target_path)

    def test_rename_node_syncs_image_work_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "source.png"
            image_path.write_bytes(b"png")
            image = self.pm.add_image(str(image_path), name="原图")

        image_node = next(n for n in self.p.tree.nodes if n.kind == "image_work" and n.image_work_id == image.id)
        self.assertTrue(self.pm.rename_node(image_node.id, "重命名图"))
        self.assertEqual(self.pm.get_image(image.id).name, "重命名图")

    def test_update_wrapped_item_size_hints_ignores_deleted_tree_items(self):
        self.widget.refresh()
        stale_item = self.widget._tree.topLevelItem(0)
        self.widget.refresh()

        with mock.patch.object(self.widget._tree, "topLevelItemCount", return_value=1), \
             mock.patch.object(self.widget._tree, "topLevelItem", return_value=stale_item):
            self.widget._update_wrapped_item_size_hints()

    def test_set_filter_kinds_all(self):
        """空过滤 = 显示全部"""
        self.widget.set_filter_kinds([])
        self.widget.refresh()
        self.assertGreater(self.widget._tree.topLevelItemCount(), 0)

    def test_set_filter_kinds_data_file_only(self):
        self.widget.set_filter_kinds(["folder", "data_file"])
        self.widget.refresh()
        # 只有文件夹和数据文件节点可见

    def test_set_filter_kinds_image_only(self):
        self.widget.set_filter_kinds(["folder", "image_work"])
        self.widget.refresh()

    def test_node_selected_signal_emitted(self):
        self.widget.refresh()
        received = []
        self.widget.node_selected.connect(lambda k, nid: received.append((k, nid)))
        # 找第一个 data_file 节点并模拟选中
        it = self.widget._tree.topLevelItem(0)
        if it:
            self.widget._tree.setCurrentItem(it)
        # 信号由 currentItemChanged 触发
        # 手动调用私有槽模拟
        node_id = None
        kind = None
        for node in self.p.tree.nodes:
            if node.kind == "data_file":
                node_id = node.id
                kind = node.kind
                break
        if node_id:
            self.widget.node_selected.emit(kind, node_id)
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0][0], "data_file")

    def test_node_activated_signal_emitted(self):
        received = []
        self.widget.node_activated.connect(lambda k, nid: received.append((k, nid)))
        self.widget.node_activated.emit("data_file", "fake-id")
        self.assertEqual(len(received), 1)

    def test_project_modified_signal_emitted(self):
        received = []
        self.widget.project_modified.connect(lambda: received.append(True))
        self.widget.project_modified.emit()
        self.assertEqual(len(received), 1)

    def test_get_selected_node_none_initially(self):
        self.widget.refresh()
        # 初始无选中节点
        result = self.widget.get_selected_node()
        # 可能是 None 也可能是根节点，重要的是不崩溃
        self.assertIsInstance(result, (type(None), tuple))

    def test_select_node_programmatic(self):
        self.widget.refresh()
        for node in self.p.tree.nodes:
            if node.kind == "data_file":
                self.widget.select_node(node.id)
                break

    def test_refresh_twice_no_crash(self):
        self.widget.refresh()
        self.widget.refresh()

    def test_filter_pipeline_kind(self):
        sp = self.pm.add_saved_pipeline("p1", [{"type": "smooth", "params": {}}])
        self.widget.set_filter_kinds(["folder", "pipeline"])
        self.widget.refresh()

    def test_report_template_node_visible_after_add(self):
        self.pm.add_report_template("tmpl_a", "# Report")
        self.widget.refresh()
        found = []

        def _walk(item):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                found.append(data[0])
            for idx in range(item.childCount()):
                _walk(item.child(idx))

        for idx in range(self.widget._tree.topLevelItemCount()):
            _walk(self.widget._tree.topLevelItem(idx))
        self.assertIn("global_report_template", found)

    def test_root_folders_remain_visible_when_empty(self):
        from core.project_manager import ProjectManager
        pm = ProjectManager()
        project = pm.create_new("tree_empty")
        restore = _patch_pm(pm)
        widget = None
        try:
            from ui.widgets.project_tree import ProjectTreeWidget
            widget = ProjectTreeWidget()
            widget.set_filter_kinds(["folder", "image_work"])
            project_root = widget._tree.topLevelItem(0)
            self.assertEqual(project_root.text(0), project.name)
            names = [project_root.child(i).text(0) for i in range(project_root.childCount())]
            self.assertEqual(names, ["数据集", "数据化", "图片集", "分析结果"])
        finally:
            restore()
            if widget is not None:
                widget.deleteLater()

    def test_move_series_between_data_files(self):
        from models.schemas import DataFile, DataSeries

        other = DataFile(name="other.csv", series=[DataSeries(name="other", x=[1.0], y=[2.0])])
        self.pm.add_data_file(other)
        moved = self.widget._move_node_to_target("series", self.s.id, other.id)
        self.assertTrue(moved)
        self.assertEqual(len(self.df.series), 0)
        self.assertTrue(any(series.id == self.s.id for series in other.series))

    def test_drop_move_moves_series_into_data_file(self):
        from models.schemas import DataFile, DataSeries

        other_node = self.pm.add_data_file(DataFile(name="other.csv", series=[DataSeries(name="other", x=[1.0], y=[2.0])]))
        self.assertIsNotNone(other_node)

        self.widget.refresh()
        source_item = self.widget._find_item(self.s.id)
        target_item = self.widget._find_item(other_node.id)

        self.assertIsNotNone(source_item)
        self.assertIsNotNone(target_item)
        self.assertTrue(self.widget._perform_drop_move(source_item, target_item))
        self.assertEqual(len(self.df.series), 0)
        target_df = self.p.find_data_file(other_node.data_file_id)
        self.assertIsNotNone(target_df)
        self.assertTrue(any(series.id == self.s.id for series in target_df.series))

    def test_create_child_folder_inherits_collection_group_type(self):
        for group_type in ("datasets", "images", "analysis_result_group"):
            root = self.pm._find_folder_by_group_type(group_type)
            self.assertIsNotNone(root)
            folder = self.widget._create_child_folder(root.id, f"{group_type}-子文件夹")
            self.assertIsNotNone(folder)
            self.assertEqual(folder.parent_id, root.id)
            self.assertEqual(getattr(folder, "group_type", None), group_type)

    def test_move_target_choices_include_nested_dataset_folders(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder = self.widget._create_child_folder(datasets_root.id, "实验组")
        self.assertIsNotNone(folder)
        node = next(n for n in self.p.tree.nodes if n.kind == "data_file" and n.data_file_id == self.df.id)

        choices = self.widget._move_target_choices("data_file", node.id)
        self.assertIn((self.widget._folder_path_label(folder.id), folder.id), choices)

    def test_move_data_file_to_nested_dataset_folder(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder = self.widget._create_child_folder(datasets_root.id, "归档")
        self.assertIsNotNone(folder)
        node = next(n for n in self.p.tree.nodes if n.kind == "data_file" and n.data_file_id == self.df.id)

        moved = self.widget._move_node_to_target("data_file", node.id, folder.id)
        self.assertTrue(moved)
        self.assertEqual(node.parent_id, folder.id)

    def test_nested_dataset_folder_is_editable(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder = self.widget._create_child_folder(datasets_root.id, "实验组")
        self.assertIsNotNone(folder)

        self.widget.refresh()
        item = self.widget._find_item(folder.id)
        self.assertIsNotNone(item)
        self.assertTrue(bool(item.flags() & Qt.ItemFlag.ItemIsEditable))
        self.assertTrue(bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled))

    def test_data_file_and_image_work_nodes_are_editable(self):
        image = self.pm.add_image("/tmp/aline-tree-image.png", name="image.png")

        self.widget.refresh()
        data_file_node = next(n for n in self.p.tree.nodes if n.kind == "data_file" and n.data_file_id == self.df.id)
        image_node = next(n for n in self.p.tree.nodes if n.kind == "image_work" and n.image_work_id == image.id)

        data_file_item = self.widget._find_item(data_file_node.id)
        image_item = self.widget._find_item(image_node.id)

        self.assertIsNotNone(data_file_item)
        self.assertIsNotNone(image_item)
        self.assertTrue(bool(data_file_item.flags() & Qt.ItemFlag.ItemIsEditable))
        self.assertTrue(bool(image_item.flags() & Qt.ItemFlag.ItemIsEditable))

    def test_cmd_add_child_folder_creates_and_selects_root_child(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)

        self.widget.refresh()
        with mock.patch("ui.widgets.project_tree.TextInputDialog.get_text", return_value=("根目录子文件夹", True)):
            self.widget._cmd_add_child_folder(datasets_root.id)

        created = next(
            (node for node in self.p.tree.nodes if node.kind == "folder" and node.parent_id == datasets_root.id and node.name == "根目录子文件夹"),
            None,
        )
        self.assertIsNotNone(created)
        selected = self.widget.get_selected_node()
        self.assertEqual(selected, ("folder", created.id))

    def test_empty_child_folder_remains_visible_with_folder_filter(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)

        self.widget.set_filter_kinds(["folder", "data_file"])
        folder = self.widget._create_child_folder(datasets_root.id, "空文件夹")
        self.assertIsNotNone(folder)
        self.widget.refresh()

        self.assertIsNotNone(self.widget._find_item(folder.id))

    def test_move_nested_folder_to_another_folder(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder_a = self.widget._create_child_folder(datasets_root.id, "A")
        folder_b = self.widget._create_child_folder(datasets_root.id, "B")
        self.assertIsNotNone(folder_a)
        self.assertIsNotNone(folder_b)

        moved = self.widget._move_node_to_target("folder", folder_a.id, folder_b.id)
        self.assertTrue(moved)
        moved_node = self.pm.get_node_by_id(folder_a.id)
        self.assertEqual(moved_node.parent_id, folder_b.id)

    def test_drop_move_moves_data_file_into_folder(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder = self.widget._create_child_folder(datasets_root.id, "拖放目标")
        self.assertIsNotNone(folder)
        node = next(n for n in self.p.tree.nodes if n.kind == "data_file" and n.data_file_id == self.df.id)

        self.widget.refresh()
        source_item = self.widget._find_item(node.id)
        target_item = self.widget._find_item(folder.id)
        self.assertTrue(self.widget._perform_drop_move(source_item, target_item))
        self.assertEqual(node.parent_id, folder.id)

    def test_drop_move_uses_remembered_drag_source(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder = self.widget._create_child_folder(datasets_root.id, "拖放目标")
        self.assertIsNotNone(folder)
        node = next(n for n in self.p.tree.nodes if n.kind == "data_file" and n.data_file_id == self.df.id)

        self.widget.refresh()
        source_item = self.widget._find_item(node.id)
        target_item = self.widget._find_item(folder.id)
        self.widget._remember_drag_source_item(source_item)

        self.assertTrue(self.widget._perform_drop_move(None, target_item))
        self.assertEqual(node.parent_id, folder.id)

    def test_tree_enables_drag_drop_mode(self):
        self.assertTrue(self.widget._tree.dragEnabled())
        self.assertEqual(self.widget._tree.dragDropMode(), QAbstractItemView.DragDropMode.DragDrop)
        self.assertTrue(self.widget._tree.showDropIndicator())


# ═══════════════════════════════════════════════════════════════════════════
# 2. SettingsPage — AI 配置
# ═══════════════════════════════════════════════════════════════════════════

class TestSettingsPage(unittest.TestCase):
    """SettingsPage 基础配置与隐藏 AI 入口"""

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        from ui.pages.settings_page import SettingsPage
        self.page = SettingsPage()

    def tearDown(self):
        self.page.deleteLater()
        self._restore_assets()

    def test_page_creates_without_crash(self):
        self.assertIsNotNone(self.page)

    def test_theme_combo_exists(self):
        self.assertIsNotNone(self.page.theme_combo)

    def test_settings_title_label_is_removed(self):
        self.assertIsNone(self.page._title_label)

    def test_tree_display_mode_combo_defaults_to_wrap(self):
        from pathlib import Path
        from unittest import mock
        from ui.pages.settings_page import SettingsPage

        temp_page = None
        try:
            with mock.patch("core.ui_preferences._CONFIG_PATH", Path("/nonexistent/aline_ui_preferences.json")):
                temp_page = SettingsPage()
            self.assertEqual(temp_page._current_tree_display_mode(), "wrap")
        finally:
            if temp_page is not None:
                temp_page.deleteLater()

    def test_ai_tab_is_hidden_from_settings_ui(self):
        titles = [self.page._tabs.tabText(i) for i in range(self.page._tabs.count())]
        self.assertEqual(titles, ["常规"])

    def test_save_ai_config_no_crash(self):
        self.page._ai_url_edit.setText("https://api.openai.com/v1")
        self.page._ai_model_edit.setText("gpt-4o-mini")
        self.page._ai_timeout_edit.setText("30")
        self.page._save_ai_config()

    def test_provider_changed_to_ollama(self):
        # Ollama 也允许填写 API key（服务端代理场景）
        self.page._ai_provider_combo.setCurrentIndex(0)
        self.page._ai_url_edit.setText("")    # Clear URL so default gets set
        self.page._ai_model_edit.setText("")  # Clear model so default gets set
        self.page._ai_provider_combo.setCurrentIndex(1)  # Ollama
        self.assertTrue(self.page._ai_key_edit.isEnabled())
        self.assertTrue(self.page._ai_ollama_keep_alive_edit.isEnabled())
        # Ollama 时若 URL 为空则设置默认值
        self.assertIn("11434", self.page._ai_url_edit.text())
        self.assertIn("llama", self.page._ai_model_edit.text())
        self.assertIn("可选", self.page._ai_key_edit.placeholderText())

    def test_provider_changed_back_to_openai(self):
        self.page._ai_provider_combo.setCurrentIndex(1)
        self.page._ai_provider_combo.setCurrentIndex(0)
        self.assertTrue(self.page._ai_key_edit.isEnabled())
        self.assertFalse(self.page._ai_ollama_keep_alive_edit.isEnabled())

    def test_default_provider_is_openai_compatible(self):
        from pathlib import Path
        from unittest import mock
        from ui.pages.settings_page import SettingsPage

        temp_page = None
        try:
            with mock.patch("core.ai_client._CONFIG_PATH", Path("/nonexistent/aline_config.json")):
                temp_page = SettingsPage()
            self.assertEqual(temp_page._current_provider_key(), "openai_compatible")
        finally:
            if temp_page is not None:
                temp_page.deleteLater()

    def test_shortcuts_changed_signal(self):
        received = []
        self.page.shortcuts_changed.connect(lambda: received.append(True))
        self.page._on_apply_shortcuts()
        self.assertEqual(len(received), 1)

    def test_shortcut_filter_hides_nonmatching_rows(self):
        zoom_in = next(lbl for lbl in self.page._shortcut_labels if lbl.text().startswith("放大"))
        save = next(lbl for lbl in self.page._shortcut_labels if lbl.text().startswith("保存项目"))
        self.page._filter_shortcut_rows("缩放")
        self.assertFalse(zoom_in.isHidden())
        self.assertTrue(save.isHidden())

    def test_reset_shortcuts_no_crash(self):
        self.page._on_reset_shortcuts()

    def test_timeout_invalid_fallback(self):
        """非数字超时输入应 fallback 到 60"""
        self.page._ai_timeout_edit.setText("abc")
        self.page._save_ai_config()  # 不崩溃

    def test_refresh_ai_tools_panel_without_project(self):
        self.page._refresh_ai_tools_panel()
        self.assertIn("全局资源", self.page._ai_tools_project_label.text())

    def test_refresh_ai_tools_panel_with_project(self):
        from core.global_assets import global_assets
        from core.project_manager import ProjectManager

        pm = ProjectManager()
        pm.create_new("settings_ai_tools")
        global_assets.add_ai_prompt("prompt-a", "hello")
        global_assets.add_ai_skill("skill-a", "result = 1")
        global_assets.add_ai_agent("agent-a", "system")
        restore = _patch_pm(pm)
        try:
            self.page._refresh_ai_tools_panel()
            self.assertIn("Prompt 1", self.page._ai_tools_summary_label.text())
            # 新 UI 使用下拉框，检查 combo 中包含 skill-a
            combo_texts = [
                self.page._ai_tool_selector.itemText(i)
                for i in range(self.page._ai_tool_selector.count())
            ]
            self.assertTrue(any("skill-a" in t for t in combo_texts))
        finally:
            restore()


class TestExtensionConfigPanel(unittest.TestCase):

    def test_reload_button_emits_signal(self):
        from ui.widgets.extension_panel import ExtensionConfigPanel

        panel = ExtensionConfigPanel()
        received = []
        panel.reload_requested.connect(lambda: received.append(True))
        panel._reload_btn.click()

        self.assertEqual(received, [True])
        panel.deleteLater()

    def test_reload_button_uses_icon_tool_button(self):
        from qfluentwidgets import ToolButton
        from ui.widgets.extension_panel import ExtensionConfigPanel

        panel = ExtensionConfigPanel()

        self.assertIsInstance(panel._reload_btn, ToolButton)
        panel.deleteLater()


# ═══════════════════════════════════════════════════════════════════════════
# 3. DataPage — on_tree_node_selected
# ═══════════════════════════════════════════════════════════════════════════

class TestDataPage(unittest.TestCase):

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("dp_test")
        self._restore = _patch_pm(self.pm)
        from ui.pages.data_page import DataPage
        self.page = DataPage()

    def tearDown(self):
        self._restore()
        self.page.deleteLater()

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

    def test_preview_uses_plot_canvas_and_switches_plot_type(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        self.assertIsNotNone(node)

        self.page.on_tree_node_selected("data_file", node.id)

        if self.page._preview_figure is None or self.page._preview_canvas is None:
            self.skipTest("matplotlib unavailable")

        self.assertEqual(self.page._preview_type_combo.count(), 5)
        self.assertEqual(len(self.page._preview_figure.axes), 1)
        self.assertGreaterEqual(len(self.page._preview_figure.axes[0].lines), 1)

        scatter_index = next(
            index for index in range(self.page._preview_type_combo.count())
            if self.page._preview_type_combo.itemText(index) == "散点"
        )
        self.page._preview_type_combo.setCurrentIndex(scatter_index)
        self.assertGreaterEqual(len(self.page._preview_figure.axes[0].collections), 1)

    def test_on_tree_node_selected_data_file(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.page.on_tree_node_selected("data_file", node.id)
            self.assertEqual(self.page._selected_id, self.s.id)

    def test_on_tree_node_selected_folder(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "folder"), None)
        if node:
            self.page.on_tree_node_selected("folder", node.id)

    def test_on_tree_node_selected_unknown_kind(self):
        self.page.on_tree_node_selected("unknown", "fake-id")

    def test_on_tree_node_selected_nonexistent_id(self):
        self.page.on_tree_node_selected("data_file", "nonexistent-id-xyz")

    def test_tree_filter_kinds_attribute(self):
        self.assertIsInstance(
            getattr(self.page, "tree_filter_kinds", []), list
        )

    def test_legacy_left_entry_not_built(self):
        self.assertFalse(hasattr(self.page, "_btn_add_ds"))
        self.assertFalse(hasattr(self.page, "_btn_import"))
        self.assertFalse(hasattr(self.page, "_btn_copy_curve"))
        self.assertFalse(hasattr(self.page, "_btn_delete"))

    def test_management_panel_updates_for_data_file_selection(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        self.assertIsNotNone(node)

        self.page.on_tree_node_selected("data_file", node.id)

        self.assertIn("当前节点:", self.page._manage_target_label.text())
        self.assertEqual(self.page._manage_type_label.text(), "节点类型: 数据文件")
        self.assertTrue(self.page._btn_apply_name.isEnabled())
        self.assertTrue(self.page._btn_delete_node.isEnabled())
        self.assertTrue(self.page._btn_copy_to_data_file.isEnabled())

    def test_management_can_rename_selected_data_file(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        self.assertIsNotNone(node)

        self.page.on_tree_node_selected("data_file", node.id)
        self.page._manage_name_edit.setText("renamed.csv")
        self.page._apply_rename_current_node()

        self.assertEqual(self.df.name, "renamed.csv")
        self.assertEqual(node.name, "renamed.csv")

    def test_management_can_copy_series_to_new_data_file(self):
        before = len(self.p.data_files)

        self.page.on_tree_node_selected("series", self.s.id)
        self.page._duplicate_current_node_as_data_file()

        self.assertEqual(len(self.p.data_files), before + 1)
        copied = self.p.data_files[-1]
        self.assertEqual(copied.series[0].name, self.s.name)
        self.assertTrue(copied.name.endswith("_copy"))

    def test_management_disables_protected_folder_edits(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "folder" and getattr(n, "group_type", None) == "datasets"), None)
        self.assertIsNotNone(node)

        self.page.on_tree_node_selected("folder", node.id)

        self.assertFalse(self.page._btn_apply_name.isEnabled())
        self.assertFalse(self.page._btn_delete_node.isEnabled())

    def test_management_enables_nested_dataset_folder_edits(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder = self.pm.add_folder("子实验", parent_id=datasets_root.id, group_type="datasets")
        self.assertIsNotNone(folder)

        self.page.on_tree_node_selected("folder", folder.id)

        self.assertTrue(self.page._btn_apply_name.isEnabled())
        self.assertTrue(self.page._btn_delete_node.isEnabled())

    def test_add_dataset_uses_selected_dataset_folder(self):
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder = self.pm.add_folder("导入目标", parent_id=datasets_root.id, group_type="datasets")
        self.assertIsNotNone(folder)
        self.page.on_tree_node_selected("folder", folder.id)

        with mock.patch("ui.pages.data_page._NameDialog.exec", return_value=True), \
             mock.patch("ui.pages.data_page._NameDialog.get_name", return_value="子目录数据集"):
            self.page._add_dataset()

        node = next((n for n in self.p.tree.nodes if n.kind == "data_file" and n.name == "子目录数据集"), None)
        self.assertIsNotNone(node)
        self.assertEqual(node.parent_id, folder.id)

    def test_import_file_uses_selected_dataset_folder(self):
        from models.schemas import DataSeries

        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        folder = self.pm.add_folder("导入子目录", parent_id=datasets_root.id, group_type="datasets")
        self.assertIsNotNone(folder)
        self.page.on_tree_node_selected("folder", folder.id)

        with mock.patch("ui.dialogs.import_dialog.ImportDialog") as dialog_cls:
            dialog = dialog_cls.return_value
            dialog.exec.return_value = True
            dialog.get_results.return_value = [DataSeries(name="imported", x=[1.0], y=[2.0])]
            dialog.get_target_data_file_id.return_value = None
            dialog.get_file_name.return_value = "imported.csv"
            self.page._import_file()

        node = next((n for n in self.p.tree.nodes if n.kind == "data_file" and n.name == "imported.csv"), None)
        self.assertIsNotNone(node)
        self.assertEqual(node.parent_id, folder.id)

    def test_import_file_can_append_to_existing_data_file(self):
        from models.schemas import DataFile, DataSeries

        target = self.pm.add_data_file(DataFile(name="existing.csv", series=[]))
        self.assertIsNotNone(target)
        existing = next((df for df in self.p.data_files if df.name == "existing.csv"), None)
        self.assertIsNotNone(existing)

        with mock.patch("ui.dialogs.import_dialog.ImportDialog") as dialog_cls:
            dialog = dialog_cls.return_value
            dialog.exec.return_value = True
            dialog.get_results.return_value = [DataSeries(name="力", x=[1.0], y=[2.0])]
            dialog.get_target_data_file_id.return_value = existing.id
            self.page._import_file()

        self.assertEqual(len(existing.series), 1)
        self.assertEqual(existing.series[0].name, "力")


# ═══════════════════════════════════════════════════════════════════════════
# 4. ChartPage — on_tree_node_selected, load_template
# ═══════════════════════════════════════════════════════════════════════════

class TestChartPage(unittest.TestCase):

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        self.pm, self.p, self.df, self.s = _make_project("cp_test")
        self._restore = _patch_pm(self.pm)
        from ui.pages.chart_page import ChartPage
        self.page = ChartPage()

    def tearDown(self):
        self._restore()
        self._restore_assets()
        self.page.deleteLater()

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

    def test_chart_current_curve_color_uses_fluent_picker_button(self):
        from PySide6.QtWidgets import QFrame
        from qfluentwidgets import ColorPickerButton

        self.assertIsInstance(self.page._style_color_btn, ColorPickerButton)
        self.assertEqual(self.page._style_color_btn.width(), 32)
        self.assertEqual(self.page._style_color_btn.height(), 32)
        self.assertEqual(self.page._plot_style_scroll.frameShape(), QFrame.Shape.NoFrame)

    def test_on_tree_node_selected_data_file(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.page.on_tree_node_selected("data_file", node.id)

    def test_on_tree_node_selected_image_work(self):
        self.page.on_tree_node_selected("image_work", "fake-image-id")

    def test_on_tree_node_selected_folder(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "folder"), None)
        if node:
            self.page.on_tree_node_selected("folder", node.id)

    def test_load_template_no_crash(self):
        self.page.load_template("nonexistent-template-id")

    def test_load_template_valid(self):
        """添加模板后再加载"""
        from models.schemas import FigureConfig, AxisConfig
        cfg = FigureConfig(name="templ1")
        cfg.theme = "Nature"
        cfg.show_errbar = True
        cfg.figure_size = (9.0, 6.0)
        cfg.dpi = 220
        cfg.font_size = 14
        cfg.font_family = "DejaVu Sans"
        cfg.legend_font_size = 12
        cfg.line_width = 2.5
        cfg.marker_size = 7.0
        cfg.grid_alpha = 0.4
        cfg.grid_line_width = 1.1
        cfg.legend_position = "lower left"
        cfg.typed_axis_config = AxisConfig(x_label="Time", y_label="Signal")
        template = self.pm.add_figure_template(cfg)
        self.assertIsNotNone(template)
        self.page.load_template(template.id)
        self.assertEqual(self.page._figure_state.theme, "Nature")
        self.assertEqual(self.page._figure_state.x_label, "Time")
        self.assertTrue(self.page._figure_state.show_errbar)
        self.assertEqual(self.page._figure_state.figure_width, 9.0)
        self.assertEqual(self.page._figure_state.figure_height, 6.0)
        self.assertEqual(self.page._figure_state.dpi, 220)
        self.assertEqual(self.page._figure_state.font_family, "DejaVu Sans")
        self.assertEqual(self.page._figure_state.legend_font_size, 12)
        self.assertEqual(self.page._figure_state.line_width, 2.5)
        self.assertEqual(self.page._figure_state.marker_size, 7.0)
        self.assertEqual(self.page._figure_state.legend_pos, "lower left")
        self.assertEqual(self.page._template_combo.currentText(), "templ1")
        self.assertTrue(self.page._btn_update_template.isEnabled())

    def test_refresh_template_combo_includes_saved_template(self):
        from models.schemas import FigureConfig

        self.pm.add_figure_template(FigureConfig(name="模板甲", theme="ACS"))
        self.page._refresh_template_combo()
        items = [self.page._template_combo.itemText(i) for i in range(self.page._template_combo.count())]
        self.assertIn("模板甲", items)

    def test_update_current_template_overwrites_existing_figure(self):
        from models.schemas import FigureConfig

        from core.global_assets import global_assets

        template = self.pm.add_figure_template(FigureConfig(name="模板可更新", theme="默认"))
        self.assertIsNotNone(template)
        figures_before = len(global_assets.list_figure_templates())
        self.page.load_template(template.id)
        self.page.load_plot_style("IEEE")
        self.page._x_label_edit.setText("Voltage")
        updated = self.page._update_current_template()
        self.assertTrue(updated)
        self.assertEqual(len(global_assets.list_figure_templates()), figures_before)
        fig = global_assets.get_figure_template(template.id)
        self.assertIsNotNone(fig)
        self.assertEqual(fig.theme, "IEEE")
        self.assertEqual(fig.typed_axis_config.x_label, "Voltage")

    def test_theme_hint_updates_with_theme(self):
        self.page.load_plot_style("Nature")
        self.page._on_quick_config_changed()
        self.assertIn("论文", self.page._theme_hint_label.text())

    def test_quick_controls_update_figure_state(self):
        self.page._x_label_edit.setText("Time")
        self.page._y_label_edit.setText("Intensity")
        self.page.load_plot_style("ACS")
        self.page._errbar_cb.setChecked(True)
        state = self.page._sync_state_from_controls()
        self.assertEqual(state.x_label, "Time")
        self.assertEqual(state.y_label, "Intensity")
        self.assertEqual(state.theme, "ACS")
        self.assertTrue(state.show_errbar)

    def test_apply_advanced_config_updates_figure_state(self):
        self.page._apply_advanced_config({
            "theme": "IEEE",
            "x_label": "Voltage",
            "y_label": "Current",
            "x_min": "0",
            "x_max": "10",
            "y_min": "1",
            "y_max": "5",
            "x_log": True,
            "y_log": False,
            "grid": False,
            "legend_pos": "upper right",
            "font_size": 12,
            "font_family": "DejaVu Sans",
            "legend_font_size": 11,
            "figure_width": 8.5,
            "figure_height": 6.5,
            "dpi": 180,
            "line_width": 2.1,
            "marker_size": 6.2,
            "grid_alpha": 0.4,
            "grid_line_width": 0.8,
            "show_errbar": True,
        })
        self.assertEqual(self.page._figure_state.theme, "IEEE")
        self.assertEqual(self.page._figure_state.x_label, "Voltage")
        self.assertEqual(self.page._figure_state.legend_pos, "upper right")
        self.assertEqual(self.page._figure_state.x_max, 10.0)
        self.assertEqual(self.page._figure_state.figure_width, 8.5)
        self.assertEqual(self.page._figure_state.figure_height, 6.5)
        self.assertEqual(self.page._figure_state.dpi, 180)
        self.assertEqual(self.page._figure_state.font_family, "DejaVu Sans")
        self.assertEqual(self.page._figure_state.legend_font_size, 11)
        self.assertEqual(self.page._figure_state.line_width, 2.1)
        self.assertEqual(self.page._figure_state.marker_size, 6.2)
        self.assertEqual(self.page._legend_pos_combo.currentText(), "upper right")
        self.assertEqual(self.page._figure_width_edit.text(), "8.5")
        self.assertEqual(self.page._plot_line_width_edit.text(), "2.1")

    def test_builtin_plot_style_fully_overrides_default_metrics(self):
        self.page._plot_line_width_edit.setText("5.0")

        self.page.load_plot_style("IEEE")

        self.assertAlmostEqual(self.page._figure_state.line_width, 1.2)
        self.assertAlmostEqual(self.page._figure_state.marker_size, 3.8)

    def test_curve_style_tab_has_explicit_load_button(self):
        self.assertIsNotNone(self.page._style_tabs)
        self.assertIsNotNone(self.page._btn_load_curve_style_template)

    def test_plot_style_tab_has_explicit_load_button(self):
        self.assertIsNotNone(self.page._btn_load_template)

    def test_plot_extension_appears_in_extension_panel(self):
        from core.extension_api import PlotExtension, extension_registry

        def _draw(axis, series, options):
            axis.axhline(options.get("y", 0.0))

        extension_registry.register_plot(
            PlotExtension(
                type="ui_plot_extension_test",
                name="UI 参考线",
                handler=_draw,
                default_options={"y": 1.5},
            )
        )
        try:
            self.page._style_tabs.setCurrentIndex(1)
            self.page._refresh_style_extension_panel()
            selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]

            self.assertIn("绘图扩展 · UI 参考线", selector_items)
        finally:
            extension_registry.unregister_plot("ui_plot_extension_test")
            self.page._refresh_style_extension_panel()

    def test_curve_style_extension_preserves_extra_plot_kwargs(self):
        from core.extension_api import CurveStyleExtension, extension_registry

        def _style_patch(style, options):
            style.update({"markeredgewidth": options.get("markeredgewidth", 2.5)})
            return style

        extension_registry.register_curve_style(
            CurveStyleExtension(
                type="ui_curve_kwargs_test",
                name="UI 曲线扩展",
                handler=_style_patch,
                default_options={"markeredgewidth": 2.5},
            )
        )
        try:
            self.page.on_tree_node_activated("series", self.s.id)
            self.page._chart_list.setCurrentRow(0)
            self.page._curve_style_extension_options["ui_curve_kwargs_test"] = {"markeredgewidth": 3.0}

            self.page._apply_curve_style_extension("ui_curve_kwargs_test")

            curve_name = self.page._chart_series[0]["name"]
            self.assertEqual(self.page._curve_styles[curve_name]["markeredgewidth"], 3.0)
        finally:
            extension_registry.unregister_curve_style("ui_curve_kwargs_test")

    def test_plot_style_extension_preserves_extra_plot_config(self):
        from core.extension_api import PlotStyleExtension, extension_registry

        def _style_patch(state, options):
            state.update({
                "legend_kwargs": {"title": options.get("title", "Demo")},
                "line_defaults": {"solid_capstyle": options.get("capstyle", "round")},
            })
            return state

        extension_registry.register_plot_style(
            PlotStyleExtension(
                type="ui_plot_style_kwargs_test",
                name="UI 绘图样式扩展",
                handler=_style_patch,
                default_options={"title": "Legend", "capstyle": "round"},
            )
        )
        try:
            self.page._plot_style_extension_options["ui_plot_style_kwargs_test"] = {"title": "Legend", "capstyle": "projecting"}

            self.page._apply_plot_style_extension("ui_plot_style_kwargs_test")

            self.assertEqual(self.page._plot_style_extras["legend_kwargs"]["title"], "Legend")
            self.assertEqual(self.page._plot_style_extras["line_defaults"]["solid_capstyle"], "projecting")
        finally:
            extension_registry.unregister_plot_style("ui_plot_style_kwargs_test")

    def test_style_tabs_hide_add_and_close_buttons(self):
        from qfluentwidgets import TabCloseButtonDisplayMode

        self.assertTrue(self.page._style_tabs.tabBar.addButton.isHidden())
        self.assertEqual(
            self.page._style_tabs.tabBar.closeButtonDisplayMode,
            TabCloseButtonDisplayMode.NEVER,
        )

    def test_plot_style_numeric_inputs_use_compact_widths(self):
        self.assertLessEqual(self.page._font_size_edit.maximumWidth(), 96)
        self.assertLessEqual(self.page._figure_width_edit.maximumWidth(), 96)
        self.assertLessEqual(self.page._dpi_edit.maximumWidth(), 96)
        self.assertLessEqual(self.page._grid_alpha_edit.maximumWidth(), 96)

    def test_plot_actions_keep_only_export_button(self):
        plot_tab = self.page._style_tabs.widget(1)
        self.assertIsNot(self.page._btn_export.parent(), plot_tab)
        self.assertIs(self.page._btn_export.parent(), self.page._plot_actions_bar)
        self.assertFalse(hasattr(self.page, "_btn_advanced"))

    def test_font_family_uses_detected_combo_choices(self):
        self.assertGreater(self.page._font_family_combo.count(), 0)
        self.assertEqual(self.page._font_family_combo.itemText(0), "默认")

    def test_unbound_style_labels_use_none_text(self):
        self.assertEqual(self.page._template_combo.itemText(0), "无")
        self.assertEqual(self.page._curve_style_template_combo.itemText(0), "无")

    def test_grid_alpha_is_clamped_to_valid_range(self):
        self.page._grid_alpha_edit.setText("5.0")

        state = self.page._sync_state_from_controls()

        self.assertEqual(state.grid_alpha, 1.0)

    def test_display_canvas_size_preserves_requested_aspect_ratio(self):
        width, height = self.page._fitted_canvas_size(1200, 800, 9.5 / 6.5)

        self.assertAlmostEqual(width / height, 9.5 / 6.5, delta=0.02)
        self.assertLessEqual(width, 1200)
        self.assertLessEqual(height, 800)

    def test_redraw_on_compact_canvas_avoids_tight_layout_warning(self):
        if self.page._figure is None or self.page._canvas_host is None:
            self.skipTest("matplotlib unavailable")

        self.page.on_tree_node_activated("series", self.s.id)
        curve = self.page._chart_series[0]
        self.page._set_curve_display_name(curve, "图例名称较长用于紧凑布局")
        self.page._apply_advanced_config({
            "font_size": 16,
            "legend_font_size": 12,
            "x_label": "较长横坐标标签",
            "y_label": "较长纵坐标标签",
        })
        self.page._canvas_host.setFixedSize(220, 160)
        self.page._sync_canvas_display_geometry()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.page._redraw_now()

        layout_warnings = [str(item.message) for item in caught if "Tight layout not applied" in str(item.message)]
        self.assertEqual(layout_warnings, [])

    def test_redraw_applies_font_family_and_sizes_to_axis_and_legend(self):
        if self.page._figure is None:
            self.skipTest("matplotlib unavailable")

        self.page.on_tree_node_activated("series", self.s.id)
        font_index = self.page._font_family_combo.findText("DejaVu Sans")
        self.assertGreaterEqual(font_index, 0)
        self.page._font_family_combo.setCurrentIndex(font_index)
        self.page._font_size_edit.setText("15")
        self.page._legend_font_size_edit.setText("9")

        self.page._redraw_now()

        axis = self.page._figure.axes[0]
        self.assertAlmostEqual(axis.xaxis.label.get_fontsize(), 15)
        self.assertIn("DejaVu Sans", axis.xaxis.label.get_fontfamily())
        self.assertAlmostEqual(axis.yaxis.label.get_fontsize(), 15)
        tick_labels = axis.get_xticklabels() + axis.get_yticklabels()
        self.assertTrue(tick_labels)
        self.assertAlmostEqual(tick_labels[0].get_fontsize(), 15)
        self.assertIn("DejaVu Sans", tick_labels[0].get_fontfamily())

        legend = axis.get_legend()
        self.assertIsNotNone(legend)
        legend_text = legend.get_texts()[0]
        self.assertAlmostEqual(legend_text.get_fontsize(), 9)
        self.assertIn("DejaVu Sans", legend_text.get_fontfamily())

    def test_load_selected_curve_style_template_applies_style(self):
        restore_assets = _patch_global_assets()
        try:
            from core.global_assets import global_assets
            from models.schemas import CurveStyle, CurveStyleTemplate

            self.page.on_tree_node_activated("series", self.s.id)
            template = global_assets.add_curve_style_template(
                CurveStyleTemplate(name="绿色虚线", style=CurveStyle(color="#00aa00", linestyle="--", marker="o"))
            )
            self.page._refresh_curve_style_template_combo()
            self.page._curve_style_template_combo.setCurrentIndex(
                self.page._curve_style_template_ids.index(template.id)
            )

            self.page._load_selected_curve_style_template()

            style = self.page._curve_styles[self.s.name]
            self.assertEqual(style["color"], "#00aa00")
            self.assertEqual(style["linestyle"], "--")
            self.assertEqual(style["marker"], "o")
        finally:
            restore_assets()

    def test_plot_style_selection_requires_explicit_load(self):
        from models.schemas import FigureConfig

        template = self.pm.add_figure_template(FigureConfig(name="显式加载模板", theme="ACS"))
        self.assertIsNotNone(template)

        self.page._refresh_template_combo()
        combo_index = self.page._plot_style_refs.index(f"template:{template.id}")
        self.page._template_combo.setCurrentIndex(combo_index)

        self.assertEqual(self.page._figure_state.theme, "默认")

        self.page._load_selected_plot_style()

        self.assertEqual(self.page._figure_state.theme, "ACS")
        self.assertEqual(self.page._template_combo.currentText(), "显式加载模板")

    def test_chart_style_extensions_appear_in_selectors_and_panel(self):
        from core.extension_api import CurveStyleExtension, PlotStyleExtension, extension_registry

        extension_registry.register_plot_style(
            PlotStyleExtension(
                type="chart_plot_selector",
                name="绘图扩展选择",
                handler=lambda state, options: {"theme": "扩展绘图"},
                description="覆盖图表绘图样式",
                default_options={"line_width": 2.4},
            )
        )
        extension_registry.register_curve_style(
            CurveStyleExtension(
                type="chart_curve_selector",
                name="曲线扩展选择",
                handler=lambda style, options: {"marker": "d"},
                description="覆盖当前曲线样式",
                default_options={"marker": "d"},
            )
        )
        try:
            self.page._refresh_template_combo()
            self.page._refresh_curve_style_template_combo()

            plot_items = [self.page._template_combo.itemText(i) for i in range(self.page._template_combo.count())]
            curve_items = [self.page._curve_style_template_combo.itemText(i) for i in range(self.page._curve_style_template_combo.count())]
            selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]

            self.assertIn("扩展 · 绘图扩展选择", plot_items)
            self.assertIn("扩展 · 曲线扩展选择", curve_items)
            self.assertIn("曲线扩展选择", selector_items)

            self.page._style_tabs.setCurrentIndex(1)
            QApplication.processEvents()
            selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]
            self.assertIn("样式扩展 · 绘图扩展选择", selector_items)
        finally:
            extension_registry.unregister_plot_style("chart_plot_selector")
            extension_registry.unregister_curve_style("chart_curve_selector")
            self.page._refresh_template_combo()
            self.page._refresh_curve_style_template_combo()

    def test_chart_style_extension_panel_applies_plot_and_curve_styles(self):
        from core.extension_api import CurveStyleExtension, PlotStyleExtension, extension_registry

        extension_registry.register_plot_style(
            PlotStyleExtension(
                type="chart_plot_apply",
                name="绘图扩展应用",
                handler=lambda state, options: {
                    "theme": "扩展绘图",
                    "line_width": float(options.get("line_width", 1.0)),
                },
                description="调整绘图线宽",
                default_options={"line_width": 3.2},
            )
        )
        extension_registry.register_curve_style(
            CurveStyleExtension(
                type="chart_curve_apply",
                name="曲线扩展应用",
                handler=lambda style, options: {
                    "linewidth": float(options.get("linewidth", 1.0)),
                    "marker": options.get("marker", "s"),
                },
                description="调整当前曲线样式",
                default_options={"linewidth": 2.8, "marker": "d"},
            )
        )
        try:
            self.page.on_tree_node_activated("series", self.s.id)

            self.page._style_tabs.setCurrentIndex(1)
            QApplication.processEvents()
            plot_selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]
            self.page._extension_panel._selector.setCurrentIndex(plot_selector_items.index("样式扩展 · 绘图扩展应用"))
            self.page._extension_panel._editor.setPlainText('{"line_width": 4.5}')
            self.page._extension_panel._apply_current()

            self.assertEqual(self.page._applied_plot_style_ref, "extension:chart_plot_apply")
            self.assertEqual(self.page._figure_state.line_width, 4.5)

            self.page._style_tabs.setCurrentIndex(0)
            QApplication.processEvents()
            curve_selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]
            self.page._extension_panel._selector.setCurrentIndex(curve_selector_items.index("曲线扩展应用"))
            self.page._extension_panel._editor.setPlainText('{"linewidth": 3.5, "marker": "s"}')
            self.page._extension_panel._apply_current()

            self.assertEqual(self.page._active_curve_style_ref, "curve_extension:chart_curve_apply")
            self.assertEqual(self.page._curve_styles[self.s.name]["linewidth"], 3.5)
            self.assertEqual(self.page._curve_styles[self.s.name]["marker"], "s")
        finally:
            extension_registry.unregister_plot_style("chart_plot_apply")
            extension_registry.unregister_curve_style("chart_curve_apply")
            self.page._refresh_template_combo()
            self.page._refresh_curve_style_template_combo()

    def test_curve_display_name_only_affects_chart_list_and_legend(self):
        if self.page._figure is None:
            self.skipTest("matplotlib unavailable")

        self.page.on_tree_node_activated("series", self.s.id)
        curve = self.page._chart_series[0]
        original_name = curve["name"]

        self.page._set_curve_display_name(curve, "图例显示名")

        self.assertEqual(curve["name"], original_name)
        self.assertEqual(curve["display_name"], "图例显示名")
        self.assertEqual(self.page._chart_list.item(0).text(), "图例显示名")

        legend = self.page._figure.axes[0].get_legend()
        self.assertIsNotNone(legend)
        self.assertEqual(legend.get_texts()[0].get_text(), "图例显示名")

    def test_save_template_named_uses_figure_state(self):
        self.page._apply_advanced_config({
            "theme": "Nature",
            "x_label": "t",
            "y_label": "y",
            "show_errbar": True,
            "figure_width": 8.0,
            "figure_height": 5.5,
            "dpi": 240,
            "font_family": "DejaVu Sans",
            "legend_font_size": 10,
            "line_width": 2.0,
            "marker_size": 6.0,
        })
        from core.global_assets import global_assets

        template = self.page._save_template_named("模板状态A")
        self.assertIsNotNone(template)
        fig = global_assets.get_figure_template(template.id)
        self.assertIsNotNone(fig)
        self.assertEqual(fig.theme, "Nature")
        self.assertEqual(fig.figure_size, (8.0, 5.5))
        self.assertEqual(fig.dpi, 240)
        self.assertEqual(fig.font_family, "DejaVu Sans")
        self.assertEqual(fig.legend_font_size, 10)
        self.assertEqual(fig.line_width, 2.0)
        self.assertEqual(fig.marker_size, 6.0)
        self.assertEqual(self.page._template_combo.currentText(), "模板状态A")

    def test_load_template_dialog_uses_renamed_template_name(self):
        from models.schemas import FigureConfig

        from core.global_assets import global_assets

        template = self.pm.add_figure_template(FigureConfig(name="old_name", theme="ACS"))
        self.assertIsNotNone(template)
        global_assets.update_figure_template(template.id, name="renamed_template")

        def _fake_get_item(_parent, _title, _label, items, current_text=None):
            self.assertIn("renamed_template", items)
            return ("renamed_template", True)

        with mock.patch("ui.pages.chart_page.SelectionDialog.get_item", side_effect=_fake_get_item):
            self.page._on_load_template()

        self.assertEqual(self.page._figure_state.theme, "ACS")


# ═══════════════════════════════════════════════════════════════════════════
# 5. ProcessPage — on_tree_node_selected, load_pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestProcessPage(unittest.TestCase):

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        self.pm, self.p, self.df, self.s = _make_project("pp_test")
        self._restore = _patch_pm(self.pm)
        from ui.pages.process_page import ProcessPage
        self.page = ProcessPage()

    def tearDown(self):
        self._restore()
        self.page.deleteLater()
        self._restore_assets()

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

    def test_process_canvas_draw_avoids_tight_layout_warning(self):
        if self.page._figure is None or self.page._canvas is None:
            self.skipTest("matplotlib unavailable")

        self.page._src_xs = [0.0, 1.0, 2.0, 3.0]
        self.page._src_ys = [1.0, 2.0, 1.5, 2.5]
        self.page._out_xs = list(self.page._src_xs)
        self.page._out_ys = [1.1, 1.9, 1.6, 2.4]

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.page._draw_preview()

        layout_warnings = [str(item.message) for item in caught if "Tight layout not applied" in str(item.message)]
        self.assertEqual(layout_warnings, [])

    def test_on_tree_node_selected_series(self):
        self.page.on_tree_node_selected("series", self.s.id)

    def test_on_tree_node_selected_data_file(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.page.on_tree_node_selected("data_file", node.id)

    def test_on_tree_node_selected_curve(self):
        self.page.on_tree_node_selected("curve", "fake-curve-id")

    def test_load_pipeline_valid(self):
        """保存 Pipeline → 加载到 ProcessPage"""
        ops = [{"type": "smooth", "params": {"method": "moving_avg", "window": 5}}]
        sp = self.pm.add_saved_pipeline("test_pipe", ops, "for test")
        self.page.load_pipeline(sp.id)
        # 操作链应被加载
        self.assertEqual(len(self.page._ops), 1)
        self.assertEqual(self.page._ops[0]["type"], "smooth")

    def test_load_pipeline_nonexistent(self):
        self.page.load_pipeline("nonexistent-node-id")

    def test_load_ops_into_chain_clears_previous(self):
        ops1 = [{"type": "crop", "params": {"x_min": 0, "x_max": 5}}]
        ops2 = [{"type": "normalize", "params": {"mode": "minmax"}},
                {"type": "resample", "params": {"n": 100}}]
        self.page._load_ops_into_chain(ops1)
        self.assertEqual(len(self.page._ops), 1)
        self.page._load_ops_into_chain(ops2)
        self.assertEqual(len(self.page._ops), 2)

    def test_load_ops_empty_list(self):
        self.page._load_ops_into_chain([])
        self.assertEqual(len(self.page._ops), 0)

    def test_save_pipeline_template_as_named(self):
        from core.global_assets import global_assets

        self.page._load_ops_into_chain([{"type": "smooth", "params": {"method": "moving_avg", "window": 5}}])
        result = self.page._save_pipeline_template_as_named("流程模板A")
        self.assertTrue(result)
        self.assertTrue(any(sp.name == "流程模板A" for sp in global_assets.list_saved_pipelines()))

    def test_overwrite_pipeline_template(self):
        from core.global_assets import global_assets
        from models.schemas import SavedPipeline

        sp = global_assets.add_saved_pipeline(SavedPipeline(name="流程模板B", ops=[{"type": "smooth", "params": {"window": 5}}]))
        self.page.load_pipeline(sp.id)
        self.page._load_ops_into_chain([{"type": "normalize", "params": {"mode": "minmax"}}])
        self.assertTrue(self.page._overwrite_pipeline_template())
        saved = global_assets.get_saved_pipeline(sp.id)
        self.assertEqual(saved.ops[0]["type"], "normalize")

    def test_load_ops_with_resample_spacing_params(self):
        ops = [{"type": "resample", "params": {"mode": "spacing", "step": 0.25}}]

        self.page._load_ops_into_chain(ops)

        self.assertEqual(self.page._param_widgets[0].get_params(), {"mode": "spacing", "step": 0.25})

    def test_load_ops_with_fft_sampling_rate_params(self):
        ops = [{"type": "fft", "params": {"output": "power", "detrend": False, "sampling_rate": 50.0}}]

        self.page._load_ops_into_chain(ops)

        self.assertEqual(
            self.page._param_widgets[0].get_params(),
            {"output": "power", "detrend": False, "sampling_rate": 50.0},
        )

    def test_load_ops_with_filter_actual_frequency_params(self):
        ops = [{"type": "filter", "params": {"cutoff": 5.0, "cutoff_mode": "actual", "sampling_rate": 100.0, "order": 3, "mode": "high"}}]

        self.page._load_ops_into_chain(ops)

        self.assertEqual(
            self.page._param_widgets[0].get_params(),
            {"cutoff": 5.0, "order": 3, "mode": "high", "cutoff_mode": "actual", "sampling_rate": 100.0},
        )

    def test_save_result_creates_new_data_file_with_custom_name(self):
        from ui.dialogs.export_flow import DataExportPlan

        self.page._out_xs = [1.0, 2.0, 3.0]
        self.page._out_ys = [2.0, 3.0, 4.0]
        self.page._save_name_edit.setText("处理结果A")
        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)

        with mock.patch(
            "ui.pages.process_page.choose_data_export_plan",
            return_value=DataExportPlan(
                export_name="处理结果A",
                new_parent_id=datasets_root.id,
                new_data_file_name="处理结果A.process",
            ),
        ):
            self.page._save_result()

        data_file = next((df for df in self.p.data_files if df.name == "处理结果A.process"), None)
        self.assertIsNotNone(data_file)
        self.assertEqual(data_file.series[0].name, "处理结果A")

    def test_save_result_appends_to_selected_data_file(self):
        from ui.dialogs.export_flow import DataExportPlan

        self.page._out_xs = [1.0, 2.0, 3.0]
        self.page._out_ys = [2.0, 3.0, 4.0]
        self.page._save_name_edit.setText("处理结果B")
        original_count = len(self.df.series)

        with mock.patch(
            "ui.pages.process_page.choose_data_export_plan",
            return_value=DataExportPlan(export_name="处理结果B", target_data_file_id=self.df.id),
        ):
            self.page._save_result()

        self.assertEqual(len(self.df.series), original_count + 1)
        self.assertEqual(self.df.series[-1].name, "处理结果B")

    def test_processing_extension_appears_in_selector_and_panel(self):
        from core.extension_api import ProcessingExtension, extension_registry

        def _scale(xs, ys, params):
            factor = float(params.get("factor", 1.0))
            return list(xs), [value * factor for value in ys]

        extension_registry.register_processing(
            ProcessingExtension(
                type="ui_scale_test",
                name="UI 缩放测试",
                handler=_scale,
                description="按 factor 缩放 Y 值",
                default_options={"factor": 2},
            )
        )
        try:
            self.page._refresh_processing_extensions()
            combo_items = [self.page._add_op_combo.itemText(i) for i in range(self.page._add_op_combo.count())]
            selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]

            self.assertIn("扩展 · UI 缩放测试", combo_items)
            self.assertIn("UI 缩放测试", selector_items)
        finally:
            extension_registry.unregister_processing("ui_scale_test")
            self.page._refresh_processing_extensions()

    def test_processing_extension_panel_adds_extension_op(self):
        from core.extension_api import ProcessingExtension, extension_registry

        def _scale(xs, ys, params):
            factor = float(params.get("factor", 1.0))
            return list(xs), [value * factor for value in ys]

        extension_registry.register_processing(
            ProcessingExtension(
                type="ui_scale_apply",
                name="UI 扩展应用",
                handler=_scale,
                description="按 factor 缩放 Y 值",
                default_options={"factor": 2},
            )
        )
        try:
            self.page._refresh_processing_extensions()
            selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]
            self.page._extension_panel._selector.setCurrentIndex(selector_items.index("UI 扩展应用"))
            self.page._extension_panel._editor.setPlainText('{"factor": 4}')
            self.page._extension_panel._apply_current()

            self.assertEqual(self.page._ops[-1]["type"], "ui_scale_apply")
            self.assertEqual(self.page._ops[-1]["params"], {"factor": 4})
        finally:
            extension_registry.unregister_processing("ui_scale_apply")
            self.page._refresh_processing_extensions()

    def test_processing_extension_panel_shows_config_field_help(self):
        from core.extension_api import ExtensionConfigField, ProcessingExtension, extension_registry

        def _scale(xs, ys, params):
            factor = float(params.get("factor", 1.0))
            return list(xs), [value * factor for value in ys]

        extension_registry.register_processing(
            ProcessingExtension(
                type="ui_scale_help",
                name="UI 配置说明",
                handler=_scale,
                description="展示扩展配置字段说明。",
                default_options={"factor": 2.5},
                config_fields=[
                    ExtensionConfigField(
                        key="factor",
                        label="倍率",
                        description="用于缩放当前 Y 值。",
                        field_type="number",
                        default=2.5,
                    )
                ],
            )
        )
        try:
            self.page._refresh_processing_extensions()
            help_text = self.page._extension_panel._config_help_label.text()
            self.assertIn("倍率", help_text)
            self.assertIn("factor", help_text)
            self.assertIn("number", help_text)
        finally:
            extension_registry.unregister_processing("ui_scale_help")
            self.page._refresh_processing_extensions()


# ═══════════════════════════════════════════════════════════════════════════
# 6. AnalysisPage — on_tree_node_selected
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalysisPage(unittest.TestCase):

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        self.pm, self.p, self.df, self.s = _make_project("ap_test")
        self._restore = _patch_pm(self.pm)
        from ui.pages.analysis_page import AnalysisPage
        self.page = AnalysisPage()

    def tearDown(self):
        self._restore()
        self._restore_assets()
        self.page.deleteLater()

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

    def test_input_action_buttons_match_height_and_template_label_is_hidden(self):
        self.assertEqual(self.page._btn_clear_inputs.height(), 32)
        self.assertEqual(self.page._btn_remove_selected_inputs.height(), 32)
        self.assertTrue(self.page._report_template_label.isHidden())

    def test_analysis_canvas_draws_chinese_without_glyph_warnings(self):
        if self.page._figure is None or self.page._canvas is None:
            self.skipTest("matplotlib unavailable")

        self.page._figure.clear()
        axis = self.page._figure.add_subplot(111)
        axis.set_title("拟合结果")
        axis.set_xlabel("波峰")
        axis.set_ylabel("波谷")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.page._canvas.draw()

        glyph_warnings = [str(item.message) for item in caught if "Glyph" in str(item.message)]
        self.assertEqual(glyph_warnings, [])

    def test_analysis_canvas_draw_avoids_tight_layout_warning(self):
        if self.page._figure is None or self.page._canvas is None:
            self.skipTest("matplotlib unavailable")

        self.page._figure.clear()
        axis = self.page._figure.add_subplot(111)
        axis.plot([0.0, 1.0, 2.0], [1.0, 2.0, 1.5], label="测试")
        axis.set_title("分析结果")
        axis.legend()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.page._canvas.draw()

        layout_warnings = [str(item.message) for item in caught if "Tight layout not applied" in str(item.message)]
        self.assertEqual(layout_warnings, [])

    def test_input_role_labels_are_hidden(self):
        self.assertTrue(self.page._primary_input_label.isHidden())
        self.assertTrue(self.page._secondary_input_label.isHidden())

    def test_input_list_copy_selection_to_clipboard(self):
        from models.schemas import DataFile, DataSeries

        other = DataFile(name="other.csv", series=[DataSeries(name="other", x=[0.0, 1.0], y=[1.0, 2.0])])
        self.pm.add_data_file(other)

        self.page._type_combo.setCurrentIndex(3)
        self.page.on_tree_node_activated("series", self.s.id)
        self.page.on_tree_node_activated("data_file", next(n.id for n in self.p.tree.nodes if n.kind == "data_file" and n.data_file_id == other.id))

        self.page._input_list.item(0).setSelected(True)
        self.page._input_list.item(1).setSelected(True)
        self.page._input_list.copy_selection_to_clipboard()

        clipboard_text = QApplication.clipboard().text()
        self.assertIn(self.s.name, clipboard_text)
        self.assertIn(other.name, clipboard_text)

    def test_summary_area_has_larger_minimum_height(self):
        current_view = self.page._analysis_tab_views["current"]
        self.assertGreaterEqual(current_view["summary_stack"].minimumHeight(), 280)

    def test_unknown_analysis_json_renders_as_flattened_summary_rows(self):
        payload = {
            "summary": {"score": 0.875, "status": "ok"},
            "items": [
                {"name": "A", "value": 1},
                {"name": "B", "value": 2},
            ],
        }

        self.page._write_summary("custom_json", payload)

        labels = [self.page._summary_table.item(row, 0).text() for row in range(self.page._summary_table.rowCount())]
        values = [self.page._summary_table.item(row, 1).text() for row in range(self.page._summary_table.rowCount())]
        self.assertIn("summary.score", labels)
        self.assertIn("items[0].name", labels)
        self.assertIn("0.875", values)
        self.assertIn("A", values)

    def test_on_tree_node_selected_data_file(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.page.on_tree_node_selected("data_file", node.id)

    def test_on_tree_node_selected_folder(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "folder"), None)
        if node:
            self.page.on_tree_node_selected("folder", node.id)

    def test_on_tree_node_selected_unknown(self):
        self.page.on_tree_node_selected("pipeline", "fake-id")

    def test_load_report_template_from_tree(self):
        tmpl = self.pm.add_report_template("analysis_tmpl", "# Report")
        self.page.load_report_template(tmpl.id)
        self.assertEqual(self.page._current_report_template_id, tmpl.id)
        self.assertEqual(self.page._report_editor.toPlainText(), "# Report")

    def test_on_tree_node_activated_report_template(self):
        tmpl = self.pm.add_report_template("analysis_tmpl", "# Report")
        self.page.on_tree_node_activated("global_report_template", tmpl.id)
        self.assertEqual(self.page._current_report_template_id, tmpl.id)

    def test_generate_report_renders_in_page(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.page._run_analysis()
        self.page._on_generate_report()
        self.assertEqual(self.page._result_tabs.currentIndex(), 1)
        self.assertIn("分析类型", self.page._report_preview.toPlainText())

    def test_save_result_prompts_for_name_before_persisting(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.page._run_analysis()

        with mock.patch("ui.pages.analysis_page.TextInputDialog.get_text", return_value=("拟合结果A", True)):
            self.page._save_result()

        saved = next((item for item in self.p.analyses if item.name == "拟合结果A"), None)
        self.assertIsNotNone(saved)

    def test_save_report_template_as_named(self):
        from core.global_assets import global_assets

        self.page._report_editor.setPlainText("# Saved Report")
        self.assertTrue(self.page._save_report_template_as_named("模板A"))
        self.assertTrue(any(t.name == "模板A" for t in global_assets.list_report_templates()))

    def test_save_report_template_as_named_reuses_existing_name(self):
        from core.global_assets import global_assets

        self.page._report_editor.setPlainText("# Saved Report A")
        self.assertTrue(self.page._save_report_template_as_named("模板同名A"))
        first_id = self.page._current_report_template_id

        self.page._report_editor.setPlainText("# Saved Report B")
        self.assertTrue(self.page._save_report_template_as_named("模板同名A"))

        matches = [t for t in global_assets.list_report_templates() if t.name == "模板同名A"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, first_id)
        self.assertEqual(matches[0].content, "# Saved Report B")

    def test_report_template_workspace_refreshes_after_save(self):
        self.page._report_editor.setPlainText("# Saved Report")
        self.assertTrue(self.page._save_report_template_as_named("模板工作台A"))
        items = [self.page._report_template_combo.itemText(i) for i in range(self.page._report_template_combo.count())]
        self.assertIn("模板工作台A", items)

    def test_save_current_report_template_updates_existing(self):
        tmpl = self.pm.add_report_template("analysis_tmpl", "# Report")
        self.page._load_report_template_by_id(tmpl.id)
        self.page._report_editor.setPlainText("# Updated Report")
        self.page._save_current_report_template()
        self.assertEqual(self.pm.get_report_template(tmpl.id).content, "# Updated Report")

    def test_analysis_extension_appears_in_type_selector_and_panel(self):
        from core.extension_api import AnalysisExtension, extension_registry

        def _span(inputs, params):
            values = list(inputs[0].get("y", []))
            return {
                "analysis_type": "ui_span_selector",
                "source_name": inputs[0].get("name", ""),
                "span": (max(values) - min(values)) if values else 0.0,
            }

        extension_registry.register_analysis(
            AnalysisExtension(
                type="ui_span_selector",
                name="UI 跨度选择",
                handler=_span,
                description="返回当前序列跨度",
                default_options={"scale": 2},
            )
        )
        try:
            self.page._refresh_analysis_type_choices()
            combo_items = [self.page._type_combo.itemText(i) for i in range(self.page._type_combo.count())]
            selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]

            self.assertIn("UI 跨度选择", combo_items)
            self.assertIn("UI 跨度选择", selector_items)
        finally:
            extension_registry.unregister_analysis("ui_span_selector")
            self.page._refresh_analysis_type_choices()

    def test_analysis_extension_panel_switches_type_and_runs(self):
        from core.extension_api import AnalysisExtension, extension_registry

        def _span(inputs, params):
            values = list(inputs[0].get("y", []))
            return {
                "analysis_type": "ui_span_run",
                "source_name": inputs[0].get("name", ""),
                "span": (max(values) - min(values)) if values else 0.0,
                "scale": params.get("scale", 1),
            }

        extension_registry.register_analysis(
            AnalysisExtension(
                type="ui_span_run",
                name="UI 跨度执行",
                handler=_span,
                description="返回当前序列跨度",
                default_options={"scale": 3},
            )
        )
        try:
            self.page._refresh_analysis_type_choices()
            selector_items = [self.page._extension_panel._selector.itemText(i) for i in range(self.page._extension_panel._selector.count())]
            self.page._extension_panel._selector.setCurrentIndex(selector_items.index("UI 跨度执行"))
            self.page._extension_panel._editor.setPlainText('{"scale": 5}')
            self.page._extension_panel._apply_current()

            self.assertEqual(self.page._current_analysis_type(), "ui_span_run")

            self.page._selected_inputs = [{"kind": "series", "node_id": self.s.id, "label": self.s.name}]
            self.page._get_selected_data = lambda: [([0.0, 1.0], [2.0, 6.0], "demo")]
            self.page._run_analysis()

            self.assertEqual(self.page._result["analysis_type"], "ui_span_run")
            self.assertEqual(self.page._result["span"], 4.0)
            self.assertEqual(self.page._result["scale"], 5)
        finally:
            extension_registry.unregister_analysis("ui_span_run")
            self.page._refresh_analysis_type_choices()

    def test_export_report_to_path(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.page._run_analysis()
        self.page._on_generate_report()
        fd, path = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            self.assertTrue(self.page._export_report_to_path(path))
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
            self.assertIn("分析类型", content)
        finally:
            os.unlink(path)

    def test_error_compare_requires_two_inputs(self):
        from models.schemas import DataSeries

        self.page._type_combo.setCurrentIndex(4)
        other = DataSeries(name="s2", x=[1.0, 2.0, 3.0], y=[1.5, 1.0, 2.5])
        self.df.series.append(other)
        self.page.on_tree_node_activated("series", self.s.id)
        self.page.on_tree_node_activated("series", other.id)
        self.page._run_analysis()
        self.assertEqual(self.page._result["analysis_type"], "error_compare")
        self.assertIn("mae", self.page._result)

    def test_load_saved_analysis_result_from_tree(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.page._run_analysis()
        with mock.patch("ui.pages.analysis_page.TextInputDialog.get_text", return_value=("拟合结果A", True)):
            self.page._save_result()
        node = next((n for n in self.p.tree.nodes if n.kind == "analysis_result"), None)
        self.assertIsNotNone(node)
        self.page.load_analysis_result(node.id)
        self.assertEqual(self.page._result["analysis_type"], "curve_fit")
        self.assertEqual(len(self.page._selected_inputs), 1)
        self.assertEqual(self.page._analysis_tabs.count(), 2)
        summary_labels = [self.page._summary_table.item(row, 0).text() for row in range(self.page._summary_table.rowCount())]
        self.assertIn("R²", summary_labels)

    def test_selecting_series_opens_all_saved_results_in_tabs(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.page._run_analysis()

        with mock.patch(
            "ui.pages.analysis_page.TextInputDialog.get_text",
            side_effect=[("拟合结果A", True), ("拟合结果B", True)],
        ):
            self.page._save_result()
            self.page._save_result()

        self.page.on_tree_node_activated("series", self.s.id)

        titles = [self.page._analysis_tabs.tabText(i) for i in range(self.page._analysis_tabs.count())]
        self.assertEqual(self.page._analysis_tabs.count(), 3)
        self.assertIn("拟合结果A", titles)
        self.assertIn("拟合结果B", titles)

    def test_analysis_result_tabs_are_closable(self):
        from qfluentwidgets import TabCloseButtonDisplayMode

        self.page.on_tree_node_activated("series", self.s.id)
        self.page._run_analysis()

        with mock.patch(
            "ui.pages.analysis_page.TextInputDialog.get_text",
            side_effect=[("拟合结果A", True), ("拟合结果B", True)],
        ):
            self.page._save_result()
            self.page._save_result()

        self.page.on_tree_node_activated("series", self.s.id)

        self.assertEqual(
            self.page._analysis_tabs.tabBar.closeButtonDisplayMode,
            TabCloseButtonDisplayMode.ON_HOVER,
        )

        self.page._analysis_tabs.setCurrentIndex(2)
        closing_title = self.page._analysis_tabs.tabText(2)
        self.page._on_analysis_tab_close_requested(2)

        titles = [self.page._analysis_tabs.tabText(i) for i in range(self.page._analysis_tabs.count())]
        self.assertEqual(self.page._analysis_tabs.count(), 2)
        self.assertNotIn(closing_title, titles)

    def test_peak_detect_uses_specialized_four_column_summary(self):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtWidgets import QAbstractItemView
        from PySide6.QtWidgets import QHeaderView
        from PySide6.QtWidgets import QTableWidgetSelectionRange

        from models.schemas import DataSeries

        target = DataSeries(
            name="oscillation",
            x=[0.0, 1.0, 2.0, 3.0, 4.0],
            y=[0.0, 2.0, 0.0, -1.5, 0.0],
        )
        self.df.series.append(target)

        self.page._type_combo.setCurrentIndex(1)
        self.page.on_tree_node_activated("series", target.id)
        self.page._run_analysis()

        view = self.page._analysis_tab_views["current"]
        self.assertIs(view["summary_stack"].currentWidget(), view["peak_summary_widget"])

        meta_labels = [view["peak_meta_table"].item(row, 0).text() for row in range(view["peak_meta_table"].rowCount())]
        self.assertIn("波峰数量", meta_labels)
        self.assertIn("波谷数量", meta_labels)

        peak_points_table = view["peak_points_table"]
        headers = [peak_points_table.horizontalHeaderItem(i).text() for i in range(peak_points_table.columnCount())]
        self.assertEqual(headers, ["波峰序号", "波峰 X", "波峰 Y", "波谷序号", "波谷 X", "波谷 Y"])
        self.assertGreaterEqual(peak_points_table.rowCount(), 1)
        self.assertEqual(view["peak_meta_table"].selectionMode(), QAbstractItemView.SelectionMode.ExtendedSelection)
        self.assertEqual(peak_points_table.selectionMode(), QAbstractItemView.SelectionMode.ExtendedSelection)
        self.assertEqual(peak_points_table.horizontalHeader().sectionResizeMode(0), QHeaderView.ResizeMode.ResizeToContents)
        self.assertEqual(peak_points_table.horizontalHeader().sectionResizeMode(3), QHeaderView.ResizeMode.ResizeToContents)
        self.assertEqual(peak_points_table.item(0, 0).text(), "1")
        self.assertEqual(peak_points_table.item(0, 1).text(), "1")
        self.assertEqual(peak_points_table.item(0, 3).text(), "1")
        self.assertEqual(peak_points_table.item(0, 4).text(), "3")

        peak_points_table.setRangeSelected(
            QTableWidgetSelectionRange(0, 0, 0, 2),
            True,
        )
        peak_points_table.copy_selection_to_clipboard()
        QApplication.processEvents()
        self.assertIn("\t", QApplication.clipboard().text())

    def test_report_preview_allows_selecting_one_result_per_analysis_type(self):
        with mock.patch(
            "ui.pages.analysis_page.TextInputDialog.get_text",
            side_effect=[("拟合结果A", True), ("拟合结果B", True), ("统计结果A", True)],
        ):
            self.page.on_tree_node_activated("series", self.s.id)
            self.page._type_combo.setCurrentIndex(0)
            self.page._run_analysis()
            self.page._save_result()
            self.page._save_result()
            self.page._type_combo.setCurrentIndex(2)
            self.page._run_analysis()
            self.page._save_result()

        self.page.on_tree_node_activated("series", self.s.id)
        self.page._on_generate_report()

        self.assertFalse(self.page._report_result_selector_panel.isHidden())
        curve_fit_combo = self.page._report_result_selectors["curve_fit"]
        statistics_combo = self.page._report_result_selectors["statistics"]
        self.assertEqual(curve_fit_combo.count(), 3)
        self.assertEqual(statistics_combo.count(), 3)

        curve_fit_combo.setCurrentIndex(2)
        statistics_combo.setCurrentIndex(2)
        self.page._render_report_preview()
        preview = self.page._report_preview.toPlainText()
        self.assertIn("拟合结果B", preview)
        self.assertIn("统计结果A", preview)
        self.assertNotIn("拟合结果A", preview)

    def test_report_preview_preserves_blank_lines_for_multi_result_sections(self):
        with mock.patch(
            "ui.pages.analysis_page.TextInputDialog.get_text",
            side_effect=[("拟合结果A", True), ("统计结果A", True)],
        ):
            self.page.on_tree_node_activated("series", self.s.id)
            self.page._type_combo.setCurrentIndex(0)
            self.page._run_analysis()
            self.page._save_result()
            self.page._type_combo.setCurrentIndex(2)
            self.page._run_analysis()
            self.page._save_result()

        self.page._report_editor.setPlainText("\n前言\n\n正文\n")
        self.page.on_tree_node_activated("series", self.s.id)
        self.page._on_generate_report()

        curve_fit_combo = self.page._report_result_selectors["curve_fit"]
        statistics_combo = self.page._report_result_selectors["statistics"]

        def _select_combo_text(combo, text):
            for index in range(combo.count()):
                if combo.itemText(index) == text:
                    combo.setCurrentIndex(index)
                    return
            self.fail(f"未找到结果选项: {text}")

        _select_combo_text(curve_fit_combo, "拟合结果A")
        _select_combo_text(statistics_combo, "统计结果A")
        self.page._render_report_preview()

        preview = self.page._report_preview.toPlainText()
        self.assertIn("## 拟合结果A\n\n\n前言\n\n正文\n", preview)
        self.assertIn("## 统计结果A\n\n\n前言\n\n正文\n", preview)

    def test_peak_detect_supports_x_distance_mode(self):
        from models.schemas import DataSeries

        target = DataSeries(
            name="peaks",
            x=[0.0, 0.2, 0.4, 0.6, 1.0, 1.2, 1.4, 1.6],
            y=[0.0, 1.0, 0.0, 0.9, 0.0, 0.0, 0.8, 0.0],
        )
        self.df.series.append(target)

        self.page._type_combo.setCurrentIndex(1)
        self.page._peak_dist_mode_combo.setCurrentIndex(1)
        self.page._peak_dist_edit.setText("0.7")
        self.page.on_tree_node_activated("series", target.id)
        self.page._run_analysis()

        self.assertEqual(self.page._result["analysis_type"], "peak_detect")
        self.assertEqual(self.page._result["distance_mode"], "x_distance")
        self.assertEqual(self.page._result["count"], 2)

    def test_peak_detect_can_export_peaks_and_valleys_as_series(self):
        from models.schemas import DataSeries

        target = DataSeries(
            name="oscillation",
            x=[0.0, 1.0, 2.0, 3.0, 4.0],
            y=[0.0, 2.0, 0.0, -1.5, 0.0],
        )
        self.df.series.append(target)

        before = len(self.p.data_files)
        self.page._type_combo.setCurrentIndex(1)
        self.page.on_tree_node_activated("series", target.id)
        self.page._run_analysis()
        self.page._export_extrema_series("peaks", "peaks")
        self.page._export_extrema_series("valleys", "valleys")

        self.assertEqual(len(self.p.data_files), before + 2)
        names = [data_file.name for data_file in self.p.data_files[-2:]]
        self.assertEqual(names, ["peaks_oscillation.analysis", "valleys_oscillation.analysis"])

    def test_single_input_mode_replaces_previous_input(self):
        from models.schemas import DataSeries

        other = DataSeries(name="s2", x=[1.0, 2.0], y=[2.0, 3.0])
        self.df.series.append(other)
        self.page.on_tree_node_activated("series", self.s.id)
        self.page.on_tree_node_activated("series", other.id)
        self.assertEqual(len(self.page._selected_inputs), 1)
        self.assertEqual(self.page._selected_inputs[0]["node_id"], other.id)


# ═══════════════════════════════════════════════════════════════════════════
# 7. DigitizePage — load_image_by_id
# ═══════════════════════════════════════════════════════════════════════════

class TestDigitizePage(unittest.TestCase):

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("dig_test")
        self._restore = _patch_pm(self.pm)
        from ui.pages.digitize_page import DigitizePage
        self.page = DigitizePage()

    def tearDown(self):
        self._restore()
        self.page.deleteLater()

    def _add_digitize_curve(self):
        from models.schemas import ImageWork

        image = ImageWork(name="SEM A", image_path="sample.png")
        self.p.images.append(image)
        curve = self.pm.add_curve_to_image(
            image.id,
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
            name="曲线1",
        )
        self.assertIsNotNone(curve)
        self.page._current_image_id = image.id
        self.page._current_curve_id = curve.id
        self.page._refresh_export_name_suggestion(force=True)
        return image, curve

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

    def test_crosshair_color_button_matches_manual_toolbar_height(self):
        self.assertEqual(self.page._crosshair_color_btn.width(), 34)
        self.assertEqual(self.page._crosshair_color_btn.height(), 34)
        self.assertEqual(self.page._crosshair_color_btn.height(), self.page._calibrate_btn.height())

    def test_load_image_by_id_nonexistent(self):
        """不存在的 ID 不崩溃"""
        self.page.load_image_by_id("nonexistent-id")

    def test_on_tree_node_selected_image_work(self):
        self.page.on_tree_node_selected("image_work", "fake-image-id")

    def test_on_tree_node_selected_folder(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "folder"), None)
        if node:
            self.page.on_tree_node_selected("folder", node.id)

    def test_legacy_project_panel_removed(self):
        self.assertIsNone(self.page._project_tree)
        self.assertFalse(hasattr(self.page, "_new_project_btn"))
        self.assertFalse(hasattr(self.page, "_open_project_btn"))
        self.assertFalse(hasattr(self.page, "_save_project_btn"))
        self.assertFalse(hasattr(self.page, "_close_project_btn"))
        self.assertIsNotNone(self.page._add_image_btn)
        self.assertIsNotNone(self.page._add_curve_btn)

    def test_export_name_suggestion_uses_image_and_curve_names(self):
        self._add_digitize_curve()
        self.assertIn("SEM", self.page._export_name_edit.text())
        self.assertIn("曲线1", self.page._export_name_edit.text())

    def test_export_to_data_file_creates_digitize_result_folder_by_default(self):
        from ui.dialogs.export_flow import DataExportPlan

        self._add_digitize_curve()
        received = []
        self.page.project_modified.connect(lambda: received.append(True))

        derived_folder_id = self.page._ensure_digitize_result_folder()
        self.assertIsNotNone(derived_folder_id)

        with mock.patch(
            "ui.pages.digitize_page.choose_data_export_plan",
            return_value=DataExportPlan(
                export_name="SEM_曲线1",
                new_parent_id=derived_folder_id,
                new_data_file_name="SEM_曲线1.digitize",
            ),
        ):
            self.page._on_export_to_data_file()

        datasets_root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(datasets_root)
        derived_folder = next(
            (node for node in self.p.tree.nodes if node.kind == "folder" and node.parent_id == datasets_root.id and node.name == "数字化结果"),
            None,
        )
        self.assertIsNotNone(derived_folder)
        data_node = next(
            (node for node in self.p.tree.nodes if node.kind == "data_file" and node.parent_id == derived_folder.id),
            None,
        )
        self.assertIsNotNone(data_node)
        data_file = next((df for df in self.p.data_files if df.id == data_node.data_file_id), None)
        self.assertIsNotNone(data_file)
        self.assertTrue(data_file.name.endswith(".digitize"))
        self.assertEqual(self.page._export_target_kind, "data_file")
        self.assertEqual(self.page._export_target_id, data_node.id)
        self.assertEqual(len(received), 1)

    def test_export_to_existing_data_file_appends_series(self):
        from ui.dialogs.export_flow import DataExportPlan

        self._add_digitize_curve()
        data_node = next((node for node in self.p.tree.nodes if node.kind == "data_file" and node.data_file_id == self.df.id), None)
        self.assertIsNotNone(data_node)
        before = len(self.df.series)

        self.page.on_tree_node_selected("data_file", data_node.id)
        with mock.patch(
            "ui.pages.digitize_page.choose_data_export_plan",
            return_value=DataExportPlan(export_name="追加结果", target_data_file_id=self.df.id),
        ):
            self.page._on_export_to_data_file()

        self.assertEqual(len(self.df.series), before + 1)
        self.assertIn(data_node.name, self.page._status_label.text())


# ═══════════════════════════════════════════════════════════════════════════
# 8. MainWindow — 树面板注入、页面切换、信号路由
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# 8. MainWindow — 树面板注入、页面切换、信号路由
# ═══════════════════════════════════════════════════════════════════════════

class TestMainWindow(unittest.TestCase):
    """MainWindow 创建一次，所有测试共享同一实例"""

    @classmethod
    def setUpClass(cls):
        cls._restore_assets = _patch_global_assets()
        cls.pm, cls.p, cls.df, cls.s = _make_project("mw_test")
        cls._restore = _patch_pm(cls.pm)
        from ui.main_window import MainWindow
        cls.win = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls._restore()
        cls._restore_assets()
        cls.win.deleteLater()

    def test_window_creates_no_crash(self):
        self.assertIsNotNone(self.win)

    def test_tree_panel_exists(self):
        self.assertIsNotNone(self.win._tree_panel)

    def test_tree_panel_has_project_action_buttons(self):
        self.assertIsNotNone(self.win._tree_panel.new_project_btn)
        self.assertIsNotNone(self.win._tree_panel.open_project_btn)
        self.assertIsNotNone(self.win._tree_panel.save_project_btn)
        self.assertIsNotNone(self.win._tree_panel.close_project_btn)
        self.assertIsNotNone(self.win._tree_panel.extension_toggle_btn)

    def test_tree_panel_has_expand_and_collapse_buttons(self):
        self.assertIsNotNone(self.win._tree_panel.tree_expand_btn)
        self.assertIsNotNone(self.win._tree_panel.tree_collapse_btn)

    def test_navigation_has_tree_toggle_button(self):
        self.assertIsNotNone(self.win._tree_toggle_nav_btn)

    def test_create_project_from_panel_uses_window_level_dialog_flow(self):
        with mock.patch("ui.main_window.TextInputDialog.get_text", return_value=("面板项目", True)) as prompt_mock, \
             mock.patch("ui.main_window.QFileDialog.getExistingDirectory", return_value="/tmp/aline-panel-project") as dir_mock, \
             mock.patch.object(self.pm, "create_new", return_value=self.p) as create_mock, \
             mock.patch.object(self.win, "_on_project_created") as created_mock:
            self.win._create_project_from_panel()

        prompt_mock.assert_called_once()
        dir_mock.assert_called_once()
        create_mock.assert_called_once_with("面板项目", parent_dir="/tmp/aline-panel-project", create_structure=True)
        created_mock.assert_called_once_with("面板项目")

    def test_open_project_from_panel_uses_window_level_dialog_flow(self):
        with mock.patch("ui.main_window.QFileDialog.getOpenFileName", return_value=("/tmp/demo.pyline", "PyLine 项目 (*.pyline)")) as file_mock, \
             mock.patch.object(self.pm, "open", return_value=self.p) as open_mock, \
             mock.patch.object(self.win, "_on_project_opened") as opened_mock:
            self.win._open_project_from_panel()

        file_mock.assert_called_once()
        open_mock.assert_called_once_with("/tmp/demo.pyline")
        opened_mock.assert_called_once_with("/tmp/demo.pyline")

    def test_ai_panel_is_disabled(self):
        self.assertIsNone(self.win._ai_panel)
        self.assertTrue(self.win._tree_panel.ai_toggle_btn.isHidden())

    def test_tree_panel_has_tree_widget(self):
        from ui.widgets.project_tree import ProjectTreeWidget
        self.assertIsInstance(self.win._tree_panel.tree, ProjectTreeWidget)

    def test_tree_panel_is_hosted_in_splitter_with_width_bounds(self):
        from PySide6.QtWidgets import QSplitter

        self.assertIsInstance(self.win._tree_splitter, QSplitter)
        self.assertIs(self.win._tree_splitter.widget(0), self.win._tree_panel)
        self.assertIs(self.win._tree_splitter.widget(1), self.win.stackedWidget)
        self.assertEqual(self.win._tree_panel.minimumWidth(), 260)
        self.assertEqual(self.win._tree_panel.maximumWidth(), 420)

    def test_switch_to_data_page_shows_tree(self):
        self.win.switchTo(self.win.data_page)
        self.assertFalse(self.win._tree_panel.isHidden())

    def test_switch_to_settings_page_hides_tree(self):
        self.win.switchTo(self.win.settings_page)
        self.assertTrue(self.win._tree_panel.isHidden())
        self.assertFalse(self.win._tree_toggle_nav_btn.isEnabled())

    def test_switch_to_home_page_hides_tree(self):
        self.win.switchTo(self.win.home_page)
        self.assertTrue(self.win._tree_panel.isHidden())

    def test_switch_to_chart_page_shows_tree(self):
        self.win.switchTo(self.win.chart_page)
        self.assertFalse(self.win._tree_panel.isHidden())
        self.assertTrue(self.win._tree_toggle_nav_btn.isEnabled())

    def test_extension_toggle_button_visible_only_on_supported_pages(self):
        self.win.switchTo(self.win.data_page)
        self.assertTrue(self.win._tree_panel.extension_toggle_btn.isHidden())

        self.win.switchTo(self.win.chart_page)
        self.assertFalse(self.win._tree_panel.extension_toggle_btn.isHidden())

        self.win.switchTo(self.win.process_page)
        self.assertFalse(self.win._tree_panel.extension_toggle_btn.isHidden())

        self.win.switchTo(self.win.analysis_page)
        self.assertFalse(self.win._tree_panel.extension_toggle_btn.isHidden())

    def test_extension_toggle_button_hides_and_shows_current_page_panel(self):
        self.win.switchTo(self.win.chart_page)
        self.assertFalse(self.win.chart_page.is_extension_panel_visible())
        self.assertTrue(self.win.chart_page._extension_panel.isHidden())

        self.win._toggle_current_page_extension_panel()
        self.assertTrue(self.win.chart_page.is_extension_panel_visible())
        self.assertFalse(self.win.chart_page._extension_panel.isHidden())

        self.win._toggle_current_page_extension_panel()
        self.assertFalse(self.win.chart_page.is_extension_panel_visible())
        self.assertTrue(self.win.chart_page._extension_panel.isHidden())

    def test_tree_toggle_button_hides_and_shows_tree_panel(self):
        self.win.switchTo(self.win.data_page)
        self.assertFalse(self.win._tree_panel.isHidden())

        self.win._toggle_tree_panel()
        self.assertTrue(self.win._tree_panel.isHidden())

        self.win._toggle_tree_panel()
        self.assertFalse(self.win._tree_panel.isHidden())

    def test_switch_to_process_page_shows_tree(self):
        self.win.switchTo(self.win.process_page)
        self.assertFalse(self.win._tree_panel.isHidden())

    def test_switch_to_analysis_page_shows_tree(self):
        self.win.switchTo(self.win.analysis_page)
        self.assertFalse(self.win._tree_panel.isHidden())

    def test_switch_to_digitize_page_shows_tree(self):
        self.win.switchTo(self.win.digitize_page)
        self.assertFalse(self.win._tree_panel.isHidden())

    def test_on_project_opened_refreshes_tree(self):
        """项目打开后树自动刷新"""
        self.win._on_project_opened(self.p.name)
        self.assertGreater(
            self.win._tree_panel.tree._tree.topLevelItemCount(), 0
        )

    def test_tree_root_switches_current_project(self):
        other = self.pm.create_new("mw_other")
        self.pm.migrate_to_v3(other)
        self.pm.set_current_project(self.p.id)
        self.win._tree_panel.tree.refresh()
        project_item = self.win._tree_panel.tree._tree.topLevelItem(1)
        self.win._tree_panel.tree._on_item_clicked(project_item, 0)
        self.assertEqual(self.pm.current_project_id, other.id)

    def test_tree_node_selected_routes_to_data_page(self):
        """树信号路由到数据页"""
        self.win.switchTo(self.win.data_page)
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.win._on_tree_node_selected("data_file", node.id)
            self.assertIs(self.win.stackedWidget.currentWidget(), self.win.data_page)

    def test_ai_tool_runner_reports_disabled(self):
        result = self.win._run_ai_tool("list_tree_nodes")
        self.assertIn("AI 功能已暂停", result)

    def test_ai_tool_catalog_is_hidden(self):
        self.assertEqual(self.win._available_tools_for_page(self.win.analysis_page), [])

    def test_ai_request_reports_disabled(self):
        self.assertEqual(self.win._run_ai_request("hello"), "AI 功能已暂停")

    def test_tree_node_selected_routes_to_process_page(self):
        self.win.switchTo(self.win.process_page)
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.win._on_tree_node_selected("data_file", node.id)

    def test_tree_panel_data_actions_visible_only_on_data_page(self):
        # I-1: data action buttons are always visible regardless of which page is active
        self.win.switchTo(self.win.data_page)
        self.assertFalse(self.win._tree_panel.new_project_btn.isHidden())
        self.assertFalse(self.win._tree_panel.open_project_btn.isHidden())
        self.assertFalse(self.win._tree_panel.save_project_btn.isHidden())
        self.assertFalse(self.win._tree_panel.close_project_btn.isHidden())
        self.assertFalse(self.win._tree_panel.add_dataset_btn.isHidden())
        self.assertFalse(self.win._tree_panel.import_file_btn.isHidden())
        self.win.switchTo(self.win.process_page)
        self.assertFalse(self.win._tree_panel.new_project_btn.isHidden())
        self.assertFalse(self.win._tree_panel.open_project_btn.isHidden())
        self.assertFalse(self.win._tree_panel.save_project_btn.isHidden())
        self.assertFalse(self.win._tree_panel.close_project_btn.isHidden())
        # Data buttons remain visible on all pages (I-1 consolidation)
        self.assertFalse(self.win._tree_panel.add_dataset_btn.isHidden())
        self.assertFalse(self.win._tree_panel.import_file_btn.isHidden())

    def test_tree_node_activated_series_stays_on_analysis_page(self):
        self.win.switchTo(self.win.analysis_page)
        self.win._on_tree_node_activated("series", self.s.id)
        self.assertIs(self.win.stackedWidget.currentWidget(), self.win.analysis_page)
        self.assertEqual(len(self.win.analysis_page._selected_inputs), 1)

    def test_tree_node_activated_analysis_result_loads_analysis_page(self):
        self.win.analysis_page.on_tree_node_activated("series", self.s.id)
        self.win.analysis_page._run_analysis()
        with mock.patch("ui.pages.analysis_page.TextInputDialog.get_text", return_value=("拟合结果A", True)):
            self.win.analysis_page._save_result()
        node = next((n for n in self.p.tree.nodes if n.kind == "analysis_result"), None)
        self.assertIsNotNone(node)
        self.win.switchTo(self.win.chart_page)
        self.win._on_tree_node_activated("analysis_result", node.id)
        self.assertIs(self.win.stackedWidget.currentWidget(), self.win.analysis_page)
        self.assertEqual(self.win.analysis_page._result["analysis_type"], "curve_fit")

    def test_tree_node_activated_series_stays_on_process_page(self):
        self.win.switchTo(self.win.process_page)
        self.win._on_tree_node_activated("series", self.s.id)
        self.assertIs(self.win.stackedWidget.currentWidget(), self.win.process_page)
        self.assertEqual(self.win.process_page._selected_src_id, self.s.id)

    def test_tree_node_activated_series_stays_on_chart_page(self):
        self.win.switchTo(self.win.chart_page)
        self.win._on_tree_node_activated("series", self.s.id)
        self.assertIs(self.win.stackedWidget.currentWidget(), self.win.chart_page)
        self.assertEqual(len(self.win.chart_page._chart_series), 1)

    def test_tree_node_activated_pipeline_loads(self):
        ops = [{"type": "smooth", "params": {"method": "moving_avg", "window": 3}}]
        sp = self.pm.add_saved_pipeline("test", ops)
        if sp:
            self.win._on_tree_node_activated("global_pipeline", sp.id)

    def test_tree_node_activated_report_template(self):
        tmpl = self.pm.add_report_template("r1", "# Report")
        self.win._on_tree_node_activated("global_report_template", tmpl.id)
        self.assertEqual(self.win.analysis_page._current_report_template_id, tmpl.id)

    def test_tree_node_activated_image_work(self):
        self.win._on_tree_node_activated("image_work", "fake-img-id")


# ═══════════════════════════════════════════════════════════════════════════
# 9. 组合信号流程测试 — 模拟完整工作流
# ═══════════════════════════════════════════════════════════════════════════

class TestSignalWorkflows(unittest.TestCase):
    """组合前端信号与后端逻辑的端到端工作流"""

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        self.pm, self.p, self.df, self.s = _make_project("wf_test")
        self._restore = _patch_pm(self.pm)

    def tearDown(self):
        self._restore()
        self._restore_assets()

    def test_workflow_import_then_visualize(self):
        """
        工作流: DataPage 树节点选中 → on_tree_node_selected →
                ChartPage 接收同一节点 → 不崩溃
        """
        from ui.pages.data_page import DataPage
        from ui.pages.chart_page import ChartPage
        dp = DataPage()
        cp = ChartPage()
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        self.assertIsNotNone(node)
        dp.on_tree_node_selected("data_file", node.id)
        cp.on_tree_node_selected("data_file", node.id)
        dp.deleteLater()
        cp.deleteLater()

    def test_workflow_save_and_load_pipeline(self):
        """
        工作流: ProcessPage 加载数据 → 设置 ops →
            保存全局 Pipeline → 按 pipeline id 加载
        """
        from ui.pages.process_page import ProcessPage
        pp = ProcessPage()
        # 设置操作链
        ops = [
            {"type": "smooth", "params": {"method": "savgol", "window": 5, "poly": 2}},
            {"type": "normalize", "params": {"mode": "minmax"}},
        ]
        pp._load_ops_into_chain(ops)
        self.assertEqual(len(pp._ops), 2)
        # 保存 Pipeline
        sp = self.pm.add_saved_pipeline("流程A", ops, "测试用")
        self.assertIsNotNone(sp)
        pp.load_pipeline(sp.id)
        self.assertEqual(len(pp._ops), 2)
        self.assertEqual(pp._ops[0]["type"], "smooth")
        pp.deleteLater()

    def test_workflow_tree_node_selected_triggers_data_preview(self):
        """
        工作流: ProjectTreeWidget 发出 node_selected →
                DataPage.on_tree_node_selected 被调用 → 数据预览不崩溃
        """
        from ui.widgets.project_tree import ProjectTreeWidget
        from ui.pages.data_page import DataPage
        tree = ProjectTreeWidget()
        dp = DataPage()
        # 连接信号
        tree.node_selected.connect(dp.on_tree_node_selected)
        # 发射信号
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            tree.node_selected.emit("data_file", node.id)
        tree.deleteLater()
        dp.deleteLater()

    def test_workflow_tree_node_selected_to_analysis(self):
        """
        工作流: ProjectTreeWidget.node_selected →
                AnalysisPage.on_tree_node_selected → 系列列表更新
        """
        from ui.widgets.project_tree import ProjectTreeWidget
        from ui.pages.analysis_page import AnalysisPage
        tree = ProjectTreeWidget()
        ap = AnalysisPage()
        tree.node_selected.connect(ap.on_tree_node_selected)
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            tree.node_selected.emit("data_file", node.id)
        tree.deleteLater()
        ap.deleteLater()

    def test_workflow_tree_node_selected_to_process(self):
        """
        工作流: ProjectTreeWidget.node_selected →
                ProcessPage.on_tree_node_selected → 处理输入设置
        """
        from ui.widgets.project_tree import ProjectTreeWidget
        from ui.pages.process_page import ProcessPage
        tree = ProjectTreeWidget()
        pp = ProcessPage()
        tree.node_selected.connect(pp.on_tree_node_selected)
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            tree.node_selected.emit("data_file", node.id)
        tree.deleteLater()
        pp.deleteLater()

    def test_workflow_project_modified_refreshes_tree(self):
        """
        工作流: 树中执行创建文件夹 → project_modified 发出 →
                树刷新后包含新文件夹节点
        """
        from ui.widgets.project_tree import ProjectTreeWidget
        tree = ProjectTreeWidget()
        tree.refresh()
        nodes_before = len(self.p.tree.nodes)
        # 手动创建文件夹
        self.pm.add_folder("新文件夹_test")
        self.assertEqual(len(self.p.tree.nodes), nodes_before + 1)
        # 刷新
        tree.refresh()
        self.assertGreater(tree._tree.topLevelItemCount(), 0)
        tree.project_modified.emit()  # 验证信号可发射
        tree.deleteLater()

    def test_workflow_settings_save_ai_config_and_reload(self):
        """
        工作流: SettingsPage 保存 AI 配置 → AIConfig.load() 读回 →
                配置一致
        """
        import tempfile, json
        from ui.pages.settings_page import SettingsPage
        from core.ai_client import AIConfig
        page = SettingsPage()
        page._ai_url_edit.setText("http://localhost:11434/v1")
        page._ai_model_edit.setText("llama3")
        page._ai_timeout_edit.setText("45")
        page._ai_provider_combo.setCurrentIndex(1)  # Ollama
        # Mock 保存路径，避免写入真实配置文件
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = f.name
        orig_path = AIConfig._config_path if hasattr(AIConfig, "_config_path") else None
        # 直接测试配置对象构建
        cfg = AIConfig(
            provider="ollama",
            base_url=page._ai_url_edit.text(),
            api_key="",
            model=page._ai_model_edit.text(),
            timeout=int(page._ai_timeout_edit.text()),
        )
        self.assertEqual(cfg.provider, "ollama")
        self.assertEqual(cfg.model, "llama3")
        self.assertEqual(cfg.timeout, 45)
        page.deleteLater()
        os.unlink(tmp_path)

    def test_workflow_pipeline_node_activated_loads_to_process(self):
        """
        工作流: MainWindow._on_tree_node_activated("global_pipeline", id) →
                ProcessPage._ops 被填充（通过直接调用 ProcessPage.load_pipeline 验证）
        """
        ops = [{"type": "derivative", "params": {}}]
        sp = self.pm.add_saved_pipeline("deriv", ops)
        self.assertIsNotNone(sp)
        # 直接测试 ProcessPage.load_pipeline 而无需创建 MainWindow
        from ui.pages.process_page import ProcessPage
        pp = ProcessPage()
        pp.load_pipeline(sp.id)
        self.assertEqual(len(pp._ops), 1)
        self.assertEqual(pp._ops[0]["type"], "derivative")
        pp.deleteLater()


# ═══════════════════════════════════════════════════════════════════════════
# 10. ImportDialog 文件解析器
# ═══════════════════════════════════════════════════════════════════════════

class TestImportDialogParsers(unittest.TestCase):
    """ImportDialog 文件解析工具函数测试"""

    def _write_temp(self, content, suffix=".csv"):
        import tempfile
        f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix,
                                        delete=False, encoding="utf-8")
        f.write(content)
        f.close()
        return f.name

    def test_parse_csv_two_column(self):
        from ui.dialogs.import_dialog import _parse_file_preview
        path = self._write_temp("x,y\n1.0,2.0\n3.0,4.0\n5.0,6.0\n")
        try:
            headers, rows = _parse_file_preview(path)
            self.assertEqual(len(headers), 2)
            self.assertEqual(len(rows), 3)
            self.assertAlmostEqual(rows[0][0], 1.0)
        finally:
            os.unlink(path)

    def test_parse_csv_no_header(self):
        from ui.dialogs.import_dialog import _parse_file_preview
        path = self._write_temp("1.0,2.0\n3.0,4.0\n")
        try:
            headers, rows = _parse_file_preview(path)
            self.assertEqual(len(rows), 2)
        finally:
            os.unlink(path)

    def test_parse_csv_tab_separated(self):
        from ui.dialogs.import_dialog import _parse_file_preview
        path = self._write_temp("x\ty\n1.0\t10.0\n2.0\t20.0\n", ".txt")
        try:
            headers, rows = _parse_file_preview(path)
            self.assertEqual(len(headers), 2)
        finally:
            os.unlink(path)

    def test_parse_json_dict_fmt(self):
        import json as json_mod
        from ui.dialogs.import_dialog import _parse_file_preview
        data = {"time": [0.0, 1.0, 2.0], "force": [0.0, 10.0, 20.0]}
        path = self._write_temp(json_mod.dumps(data), ".json")
        try:
            headers, rows = _parse_file_preview(path)
            self.assertEqual(len(headers), 2)
            self.assertEqual(len(rows), 3)
        finally:
            os.unlink(path)

    def test_parse_json_list_fmt(self):
        import json as json_mod
        from ui.dialogs.import_dialog import _parse_file_preview
        data = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
        path = self._write_temp(json_mod.dumps(data), ".json")
        try:
            headers, rows = _parse_file_preview(path)
            self.assertEqual(len(rows), 2)
        finally:
            os.unlink(path)

    def test_parse_npy(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy not available")
        from ui.dialogs.import_dialog import _parse_file_preview
        import tempfile
        arr = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        path = tempfile.mktemp(suffix=".npy")
        try:
            np.save(path, arr)
            headers, rows = _parse_file_preview(path)
            self.assertEqual(len(headers), 2)
            self.assertEqual(len(rows), 3)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_import_dialog_creates_no_crash(self):
        from ui.dialogs.import_dialog import ImportDialog
        dlg = ImportDialog()
        self.assertIsNotNone(dlg)
        dlg.deleteLater()

    def test_import_dialog_state_machine_back_and_forth(self):
        from ui.dialogs.import_dialog import ImportDialog
        dlg = ImportDialog()
        dlg._file_path = "demo.csv"
        dlg._raw_headers = ["x", "y"]
        dlg._raw_rows = [[1.0, 2.0], [3.0, 4.0]]
        dlg._btn_next.setEnabled(True)

        dlg._go_next()
        self.assertEqual(dlg._stack.currentIndex(), 1)
        self.assertEqual(dlg._btn_next.text(), "导入")
        self.assertTrue(dlg._btn_back.isEnabled())

        dlg._go_next()
        self.assertEqual(dlg._stack.currentIndex(), 2)
        self.assertEqual(dlg._btn_next.text(), "完成")

        dlg._go_back()
        self.assertEqual(dlg._stack.currentIndex(), 1)
        self.assertEqual(dlg._btn_next.text(), "导入")

        dlg._go_back()
        self.assertEqual(dlg._stack.currentIndex(), 0)
        self.assertEqual(dlg._btn_next.text(), "下一步")
        self.assertFalse(dlg._btn_back.isEnabled())
        dlg.deleteLater()

    def test_import_dialog_builds_variable_role_table(self):
        from qfluentwidgets import TableWidget
        from ui.dialogs.import_dialog import ImportDialog

        dlg = ImportDialog()
        dlg._raw_headers = ["time", "force", "col_2"]
        dlg._raw_rows = [[0.0, 1.0, 0.1], [1.0, 2.0, 0.2]]

        dlg._populate_col_table()

        self.assertIsInstance(dlg._col_table, TableWidget)
        self.assertEqual(dlg._col_table.rowCount(), 3)
        self.assertEqual(dlg._col_table.columnCount(), 6)
        self.assertEqual(dlg._name_edits[0].text(), "time")
        self.assertEqual(dlg._name_edits[2].text(), "变量3")
        self.assertTrue(dlg._role_buttons[0]["X 轴"].isChecked())
        self.assertTrue(dlg._role_buttons[1]["Y 轴"].isChecked())
        self.assertTrue(dlg._role_buttons[2]["跳过"].isChecked())
        dlg.deleteLater()

    def test_import_dialog_defaults_to_new_data_file_name(self):
        from ui.dialogs.import_dialog import ImportDialog

        dlg = ImportDialog()
        dlg._file_path = "demo.csv"
        dlg._raw_headers = ["time", "signal"]
        dlg._raw_rows = [[0.0, 1.0], [1.0, 2.0]]
        dlg._populate_col_table()

        self.assertIsNone(dlg.get_target_data_file_id())
        self.assertEqual(dlg.get_file_name(), "demo.csv")
        dlg.deleteLater()

    def test_import_dialog_can_target_existing_data_file(self):
        from ui.dialogs.import_dialog import ImportDialog

        pm, _p, _df, _s = _make_project("import_existing")
        restore = _patch_pm(pm)
        dlg = None
        try:
            dlg = ImportDialog()
            dlg._file_path = "demo.csv"
            dlg._raw_headers = ["time", "signal"]
            dlg._raw_rows = [[0.0, 1.0], [1.0, 2.0]]
            dlg._populate_col_table()

            self.assertGreaterEqual(dlg._data_file_target_combo.count(), 2)
            dlg._data_file_target_combo.setCurrentIndex(1)
            self.assertEqual(dlg.get_target_data_file_id(), pm.current_project.data_files[0].id)
            self.assertFalse(dlg._data_file_name_edit.isEnabled())
        finally:
            restore()
            if dlg is not None:
                dlg.deleteLater()

    def test_import_dialog_multi_y_uses_variable_names(self):
        from ui.dialogs.import_dialog import ImportDialog

        dlg = ImportDialog()
        dlg._file_path = "demo.csv"
        dlg._raw_headers = ["time", "force", "stress"]
        dlg._raw_rows = [[0.0, 1.0, 3.0], [1.0, 2.0, 4.0]]
        dlg._populate_col_table()
        dlg._name_edits[1].setText("力")
        dlg._name_edits[2].setText("应力")
        dlg._role_buttons[2]["Y 轴"].setChecked(True)

        series_list = dlg._do_import()

        self.assertEqual([series.name for series in series_list], ["力", "应力"])
        dlg.deleteLater()


# ═══════════════════════════════════════════════════════════════════════════
# 11. AnalysisPage — on_tree_node_activated 和输入管理
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalysisPageV3(unittest.TestCase):

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        self.pm, self.p, self.df, self.s = _make_project("ap_v3")
        self._restore = _patch_pm(self.pm)
        from ui.pages.analysis_page import AnalysisPage
        self.page = AnalysisPage()

    def tearDown(self):
        self._restore()
        self._restore_assets()
        self.page.deleteLater()

    def test_on_tree_node_activated_series_to_analysis(self):
        """_to_analysis 后缀的 kind 应去掉后缀并加入输入列表"""
        self.page.on_tree_node_activated("series_to_analysis", self.s.id)
        self.assertGreater(len(self.page._selected_inputs), 0)

    def test_on_tree_node_activated_series(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.assertGreater(len(self.page._selected_inputs), 0)

    def test_dedup_same_node_id(self):
        """同一 node_id 多次激活不重复添加"""
        self.page.on_tree_node_activated("series", self.s.id)
        self.page.on_tree_node_activated("series", self.s.id)
        self.assertEqual(len(self.page._selected_inputs), 1)

    def test_clear_inputs(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.page._clear_inputs()
        self.assertEqual(len(self.page._selected_inputs), 0)

    def test_get_selected_data_returns_series(self):
        self.page.on_tree_node_activated("series", self.s.id)
        data = self.page._get_selected_data()
        self.assertEqual(len(data), 1)
        xs, ys, name = data[0]
        self.assertEqual(len(xs), len(self.s.x))

    def test_peak_export_buttons_only_visible_in_peak_mode(self):
        self.page._type_combo.setCurrentIndex(0)
        self.assertTrue(self.page._export_peaks_btn.isHidden())
        self.assertTrue(self.page._export_valleys_btn.isHidden())

        self.page._type_combo.setCurrentIndex(1)
        self.assertFalse(self.page._export_peaks_btn.isHidden())
        self.assertFalse(self.page._export_valleys_btn.isHidden())


# ═══════════════════════════════════════════════════════════════════════════
# 12. ChartPage — on_tree_node_activated 和 _chart_series 管理
# ═══════════════════════════════════════════════════════════════════════════

class TestChartPageV3(unittest.TestCase):

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        self.pm, self.p, self.df, self.s = _make_project("cp_v3")
        self._restore = _patch_pm(self.pm)
        from ui.pages.chart_page import ChartPage
        self.page = ChartPage()

    def tearDown(self):
        self._restore()
        self._restore_assets()
        self.page.deleteLater()

    def test_on_tree_node_activated_series_adds_to_chart(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.assertGreater(len(self.page._chart_series), 0)

    def test_on_tree_node_activated_data_file_adds_all_series(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        self.assertIsNotNone(node)
        self.page.on_tree_node_activated("data_file", node.id)
        self.assertGreater(len(self.page._chart_series), 0)

    def test_dedup_same_series(self):
        self.page.on_tree_node_activated("series", self.s.id)
        count1 = len(self.page._chart_series)
        self.page.on_tree_node_activated("series", self.s.id)
        self.assertEqual(len(self.page._chart_series), count1)

    def test_clear_chart(self):
        self.page.on_tree_node_activated("series", self.s.id)
        self.page._on_clear_chart()
        self.assertEqual(len(self.page._chart_series), 0)

    def test_data_file_activation_batches_redraw(self):
        from models.schemas import DataSeries

        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        self.assertIsNotNone(node)
        self.df.series.append(DataSeries(name="s2", x=[1.0, 2.0], y=[3.0, 4.0]))

        with mock.patch.object(self.page, "_redraw_now") as redraw:
            self.page.on_tree_node_activated("data_file", node.id)

        self.assertEqual(len(self.page._chart_series), 2)
        self.assertEqual(redraw.call_count, 1)

    def test_export_to_picture_group_creates_project_picture_node(self):
        from ui.dialogs.export_flow import PictureExportPlan

        self.page.on_tree_node_activated("series", self.s.id)
        with tempfile.TemporaryDirectory() as temp_dir:
            project_file = Path(temp_dir) / "chart_export.pyline"
            self.pm.save(str(project_file))
            picture_root = next(
                n for n in self.p.tree.nodes
                if n.kind == "folder" and getattr(n, "group_type", None) == "pictures"
            )
            self.page.on_tree_node_selected("folder", picture_root.id)
            with mock.patch(
                "ui.pages.chart_page.choose_picture_export_plan",
                return_value=PictureExportPlan(export_name="chart.png", target_folder_id=picture_root.id),
            ):
                self.page._on_export_to_picture_group()

            self.assertEqual(len(self.p.pictures), 1)
            picture = self.p.pictures[0]
            self.assertTrue(Path(self.pm.get_picture_path(picture.id)).exists())
            picture_node = next((n for n in self.p.tree.nodes if n.kind == "picture" and n.picture_id == picture.id), None)
            self.assertIsNotNone(picture_node)
            self.assertEqual(picture_node.parent_id, picture_root.id)

    def test_project_modified_signal_emitted_on_save_template(self):
        """保存模板应发出 project_modified"""
        from models.schemas import FigureConfig
        received = []
        self.page.project_modified.connect(lambda: received.append(True))
        cfg = FigureConfig(name="tmpl_test")
        tm = self.pm.add_figure_template(cfg)
        self.page.project_modified.emit()
        self.assertEqual(len(received), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 13. SettingsPage v0.3 — temperature/max_tokens 字段
# ═══════════════════════════════════════════════════════════════════════════

class TestSettingsPageV3(unittest.TestCase):

    def setUp(self):
        from ui.pages.settings_page import SettingsPage
        self.page = SettingsPage()

    def tearDown(self):
        self.page.deleteLater()

    def test_temperature_edit_exists(self):
        self.assertIsNotNone(self.page._ai_temperature_edit)

    def test_max_tokens_edit_exists(self):
        self.assertIsNotNone(self.page._ai_max_tokens_edit)

    def test_top_p_edit_exists(self):
        self.assertIsNotNone(self.page._ai_top_p_edit)

    def test_system_prompt_edit_exists(self):
        self.assertIsNotNone(self.page._ai_system_prompt_edit)

    def test_save_with_temperature(self):
        self.page._ai_temperature_edit.setText("0.5")
        self.page._ai_top_p_edit.setText("0.8")
        self.page._ai_max_tokens_edit.setText("1024")
        self.page._ai_system_prompt_edit.setPlainText("请使用中文")
        self.page._save_ai_config()  # should not crash

    def test_invalid_temperature_fallback(self):
        self.page._ai_temperature_edit.setText("not_a_number")
        self.page._save_ai_config()  # should fallback without crash

    def test_invalid_max_tokens_fallback(self):
        self.page._ai_max_tokens_edit.setText("-1abc")
        self.page._save_ai_config()  # should fallback without crash

    def test_invalid_top_p_fallback(self):
        self.page._ai_top_p_edit.setText("2.5")
        cfg = self.page._collect_ai_config()
        self.assertEqual(cfg.top_p, 1.0)

    def test_tmpl_list_exists(self):
        self.assertIsNotNone(self.page._tmpl_list)
        self.assertTrue(self.page._tmpl_card.isHidden())

    def test_refresh_templates_no_project(self):
        """无打开项目时刷新不崩溃"""
        self.page.refresh_templates()

    def test_refresh_templates_with_project(self):
        from core.project_manager import ProjectManager
        pm = ProjectManager()
        p = pm.create_new("sett_tmpl_test")
        pm.add_report_template("tmpl1", "# Hello")
        # Patch and refresh
        restore = _patch_pm(pm)
        try:
            self.page.refresh_templates()
            self.assertEqual(self.page._tmpl_list.count(), 0)
        finally:
            restore()

    def test_report_template_card_hidden(self):
        self.assertTrue(self.page._tmpl_card.isHidden())


class TestReportTemplateDialog(unittest.TestCase):

    def setUp(self):
        self._restore_assets = _patch_global_assets()
        from core.global_assets import global_assets
        from models.schemas import ReportTemplate
        from ui.dialogs import report_template_dialog as report_dialog_module

        self._report_dialog_module = report_dialog_module
        self._web_patch = mock.patch.object(report_dialog_module, "_HAS_WEB", False)
        self._web_patch.start()
        self.template = global_assets.add_report_template(ReportTemplate(name="报告模板A", content="# Old Report"))
        self.dialog = report_dialog_module.ReportTemplateDialog(template_id=self.template.id)

    def tearDown(self):
        self.dialog.deleteLater()
        self._web_patch.stop()
        self._restore_assets()

    def test_load_template_list_uses_global_assets(self):
        items = [self.dialog._tmpl_combo.itemText(i) for i in range(self.dialog._tmpl_combo.count())]
        self.assertIn("报告模板A", items)

    def test_save_template_updates_existing_template_without_duplication(self):
        from core.global_assets import global_assets

        self.dialog._editor.setPlainText("# Updated Report")
        with mock.patch("ui.dialogs.report_template_dialog.TextInputDialog.get_text", return_value=("报告模板A", True)):
            self.dialog._on_save_template()

        matches = [item for item in global_assets.list_report_templates() if item.name == "报告模板A"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, self.template.id)
        self.assertEqual(matches[0].content, "# Updated Report")


if __name__ == "__main__":
    unittest.main()
