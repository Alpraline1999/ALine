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
from .widgets.ai_assistant_panel import AIAssistantPanel
from core.project_manager import project_manager
from core.ai_client import AIConfig
from core.ai.tool_executor import execute_tool
from core.ai.tool_registry import TOOLS

# 页面 2-6 默认显示完整共享树，主页和设置页不显示。
_BUSINESS_TREE_KINDS = [
    "folder", "data_file", "image_work",
    "pipeline", "figure_template", "report_template",
    "ai_prompt", "ai_skill", "ai_agent",
    "series", "curve",
]

# 每个页面显示的树节点类型（空列表 = 不显示树）
_PAGE_TREE_KINDS = {
    "homePage":      [],
    "dataPage":      _BUSINESS_TREE_KINDS,
    "chartPage":     _BUSINESS_TREE_KINDS,
    "processPage":   _BUSINESS_TREE_KINDS,
    "analysisPage":  _BUSINESS_TREE_KINDS,
    "digitizePage":  _BUSINESS_TREE_KINDS,
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

        self._ai_panel = AIAssistantPanel(self)
        self._ai_panel.hide()
        self.widgetLayout.addWidget(self._ai_panel)

    def _setup_theme_watcher(self):
        self.settings_page.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.settings_page.shortcuts_changed.connect(self.digitize_page.apply_shortcuts)
        self.settings_page.ai_panel_visibility_changed.connect(self._on_ai_panel_visibility_changed)

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
        for page in [self.digitize_page, self.data_page, self.process_page, self.analysis_page]:
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
        self._ai_panel.setVisible(show and AIConfig.load().show_assistant)
        if show:
            self._tree_panel.tree.set_filter_kinds(kinds)
        self._update_ai_panel_context(page=interface)

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
        elif kind == "report_template":
            self.switchTo(self.analysis_page)
            if hasattr(self.analysis_page, 'load_report_template'):
                self.analysis_page.load_report_template(node_id)
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
        """单击节点 → 通知当前页面并同步 AI 助手上下文。"""
        page = self.stackedWidget.currentWidget()
        if hasattr(page, 'on_tree_node_selected'):
            page.on_tree_node_selected(kind, node_id)
        self._update_ai_panel_context(page=page, selected_kind=kind, node_id=node_id)

    def _on_ai_panel_visibility_changed(self, visible: bool) -> None:
        current_page = self.stackedWidget.currentWidget()
        obj_name = getattr(current_page, "objectName", lambda: "")()
        self._ai_panel.setVisible(bool(_PAGE_TREE_KINDS.get(obj_name, [])) and visible)

    def _describe_node_for_ai(self, kind: str, node_id: str) -> str:
        if not node_id:
            return "未选择节点"
        if kind in ("series", "curve"):
            series = project_manager.get_series_from_node(kind, node_id)
            if series is not None:
                return f"{kind}: {series.name}"
        node = project_manager.get_node_by_id(node_id)
        if node is not None:
            return f"{kind}: {node.name}"
        return f"{kind}: {node_id}"

    def _build_ai_context_text(self, page) -> str:
        if page is None:
            return "暂无页面上下文"
        if page is self.data_page:
            selected_type = getattr(page, "_selected_type", None)
            selected_id = getattr(page, "_selected_id", None)
            return f"数据页当前预览类型: {selected_type or '无'}\n当前预览 ID: {selected_id or '无'}"
        if page is self.chart_page:
            chart_series = getattr(page, "_chart_series", [])
            return f"图表工作集条目数: {len(chart_series)}"
        if page is self.process_page:
            ops = getattr(page, "_ops", [])
            selected_src_id = getattr(page, "_selected_src_id", None)
            return f"处理链操作数: {len(ops)}\n当前输入 ID: {selected_src_id or '无'}"
        if page is self.analysis_page:
            inputs = getattr(page, "_selected_inputs", [])
            result = getattr(page, "_result", None)
            report_name = getattr(page, "_current_report_template_name", "默认模板")
            analysis_type = result.get("analysis_type") if isinstance(result, dict) else "未运行"
            return f"分析输入数: {len(inputs)}\n当前分析类型: {analysis_type}\n当前报告模板: {report_name}"
        if page is self.digitize_page:
            image_id = getattr(page, "_current_image_id", None)
            curve_id = getattr(page, "_current_curve_id", None)
            export_target = getattr(page, "_export_target_id", None)
            return f"当前图片 ID: {image_id or '无'}\n当前曲线 ID: {curve_id or '无'}\n导出目标 ID: {export_target or '无'}"
        return "暂无页面上下文"

    def _tool_context_for_current_page(self, page) -> dict:
        return {
            "selected_node_id": getattr(self, "_last_ai_node_id", None),
            "chart_page": self.chart_page if page is self.chart_page else None,
            "process_page": self.process_page if page is self.process_page else None,
            "analysis_page": self.analysis_page if page is self.analysis_page else None,
            "digitize_page": self.digitize_page if page is self.digitize_page else None,
        }

    def _available_tools_for_page(self, page) -> list[str]:
        tools = ["list_tree_nodes", "get_node_detail", "list_data_files"]
        if page is self.chart_page:
            tools.append("read_chart_config")
        if page is self.process_page:
            tools.append("save_pipeline_template")
        if page is self.analysis_page:
            tools.append("render_report_template")
        if page is self.digitize_page:
            tools.append("export_curve_to_data_file")
        return [tool for tool in tools if tool in TOOLS]

    def _run_ai_tool(self, tool_name: str) -> str:
        page = self.stackedWidget.currentWidget()
        return execute_tool(tool_name, self._tool_context_for_current_page(page))

    def _page_label_for_ai(self, page) -> str:
        if page is self.data_page:
            return "数据管理"
        if page is self.chart_page:
            return "可视化"
        if page is self.process_page:
            return "数据处理"
        if page is self.analysis_page:
            return "数据分析"
        if page is self.digitize_page:
            return "图片取点"
        if page is self.settings_page:
            return "设置"
        return "主页"

    def _update_ai_panel_context(self, page=None, selected_kind: str | None = None, node_id: str | None = None) -> None:
        page = page or self.stackedWidget.currentWidget()
        self._ai_panel.set_current_page(self._page_label_for_ai(page))
        if selected_kind and node_id:
            self._last_ai_node_id = node_id
            self._ai_panel.set_selected_node(self._describe_node_for_ai(selected_kind, node_id))
        self._ai_panel.set_context_text(self._build_ai_context_text(page))
        self._ai_panel.set_tool_runner(self._run_ai_tool, self._available_tools_for_page(page))

    # ─────────────────────────────────────────────────────────
    # 数据页路由（保留）
    # ─────────────────────────────────────────────────────────

    def _on_send_to_visualize(self, data_type: str, obj_id: str):
        self.switchTo(self.chart_page)
        if hasattr(self.chart_page, 'receive_data'):
            self.chart_page.receive_data(data_type, obj_id)
        self._update_ai_panel_context(page=self.chart_page, selected_kind=data_type, node_id=obj_id)

    def _on_send_to_process(self, data_type: str, obj_id: str):
        self.switchTo(self.process_page)
        if hasattr(self.process_page, 'receive_data'):
            self.process_page.receive_data(data_type, obj_id)
        self._update_ai_panel_context(page=self.process_page, selected_kind=data_type, node_id=obj_id)

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
