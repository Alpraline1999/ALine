from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon as FIF, FluentWindow, NavigationItemPosition,
    setTheme, Theme, MessageBox, SubtitleLabel, ToolButton,
)

from .pages.home_page import HomePage
from .pages.digitize_page import DigitizePage
from .pages.chart_page import ChartPage
from .pages.data_page import DataPage
from .pages.process_page import ProcessPage
from .pages.analysis_page import AnalysisPage
from .pages.settings_page import SettingsPage
from .widgets.project_tree import ProjectTreeWidget
from core.project_manager import project_manager

# 每个页面显示的树节点类型（空列表 = 不显示树）
_PAGE_TREE_KINDS = {
    "homePage":      [],
    "dataPage":      ["folder", "data_file", "image_work", "series", "curve"],
    "chartPage":     ["folder", "data_file", "image_work", "figure_template", "series", "curve"],
    "processPage":   ["folder", "data_file", "image_work", "pipeline", "series", "curve"],
    "analysisPage":  ["folder", "data_file", "image_work", "series", "curve"],
    "digitizePage":  ["folder", "image_work"],
    "settingsPage":  [],
}


class _SharedTreePanel(QWidget):
    """固定260px宽的项目树侧边面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(260)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.tree = ProjectTreeWidget(self)
        layout.addWidget(self.tree)


class MainWindow(FluentWindow):
    """ALine 主窗口 — 统一共享项目树"""

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._setup_theme_watcher()
        self._setup_project_signals()

    def _setup_ui(self):
        self.setWindowTitle("ALine")
        self.resize(1440, 860)

        # ── 页面实例 ──────────────────────────────────────────
        self.home_page = HomePage(self)
        self.home_page.setObjectName("homePage")

        self.data_page = DataPage(self)
        self.data_page.setObjectName("dataPage")

        self.chart_page = ChartPage(self)
        self.chart_page.setObjectName("chartPage")

        self.process_page = ProcessPage(self)
        self.process_page.setObjectName("processPage")

        self.analysis_page = AnalysisPage(self)
        self.analysis_page.setObjectName("analysisPage")

        self.digitize_page = DigitizePage(self)
        self.digitize_page.setObjectName("digitizePage")

        self.settings_page = SettingsPage(self)
        self.settings_page.setObjectName("settingsPage")

        # ── 导航注册（新顺序：数据管理优先）──────────────────
        self.addSubInterface(self.home_page,     FIF.HOME,            "主页",    NavigationItemPosition.TOP)
        self.addSubInterface(self.data_page,     FIF.FOLDER,          "数据管理", NavigationItemPosition.TOP)
        self.addSubInterface(self.chart_page,    FIF.PIE_SINGLE,      "可视化",   NavigationItemPosition.TOP)
        self.addSubInterface(self.process_page,  FIF.DEVELOPER_TOOLS, "数据处理", NavigationItemPosition.TOP)
        self.addSubInterface(self.analysis_page, FIF.SEARCH,          "数据分析", NavigationItemPosition.TOP)
        self.addSubInterface(self.digitize_page, FIF.EDIT,            "图片取点", NavigationItemPosition.TOP)
        self.addSubInterface(self.settings_page, FIF.SETTING,         "设置",    NavigationItemPosition.BOTTOM)

        # 永久 COMPACT（图标）模式
        self.navigationInterface.panel.setMenuButtonVisible(False)
        self.navigationInterface.panel.setMinimumExpandWidth(99999)

        # ── 注入共享树面板 ─────────────────────────────────────
        self._tree_panel = _SharedTreePanel(self)
        self._tree_panel.hide()
        # widgetLayout 是 FluentWindow 里包含 stackedWidget 的 QHBoxLayout
        self.widgetLayout.insertWidget(0, self._tree_panel)

    def _setup_theme_watcher(self):
        self.settings_page.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.settings_page.shortcuts_changed.connect(self.digitize_page.apply_shortcuts)

    def _setup_project_signals(self):
        self.home_page.project_created.connect(self._on_project_created)
        self.home_page.project_opened.connect(self._on_project_opened)
        self.digitize_page.project_modified.connect(self._on_project_modified)
        self.digitize_page.project_saved.connect(self._update_window_title)

        # 数据管理页信号
        self.data_page.project_modified.connect(self._on_project_modified)
        self.data_page.send_to_visualize.connect(self._on_send_to_visualize)
        self.data_page.send_to_process.connect(self._on_send_to_process)

        # 共享树信号路由
        self._tree_panel.tree.node_selected.connect(self._on_tree_node_selected)
        self._tree_panel.tree.node_activated.connect(self._on_tree_node_activated)
        self._tree_panel.tree.project_modified.connect(self._on_project_modified)
        self._tree_panel.tree.project_modified.connect(self._tree_panel.tree.refresh)

        # 页面修改后刷新树
        for page in [self.digitize_page, self.data_page, self.process_page]:
            page.project_modified.connect(self._tree_panel.tree.refresh)

    # ─────────────────────────────────────────────────────────
    # FluentWindow.switchTo 覆盖
    # ─────────────────────────────────────────────────────────

    def switchTo(self, interface, isAutoScroll: bool = False) -> None:
        super().switchTo(interface)
        obj_name = getattr(interface, "objectName", lambda: "")()
        kinds = _PAGE_TREE_KINDS.get(obj_name, [])
        show = bool(kinds)
        self._tree_panel.setVisible(show)
        if show:
            self._tree_panel.tree.set_filter_kinds(kinds)

    # ─────────────────────────────────────────────────────────
    # 项目生命周期
    # ─────────────────────────────────────────────────────────

    def _on_project_created(self, name: str):
        p = project_manager.current_project
        if p is not None:
            project_manager.migrate_to_v2(p)
            project_manager.migrate_to_v3(p)
        self._update_window_title()
        self.digitize_page._refresh_project_tree()
        self.data_page.refresh()
        self._tree_panel.tree.refresh()
        self.settings_page.refresh_templates()
        self.switchTo(self.data_page)

    def _on_project_opened(self, file_path: str):
        p = project_manager.current_project
        if p is not None:
            project_manager.migrate_to_v2(p)
            project_manager.migrate_to_v3(p)
        self._update_window_title()
        self.digitize_page._refresh_project_tree()
        self.data_page.refresh()
        self._tree_panel.tree.refresh()
        self.settings_page.refresh_templates()
        self.switchTo(self.data_page)

    def _on_project_modified(self):
        if project_manager.current_project:
            project_manager.current_project.is_modified = True
        self._update_window_title()

    def _update_window_title(self):
        if project_manager.current_project:
            name = project_manager.current_project.name
            marker = " *" if project_manager.current_project.is_modified else ""
            self.setWindowTitle(f"ALine - {name}{marker}")
        else:
            self.setWindowTitle("ALine")

    # ─────────────────────────────────────────────────────────
    # 树节点路由
    # ─────────────────────────────────────────────────────────

    def _on_tree_node_activated(self, kind: str, node_id: str) -> None:
        """双击节点 → 跳转到对应功能页并传递选中。"""
        if kind == "image_work":
            self.switchTo(self.digitize_page)
            if hasattr(self.digitize_page, 'load_image_by_id'):
                self.digitize_page.load_image_by_id(node_id)
        elif kind == "pipeline":
            if hasattr(self.process_page, 'load_pipeline'):
                self.process_page.load_pipeline(node_id)
            self.switchTo(self.process_page)
        elif kind in ("figure_template",):
            if hasattr(self.chart_page, 'load_template'):
                self.chart_page.load_template(node_id)
            self.switchTo(self.chart_page)
        elif kind in ("data_file", "series", "curve",
                       "data_file_to_chart", "image_work_to_chart",
                       "series_to_chart", "curve_to_chart"):
            self.switchTo(self.chart_page)
            if hasattr(self.chart_page, 'on_tree_node_activated'):
                self.chart_page.on_tree_node_activated(kind, node_id)
        elif kind in ("data_file_to_process", "series_to_process", "curve_to_process"):
            self.switchTo(self.process_page)
            if hasattr(self.process_page, 'on_tree_node_selected'):
                self.process_page.on_tree_node_selected(kind, node_id)
        elif kind in ("data_file_to_analysis", "series_to_analysis", "curve_to_analysis"):
            self.switchTo(self.analysis_page)
            if hasattr(self.analysis_page, 'on_tree_node_activated'):
                self.analysis_page.on_tree_node_activated(kind, node_id)

    def _on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """单击节点 → 通知当前页面。"""
        page = self.stackedWidget.currentWidget()
        if hasattr(page, 'on_tree_node_selected'):
            page.on_tree_node_selected(kind, node_id)

    # ─────────────────────────────────────────────────────────
    # 数据页路由（保留）
    # ─────────────────────────────────────────────────────────

    def _on_send_to_visualize(self, data_type: str, obj_id: str):
        self.switchTo(self.chart_page)
        if hasattr(self.chart_page, 'receive_data'):
            self.chart_page.receive_data(data_type, obj_id)

    def _on_send_to_process(self, data_type: str, obj_id: str):
        self.switchTo(self.process_page)
        if hasattr(self.process_page, 'receive_data'):
            self.process_page.receive_data(data_type, obj_id)

    # ─────────────────────────────────────────────────────────
    # 关闭 / 主题
    # ─────────────────────────────────────────────────────────

    def closeEvent(self, event):
        unsaved = [p for p in project_manager.projects if p.is_modified]
        if unsaved:
            names = "、".join(p.name for p in unsaved)
            dlg = MessageBox("未保存的更改", f"以下项目有未保存的更改：\n{names}\n\n确定要退出吗？", self)
            if not dlg.exec():
                event.ignore()
                return
        event.accept()

    def _on_theme_changed(self, index: int):
        themes = [Theme.LIGHT, Theme.DARK, Theme.AUTO]
        setTheme(themes[index])
        QTimer.singleShot(100, self._update_all_pages_theme)

    def _update_all_pages_theme(self):
        self.home_page.update_theme()
        self.settings_page._update_colors()
        self.digitize_page.update_theme_colors()
        self.chart_page._redraw()
        self.data_page.update_theme()
        self.process_page.update_theme()
        self.analysis_page.update_theme()
