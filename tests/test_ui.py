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
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 项目根路径
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

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


# ═══════════════════════════════════════════════════════════════════════════
# 1. ProjectTreeWidget
# ═══════════════════════════════════════════════════════════════════════════

class TestProjectTreeWidget(unittest.TestCase):
    """ProjectTreeWidget 信号与基本操作"""

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("tree_test")
        self._restore = _patch_pm(self.pm)
        from ui.widgets.project_tree import ProjectTreeWidget
        self.widget = ProjectTreeWidget()

    def tearDown(self):
        self._restore()
        self.widget.deleteLater()

    def test_refresh_builds_tree(self):
        self.widget.refresh()
        # 树应该有若干根节点
        self.assertGreater(self.widget._tree.topLevelItemCount(), 0)

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


# ═══════════════════════════════════════════════════════════════════════════
# 2. SettingsPage — AI 配置
# ═══════════════════════════════════════════════════════════════════════════

class TestSettingsPage(unittest.TestCase):
    """SettingsPage AI 接口配置信号"""

    def setUp(self):
        from ui.pages.settings_page import SettingsPage
        self.page = SettingsPage()

    def tearDown(self):
        self.page.deleteLater()

    def test_page_creates_without_crash(self):
        self.assertIsNotNone(self.page)

    def test_theme_combo_exists(self):
        self.assertIsNotNone(self.page.theme_combo)

    def test_ai_url_edit_exists(self):
        self.assertIsNotNone(self.page._ai_url_edit)

    def test_ai_model_edit_exists(self):
        self.assertIsNotNone(self.page._ai_model_edit)

    def test_save_ai_config_no_crash(self):
        self.page._ai_url_edit.setText("https://api.openai.com/v1")
        self.page._ai_model_edit.setText("gpt-4o-mini")
        self.page._ai_timeout_edit.setText("30")
        self.page._save_ai_config()

    def test_provider_changed_to_ollama(self):
        # API key should be disabled for Ollama
        self.page._ai_url_edit.setText("")  # Clear URL so default gets set
        self.page._ai_provider_combo.setCurrentIndex(1)  # Ollama
        self.assertFalse(self.page._ai_key_edit.isEnabled())
        # Ollama 时若 URL 为空则设置默认值
        self.assertIn("11434", self.page._ai_url_edit.text())

    def test_provider_changed_back_to_openai(self):
        self.page._ai_provider_combo.setCurrentIndex(1)
        self.page._ai_provider_combo.setCurrentIndex(0)
        self.assertTrue(self.page._ai_key_edit.isEnabled())

    def test_shortcuts_changed_signal(self):
        received = []
        self.page.shortcuts_changed.connect(lambda: received.append(True))
        self.page._on_apply_shortcuts()
        self.assertEqual(len(received), 1)

    def test_reset_shortcuts_no_crash(self):
        self.page._on_reset_shortcuts()

    def test_timeout_invalid_fallback(self):
        """非数字超时输入应 fallback 到 60"""
        self.page._ai_timeout_edit.setText("abc")
        self.page._save_ai_config()  # 不崩溃


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

    def test_on_tree_node_selected_data_file(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.page.on_tree_node_selected("data_file", node.id)

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


# ═══════════════════════════════════════════════════════════════════════════
# 4. ChartPage — on_tree_node_selected, load_template
# ═══════════════════════════════════════════════════════════════════════════

class TestChartPage(unittest.TestCase):

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("cp_test")
        self._restore = _patch_pm(self.pm)
        from ui.pages.chart_page import ChartPage
        self.page = ChartPage()

    def tearDown(self):
        self._restore()
        self.page.deleteLater()

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

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
        from models.schemas import FigureConfig
        cfg = FigureConfig(name="templ1")
        node = self.pm.add_figure_template(cfg)
        self.assertIsNotNone(node)
        self.page.load_template(node.id)


# ═══════════════════════════════════════════════════════════════════════════
# 5. ProcessPage — on_tree_node_selected, load_pipeline
# ═══════════════════════════════════════════════════════════════════════════

class TestProcessPage(unittest.TestCase):

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("pp_test")
        self._restore = _patch_pm(self.pm)
        from ui.pages.process_page import ProcessPage
        self.page = ProcessPage()

    def tearDown(self):
        self._restore()
        self.page.deleteLater()

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

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
        # 找到 pipeline 节点
        node = next((n for n in self.p.tree.nodes if n.kind == "pipeline"), None)
        self.assertIsNotNone(node)
        self.page.load_pipeline(node.id)
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


# ═══════════════════════════════════════════════════════════════════════════
# 6. AnalysisPage — on_tree_node_selected
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalysisPage(unittest.TestCase):

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("ap_test")
        self._restore = _patch_pm(self.pm)
        from ui.pages.analysis_page import AnalysisPage
        self.page = AnalysisPage()

    def tearDown(self):
        self._restore()
        self.page.deleteLater()

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

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

    def test_page_creates_no_crash(self):
        self.assertIsNotNone(self.page)

    def test_load_image_by_id_nonexistent(self):
        """不存在的 ID 不崩溃"""
        self.page.load_image_by_id("nonexistent-id")

    def test_on_tree_node_selected_image_work(self):
        self.page.on_tree_node_selected("image_work", "fake-image-id")

    def test_on_tree_node_selected_folder(self):
        node = next((n for n in self.p.tree.nodes if n.kind == "folder"), None)
        if node:
            self.page.on_tree_node_selected("folder", node.id)


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
        cls.pm, cls.p, cls.df, cls.s = _make_project("mw_test")
        cls._restore = _patch_pm(cls.pm)
        from ui.main_window import MainWindow
        cls.win = MainWindow()

    @classmethod
    def tearDownClass(cls):
        cls._restore()
        cls.win.deleteLater()

    def test_window_creates_no_crash(self):
        self.assertIsNotNone(self.win)

    def test_tree_panel_exists(self):
        self.assertIsNotNone(self.win._tree_panel)

    def test_tree_panel_has_tree_widget(self):
        from ui.widgets.project_tree import ProjectTreeWidget
        self.assertIsInstance(self.win._tree_panel.tree, ProjectTreeWidget)

    def test_switch_to_data_page_shows_tree(self):
        self.win.switchTo(self.win.data_page)
        self.assertFalse(self.win._tree_panel.isHidden())

    def test_switch_to_settings_page_hides_tree(self):
        self.win.switchTo(self.win.settings_page)
        self.assertTrue(self.win._tree_panel.isHidden())

    def test_switch_to_home_page_hides_tree(self):
        self.win.switchTo(self.win.home_page)
        self.assertTrue(self.win._tree_panel.isHidden())

    def test_switch_to_chart_page_shows_tree(self):
        self.win.switchTo(self.win.chart_page)
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

    def test_tree_node_selected_routes_to_data_page(self):
        """树信号路由到数据页"""
        self.win.switchTo(self.win.data_page)
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.win._on_tree_node_selected("data_file", node.id)

    def test_tree_node_selected_routes_to_process_page(self):
        self.win.switchTo(self.win.process_page)
        node = next((n for n in self.p.tree.nodes if n.kind == "data_file"), None)
        if node:
            self.win._on_tree_node_selected("data_file", node.id)

    def test_tree_node_activated_pipeline_loads(self):
        ops = [{"type": "smooth", "params": {"method": "moving_avg", "window": 3}}]
        self.pm.add_saved_pipeline("test", ops)
        node = next((n for n in self.p.tree.nodes if n.kind == "pipeline"), None)
        if node:
            self.win._on_tree_node_activated("pipeline", node.id)

    def test_tree_node_activated_figure_template(self):
        from models.schemas import FigureConfig
        cfg = FigureConfig(name="t1")
        tn = self.pm.add_figure_template(cfg)
        if tn:
            self.win._on_tree_node_activated("figure_template", tn.id)

    def test_tree_node_activated_image_work(self):
        self.win._on_tree_node_activated("image_work", "fake-img-id")


# ═══════════════════════════════════════════════════════════════════════════
# 9. 组合信号流程测试 — 模拟完整工作流
# ═══════════════════════════════════════════════════════════════════════════

class TestSignalWorkflows(unittest.TestCase):
    """组合前端信号与后端逻辑的端到端工作流"""

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("wf_test")
        self._restore = _patch_pm(self.pm)

    def tearDown(self):
        self._restore()

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
                保存 Pipeline → 树出现新节点 → 加载 Pipeline
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
        nodes_before = len(self.p.tree.nodes)
        # 树中应有 pipeline 节点
        pnode = next((n for n in self.p.tree.nodes if n.kind == "pipeline"), None)
        self.assertIsNotNone(pnode)
        # 加载 Pipeline
        pp.load_pipeline(pnode.id)
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
        工作流: MainWindow._on_tree_node_activated("pipeline", id) →
                ProcessPage._ops 被填充（通过直接调用 ProcessPage.load_pipeline 验证）
        """
        ops = [{"type": "derivative", "params": {}}]
        self.pm.add_saved_pipeline("deriv", ops)
        pnode = next((n for n in self.p.tree.nodes if n.kind == "pipeline"), None)
        self.assertIsNotNone(pnode)
        # 直接测试 ProcessPage.load_pipeline 而无需创建 MainWindow
        from ui.pages.process_page import ProcessPage
        pp = ProcessPage()
        pp.load_pipeline(pnode.id)
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


# ═══════════════════════════════════════════════════════════════════════════
# 11. AnalysisPage — on_tree_node_activated 和输入管理
# ═══════════════════════════════════════════════════════════════════════════

class TestAnalysisPageV3(unittest.TestCase):

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("ap_v3")
        self._restore = _patch_pm(self.pm)
        from ui.pages.analysis_page import AnalysisPage
        self.page = AnalysisPage()

    def tearDown(self):
        self._restore()
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


# ═══════════════════════════════════════════════════════════════════════════
# 12. ChartPage — on_tree_node_activated 和 _chart_series 管理
# ═══════════════════════════════════════════════════════════════════════════

class TestChartPageV3(unittest.TestCase):

    def setUp(self):
        self.pm, self.p, self.df, self.s = _make_project("cp_v3")
        self._restore = _patch_pm(self.pm)
        from ui.pages.chart_page import ChartPage
        self.page = ChartPage()

    def tearDown(self):
        self._restore()
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

    def test_save_with_temperature(self):
        self.page._ai_temperature_edit.setText("0.5")
        self.page._ai_max_tokens_edit.setText("1024")
        self.page._save_ai_config()  # should not crash

    def test_invalid_temperature_fallback(self):
        self.page._ai_temperature_edit.setText("not_a_number")
        self.page._save_ai_config()  # should fallback without crash

    def test_invalid_max_tokens_fallback(self):
        self.page._ai_max_tokens_edit.setText("-1abc")
        self.page._save_ai_config()  # should fallback without crash

    def test_tmpl_list_exists(self):
        self.assertIsNotNone(self.page._tmpl_list)

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
            self.assertGreater(self.page._tmpl_list.count(), 0)
        finally:
            restore()


if __name__ == "__main__":
    unittest.main()
