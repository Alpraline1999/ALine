import asyncio
from typing import Protocol, cast

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QSizePolicy, QSplitter, QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon as FIF, FluentWindow, NavigationItemPosition,
    NavigationToolButton,
    setTheme, Theme, MessageBox, ToggleToolButton, ToolButton,
    ToolTipFilter, ToolTipPosition,
)

from app.context import AppContext
from app.messages import AppCommand, AppCommandType, TreeCommand
from app.tree_action_dispatcher import ProjectTreeActionDispatcher
from .page_view_state import MainWindowViewState
from .pages.home_page import HomePage
from .pages.digitize_page import DigitizePage
from .pages.chart_page import ChartPage
from .pages.data_page import DataPage
from .pages.process_page import ProcessPage
from .pages.analysis_page import AnalysisPage
from .pages.settings_page import SettingsPage
from .dialogs.fluent_dialogs import TextInputDialog
from .dialogs.project_tree_manage_dialog import ProjectTreeManageDialog
from .notifications import show_error, show_success, show_warning
from .widgets.project_tree import ProjectTreeWidget
from ai.agent import ALineAgent
from ai.command_layer import CommandDispatcher
from core.global_assets import global_assets
from core.project_manager import project_manager
from core.ui_preferences import is_page_tree_focus_mode_enabled, reset_all_onboarding_progress
from core.ai_client import AIConfig
from core.ai.tool_executor import execute_tool
from core.ai.tool_registry import TOOLS
from core.shortcut_manager import ShortcutBindingSet, shortcut_manager

# 页面 2-6 默认显示完整共享树，主页和设置页不显示。
_BUSINESS_TREE_KINDS = [
    "folder", "data_file", "source_file", "image_work", "picture",
    "pipeline", "figure_template", "report_template", "analysis_result",
    "global_pipeline", "global_report_template",
    "global_curve_style_template", "global_plot_style", "global_plot_theme",
    "global_extension_config",
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

_PAGE_TREE_FOCUS_KINDS = {
    "homePage":      [],
    "dataPage":      [],
    "chartPage":     ["datasets", "pictures"],
    "processPage":   ["datasets"],
    "analysisPage":  ["datasets", "analysis_result_group"],
    "digitizePage":  ["datasets", "images"],
    "settingsPage":  [],
}

_TREE_PANEL_MIN_WIDTH = 260
_TREE_PANEL_MAX_WIDTH = 420
_TREE_PANEL_DEFAULT_WIDTH = 260
_EXTENSION_PANEL_SHOW_ICON = getattr(FIF, "VIEW", FIF.SEARCH)
_EXTENSION_PANEL_HIDE_ICON = getattr(FIF, "HIDE", FIF.CANCEL)
_DATA_PAGE_NAV_ICON = getattr(FIF, "APPLICATION", FIF.FOLDER)
_DIGITIZE_PAGE_NAV_ICON = getattr(FIF, "LABEL", FIF.EDIT)
_TREE_EXPAND_ALL_ICON = getattr(FIF, "CHEVRON_DOWN_MED", getattr(FIF, "DOWN", FIF.ZOOM_IN))
_TREE_COLLAPSE_ALL_ICON = getattr(FIF, "CHEVRON_RIGHT_MED", getattr(FIF, "RIGHT_ARROW", FIF.ZOOM_OUT))


class _TreeSelectablePage(Protocol):
    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        ...


class _TreeActivatablePage(_TreeSelectablePage, Protocol):
    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        ...


class _ExtensionPanelPage(Protocol):
    def supports_extension_panel_toggle(self) -> bool:
        ...

    def is_extension_panel_visible(self) -> bool:
        ...

    def set_extension_panel_visible(self, visible: bool) -> None:
        ...


class _SharedTreePanel(QWidget):
    """可拉伸、带宽度边界的项目树侧边面板。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(_TREE_PANEL_MIN_WIDTH)
        self.setMaximumWidth(_TREE_PANEL_MAX_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # ── 单排工具栏：项目操作（左） | 分隔线 | 数据操作（右） | AI助手开关（最右）──
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(2)

        left_group_container = QWidget(self)
        left_group_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        left_group = QHBoxLayout(left_group_container)
        left_group.setContentsMargins(0, 0, 0, 0)
        left_group.setSpacing(2)

        self.new_project_btn = ToolButton(FIF.FOLDER_ADD, self)
        self.new_project_btn.setToolTip("新建项目")
        left_group.addWidget(self.new_project_btn)

        self.open_project_btn = ToolButton(FIF.FOLDER, self)
        self.open_project_btn.setToolTip("打开项目")
        left_group.addWidget(self.open_project_btn)

        self.save_project_btn = ToolButton(FIF.SAVE, self)
        self.save_project_btn.setToolTip("保存当前项目")
        left_group.addWidget(self.save_project_btn)

        self.close_project_btn = ToolButton(FIF.CLOSE, self)
        self.close_project_btn.setToolTip("关闭当前项目")
        left_group.addWidget(self.close_project_btn)

        toolbar.addWidget(left_group_container, 1)

        # 中间分隔线
        self._toolbar_separator = QFrame(self)
        self._toolbar_separator.setFrameShape(QFrame.Shape.VLine)
        self._toolbar_separator.setFixedWidth(2)
        toolbar.addWidget(self._toolbar_separator, 0, Qt.AlignmentFlag.AlignCenter)

        right_group_container = QWidget(self)
        right_group_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        right_group = QHBoxLayout(right_group_container)
        right_group.setContentsMargins(0, 0, 0, 0)
        right_group.setSpacing(2)
        right_group.addStretch(1)
        self._toolbar_right_group = right_group

        self.tree_expand_toggle_btn = ToolButton(_TREE_EXPAND_ALL_ICON, self)
        self.tree_expand_toggle_btn.setToolTip("全部展开")
        right_group.addWidget(self.tree_expand_toggle_btn)

        self.tree_manage_btn = ToolButton(FIF.ALIGNMENT, self)
        self.tree_manage_btn.setToolTip("项目树管理")
        right_group.addWidget(self.tree_manage_btn)

        self.extension_toggle_btn = ToolButton(_EXTENSION_PANEL_HIDE_ICON, self)
        self.extension_toggle_btn.setToolTip("隐藏扩展面板")
        self.extension_toggle_btn.hide()
        right_group.addWidget(self.extension_toggle_btn)

        toolbar.addWidget(right_group_container, 1)

        layout.addLayout(toolbar)

        self.tree = ProjectTreeWidget(self)
        layout.addWidget(self.tree)

        self.tree_expand_toggle_btn.clicked.connect(self._toggle_tree_expansion)
        self.tree._tree.itemExpanded.connect(self._sync_tree_expand_toggle_button)
        self.tree._tree.itemCollapsed.connect(self._sync_tree_expand_toggle_button)
        self.tree.refreshed.connect(self._sync_tree_expand_toggle_button)

        # 安装 Fluent 风格 Tooltip
        for btn in [self.new_project_btn, self.open_project_btn, self.save_project_btn,
            self.close_project_btn, self.tree_expand_toggle_btn, self.tree_manage_btn,
            self.extension_toggle_btn]:
            btn.setFixedSize(32, 32)
            btn.installEventFilter(ToolTipFilter(btn, 500, ToolTipPosition.BOTTOM))

        self._sync_tree_expand_toggle_button()

    @staticmethod
    def _tool_button_icon(icon_source):
        return icon_source.icon() if hasattr(icon_source, "icon") else icon_source

    def _sync_tree_expand_toggle_button(self, *_args) -> None:
        expanded = self.tree.all_expandable_items_expanded()
        icon_source = _TREE_EXPAND_ALL_ICON if expanded else _TREE_COLLAPSE_ALL_ICON
        tooltip = "全部折叠" if expanded else "全部展开"
        self.tree_expand_toggle_btn.setIcon(self._tool_button_icon(icon_source))
        self.tree_expand_toggle_btn.setToolTip(tooltip)

    def _toggle_tree_expansion(self) -> None:
        if self.tree.all_expandable_items_expanded():
            self.tree.collapse_all_items()
        else:
            self.tree.expand_all_items()
        self._sync_tree_expand_toggle_button()


class MainWindow(FluentWindow):
    """ALine 主窗口 — 统一共享项目树"""

    def __init__(self):
        super().__init__()
        self.app_context = AppContext()
        self._tree_action_dispatcher = ProjectTreeActionDispatcher(
            command_handler=self._handle_tree_app_command,
            project_id_getter=lambda: project_manager.current_project_id,
        )
        self._page_tree_focus_mode_enabled = is_page_tree_focus_mode_enabled()
        self._view_state = MainWindowViewState(tree_panel_width=_TREE_PANEL_DEFAULT_WIDTH)
        self._shortcut_bindings = ShortcutBindingSet()
        self._setup_ui()
        self._setup_shortcuts()
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
        self.addSubInterface(self.data_page,     _DATA_PAGE_NAV_ICON, "数据管理", NavigationItemPosition.TOP)
        self.addSubInterface(self.chart_page,    FIF.PIE_SINGLE,      "数据可视化",   NavigationItemPosition.TOP)
        self.addSubInterface(self.process_page,  FIF.DEVELOPER_TOOLS, "数据处理", NavigationItemPosition.TOP)
        self.addSubInterface(self.analysis_page, FIF.SEARCH,          "数据分析", NavigationItemPosition.TOP)
        self.addSubInterface(self.digitize_page, _DIGITIZE_PAGE_NAV_ICON, "图片数字化", NavigationItemPosition.TOP)
        self.addSubInterface(self.settings_page, FIF.SETTING,         "设置",    NavigationItemPosition.BOTTOM)

        self._tree_toggle_nav_btn = NavigationToolButton(FIF.MENU, self)
        self.navigationInterface.insertWidget(
            0,
            routeKey="toggleProjectTree",
            widget=self._tree_toggle_nav_btn,
            onClick=self._toggle_tree_panel,
            position=NavigationItemPosition.TOP,
            tooltip="隐藏项目树",
        )

        # 永久 COMPACT（图标）模式
        self.navigationInterface.panel.setMenuButtonVisible(False)
        self.navigationInterface.panel.setReturnButtonVisible(False)
        self.navigationInterface.panel.setMinimumExpandWidth(99999)

        # ── 注入共享树面板 ─────────────────────────────────────
        self._tree_panel = _SharedTreePanel(self)
        self._tree_panel.hide()
        self.widgetLayout.removeWidget(self.stackedWidget)
        self._tree_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._tree_splitter.setHandleWidth(6)
        self._tree_splitter.addWidget(self._tree_panel)
        self._tree_splitter.addWidget(self.stackedWidget)
        self._tree_splitter.setCollapsible(0, True)
        self._tree_splitter.setCollapsible(1, False)
        self._tree_splitter.setStretchFactor(0, 0)
        self._tree_splitter.setStretchFactor(1, 1)
        self._tree_splitter.splitterMoved.connect(self._remember_tree_panel_width)
        self.widgetLayout.insertWidget(0, self._tree_splitter)
        self._apply_tree_panel_width(True)
        self._tree_panel.new_project_btn.clicked.connect(self._create_project_from_panel)
        self._tree_panel.open_project_btn.clicked.connect(self._open_project_from_panel)
        self._tree_panel.save_project_btn.clicked.connect(self._save_current_project_from_panel)
        self._tree_panel.close_project_btn.clicked.connect(self._close_current_project_from_panel)
        self._tree_panel.tree_manage_btn.clicked.connect(self._open_project_tree_manage_dialog)
        self._tree_panel.extension_toggle_btn.clicked.connect(self._toggle_current_page_extension_panel)

        self._set_shared_extension_panel_visible(False)
        self._update_tree_panel_visibility(self.home_page)

    def _setup_theme_watcher(self):
        theme_combo = self.settings_page.theme_combo
        if theme_combo is not None:
            theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        shortcut_manager.shortcuts_changed.connect(self.apply_shortcuts)
        self.settings_page.tree_display_mode_changed.connect(self._tree_panel.tree.set_name_display_mode)
        self.settings_page.page_tree_focus_mode_changed.connect(self._on_page_tree_focus_mode_changed)

    def _tree_kinds_for_interface(self, interface) -> list[str]:
        obj_name = getattr(interface, "objectName", lambda: "")()
        if self._page_tree_focus_mode_enabled:
            if obj_name == "dataPage":
                return list(_PAGE_TREE_KINDS.get(obj_name, []))
            return []
        return list(_PAGE_TREE_KINDS.get(obj_name, []))

    def _tree_focus_groups_for_interface(self, interface) -> list[str]:
        if not self._page_tree_focus_mode_enabled:
            return []
        obj_name = getattr(interface, "objectName", lambda: "")()
        return list(_PAGE_TREE_FOCUS_KINDS.get(obj_name, []))

    def _on_page_tree_focus_mode_changed(self, enabled: bool) -> None:
        self._page_tree_focus_mode_enabled = bool(enabled)
        self._update_tree_panel_visibility(self.stackedWidget.currentWidget())

    def _setup_shortcuts(self) -> None:
        context = Qt.ShortcutContext.WindowShortcut
        self._shortcut_bindings.bind("new_project", self, self._create_project_from_panel, context=context)
        self._shortcut_bindings.bind("open_project", self, self._open_project_from_panel, context=context)
        self._shortcut_bindings.bind("save", self, self._save_current_project_from_panel, context=context)
        self._shortcut_bindings.bind("close_project", self, self._close_current_project_from_panel, context=context)
        self._shortcut_bindings.bind("toggle_project_tree", self, self._toggle_tree_panel, context=context)
        self._shortcut_bindings.bind("toggle_extension_panel", self, self._toggle_current_page_extension_panel, context=context)
        self._shortcut_bindings.bind("go_home", self, lambda: self.switchTo(self.home_page), context=context)
        self._shortcut_bindings.bind("go_data_page", self, lambda: self.switchTo(self.data_page), context=context)
        self._shortcut_bindings.bind("go_chart_page", self, lambda: self.switchTo(self.chart_page), context=context)
        self._shortcut_bindings.bind("go_process_page", self, lambda: self.switchTo(self.process_page), context=context)
        self._shortcut_bindings.bind("go_analysis_page", self, lambda: self.switchTo(self.analysis_page), context=context)
        self._shortcut_bindings.bind("go_digitize_page", self, lambda: self.switchTo(self.digitize_page), context=context)
        self._shortcut_bindings.bind("go_settings_page", self, lambda: self.switchTo(self.settings_page), context=context)
        self._shortcut_bindings.bind("data_add_dataset", self, self.data_page.add_dataset_from_shell, context=context)
        self._shortcut_bindings.bind("data_import_file", self, self.data_page.import_file_from_shell, context=context)

    def apply_shortcuts(self) -> None:
        self._shortcut_bindings.apply()
        for page in (self.data_page, self.chart_page, self.process_page, self.analysis_page, self.digitize_page):
            if hasattr(page, "apply_shortcuts"):
                page.apply_shortcuts()

    def _setup_project_signals(self):
        self.home_page.project_created.connect(self._on_project_created)
        self.home_page.project_opened.connect(self._on_project_opened)
        self.home_page.quick_start_requested.connect(self._on_home_quick_start_requested)
        self.settings_page.replay_onboarding_requested.connect(self._replay_home_onboarding)
        self.settings_page.extensions_reloaded.connect(self._on_extensions_reloaded)
        self.settings_page.project_modified.connect(self._on_project_modified)
        self.settings_page.assets_modified.connect(self._tree_panel.tree.refresh)
        self.digitize_page.project_modified.connect(self._on_project_modified)
        self.digitize_page.project_saved.connect(self._update_window_title)
        self.chart_page.project_modified.connect(self._on_project_modified)
        self.chart_page.extensions_reloaded.connect(self._on_extensions_reloaded)
        self.process_page.extensions_reloaded.connect(self._on_extensions_reloaded)
        self.analysis_page.extensions_reloaded.connect(self._on_extensions_reloaded)

        # 数据管理页信号
        self.data_page.project_modified.connect(self._on_project_modified)
        self.data_page.send_to_visualize.connect(self._on_send_to_visualize)
        self.data_page.send_to_process.connect(self._on_send_to_process)

        # 共享树信号路由
        self._tree_panel.tree.node_selected.connect(self._dispatch_tree_node_selected)
        self._tree_panel.tree.node_activated.connect(self._dispatch_tree_node_activated)
        self._tree_panel.tree.project_modified.connect(self._on_project_modified)
        self._tree_panel.tree.project_modified.connect(self._tree_panel.tree.refresh)

        # 页面修改后刷新树
        for page in [self.chart_page, self.digitize_page, self.data_page, self.process_page, self.analysis_page, self.settings_page]:
            page.project_modified.connect(self._tree_panel.tree.refresh)
        self.chart_page.assets_modified.connect(self._tree_panel.tree.refresh)
        self.process_page.assets_modified.connect(self._tree_panel.tree.refresh)
        self.analysis_page.assets_modified.connect(self._tree_panel.tree.refresh)

    def _on_extensions_reloaded(self) -> None:
        from core.extension_api import extension_registry

        self.home_page.refresh_extension_summary()
        self.process_page.refresh_processing_extensions()
        self.analysis_page.refresh_analysis_type_choices()

        plot_types = {extension.type for extension in extension_registry.list_plot()}
        self.chart_page.handle_extension_runtime_reload(plot_types)
        self._tree_panel.tree.refresh()

    # ─────────────────────────────────────────────────────────
    # FluentWindow.switchTo 覆盖
    # ─────────────────────────────────────────────────────────

    def switchTo(self, interface, isAutoScroll: bool = False) -> None:
        super().switchTo(interface)
        self._update_tree_panel_visibility(interface)

    def _tree_available_for_interface(self, interface) -> bool:
        return bool(self._tree_kinds_for_interface(interface) or self._tree_focus_groups_for_interface(interface))

    def _page_supports_extension_panel(self, interface) -> bool:
        if interface is None or not hasattr(interface, "supports_extension_panel_toggle"):
            return False
        return bool(interface.supports_extension_panel_toggle())

    def _extension_panel_pages(self) -> list[_ExtensionPanelPage]:
        pages: list[_ExtensionPanelPage] = []
        for interface in (
            self.chart_page,
            self.process_page,
            self.analysis_page,
            self.digitize_page,
        ):
            if self._page_supports_extension_panel(interface):
                pages.append(cast(_ExtensionPanelPage, interface))
        return pages

    def _set_shared_extension_panel_visible(self, visible: bool) -> None:
        self._view_state.shared_extension_panel_visible = bool(visible)
        for extension_page in self._extension_panel_pages():
            extension_page.set_extension_panel_visible(self._view_state.shared_extension_panel_visible)

    def _update_extension_panel_toggle_button(self, interface) -> None:
        button = self._tree_panel.extension_toggle_btn
        show_button = self._tree_available_for_interface(interface)
        supported = self._page_supports_extension_panel(interface)
        button.setVisible(show_button)
        button.setEnabled(supported)
        if not show_button:
            return
        if not supported:
            button.setIcon(_EXTENSION_PANEL_SHOW_ICON.icon())
            button.setToolTip("当前页面没有扩展面板")
            return
        extension_page = cast(_ExtensionPanelPage, interface)
        if bool(extension_page.is_extension_panel_visible()) != self._view_state.shared_extension_panel_visible:
            extension_page.set_extension_panel_visible(self._view_state.shared_extension_panel_visible)
        visible = self._view_state.shared_extension_panel_visible
        button.setIcon((_EXTENSION_PANEL_HIDE_ICON if visible else _EXTENSION_PANEL_SHOW_ICON).icon())
        button.setToolTip("隐藏扩展面板" if visible else "显示扩展面板")

    def _update_tree_panel_visibility(self, interface) -> None:
        kinds = self._tree_kinds_for_interface(interface)
        focus_groups = self._tree_focus_groups_for_interface(interface)
        show = bool(kinds or focus_groups)
        tree_visible = show and not self._view_state.tree_panel_user_hidden
        self._tree_panel.setVisible(tree_visible)
        self._apply_tree_panel_width(tree_visible)
        self._tree_toggle_nav_btn.setEnabled(show)
        self._tree_toggle_nav_btn.setToolTip("显示项目树" if self._view_state.tree_panel_user_hidden else "隐藏项目树")
        self._update_extension_panel_toggle_button(interface)
        if show:
            self._tree_panel.tree.set_filter_kinds(kinds, focus_root_group_types=focus_groups)

    def _toggle_tree_panel(self) -> None:
        current_page = self.stackedWidget.currentWidget()
        if not self._tree_available_for_interface(current_page):
            return
        self._view_state.tree_panel_user_hidden = not self._view_state.tree_panel_user_hidden
        self._update_tree_panel_visibility(current_page)

    def _toggle_current_page_extension_panel(self) -> None:
        current_page = self.stackedWidget.currentWidget()
        if not self._page_supports_extension_panel(current_page):
            return
        self._set_shared_extension_panel_visible(not self._view_state.shared_extension_panel_visible)
        self._update_extension_panel_toggle_button(current_page)

    def _open_project_tree_manage_dialog(self) -> None:
        dialog = ProjectTreeManageDialog(self)
        dialog.project_modified.connect(self._on_project_modified)
        dialog.project_modified.connect(self._tree_panel.tree.refresh)
        dialog.exec()

    def _remember_tree_panel_width(self, *_args) -> None:
        if not self._tree_panel.isVisible():
            return
        width = self._tree_panel.width()
        if width <= 0:
            return
        self._view_state.tree_panel_width = max(_TREE_PANEL_MIN_WIDTH, min(_TREE_PANEL_MAX_WIDTH, width))

    def _apply_tree_panel_width(self, visible: bool) -> None:
        total_width = max(self.width(), self._view_state.tree_panel_width + 1)
        if visible:
            panel_width = max(_TREE_PANEL_MIN_WIDTH, min(_TREE_PANEL_MAX_WIDTH, self._view_state.tree_panel_width))
            self._tree_splitter.setSizes([panel_width, max(1, total_width - panel_width)])
            return
        self._remember_tree_panel_width()
        self._tree_splitter.setSizes([0, total_width])

    # ─────────────────────────────────────────────────────────
    # 项目生命周期
    # ─────────────────────────────────────────────────────────

    def _on_project_created(self, name: str):
        p = project_manager.current_project
        if p is not None:
            project_manager.migrate_to_v2(p)
            project_manager.migrate_to_v3(p)
        self._update_window_title()
        self.digitize_page.refresh_project_tree()
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
        self.digitize_page.refresh_project_tree()
        self.data_page.refresh()
        self._tree_panel.tree.refresh()
        self.settings_page.refresh_templates()
        self.switchTo(self.data_page)

    def _on_project_modified(self):
        if project_manager.current_project:
            project_manager.current_project.is_modified = True
        self._update_window_title()

    def _on_home_quick_start_requested(self, destination: str) -> None:
        destination_map = {
            "data": self.data_page,
            "process": self.process_page,
            "analysis": self.analysis_page,
        }
        page = destination_map.get(destination)
        if page is not None:
            self.switchTo(page)

    def _replay_home_onboarding(self) -> None:
        reset_all_onboarding_progress()
        self.switchTo(self.home_page)
        QTimer.singleShot(0, lambda: self.home_page.start_onboarding(force=True))

    def _create_project_from_panel(self) -> None:
        name, ok = TextInputDialog.get_text(self, "新建项目", placeholder="请输入项目名称")
        if not ok:
            return
        clean_name = name.strip()
        if not clean_name:
            return
        base_dir = QFileDialog.getExistingDirectory(self, "选择项目保存目录", "")
        if not base_dir:
            return
        try:
            project_manager.create_new(clean_name, parent_dir=base_dir, create_structure=True)
        except Exception as exc:
            show_error(self, "错误", f"创建项目失败:\n{exc}")
            return
        self._on_project_created(clean_name)

    def _open_project_from_panel(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开项目",
            "",
            "ALine 项目 (*.aline);;所有文件 (*)",
        )
        if not file_path:
            return
        try:
            project_manager.open(file_path)
        except Exception as exc:
            show_error(self, "错误", f"无法打开项目:\n{exc}")
            return
        self._on_project_opened(file_path)

    def _save_current_project_from_panel(self) -> bool:
        project = project_manager.current_project
        if project is None:
            show_warning(self, "提示", "请先打开项目")
            return False

        file_path = project.file_path
        if file_path is None:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存项目",
                f"{project.name}.aline",
                "ALine 项目 (*.aline)",
            )
        if not file_path:
            return False

        try:
            project_manager.save(file_path)
        except Exception as exc:
            show_error(self, "保存失败", exc)
            return False

        self.data_page.refresh()
        self.digitize_page.refresh_project_tree()
        self._tree_panel.tree.refresh()
        self.settings_page.refresh_templates()
        self._update_window_title()
        show_success(self, "已保存", file_path)
        return True

    def _close_current_project_from_panel(self) -> None:
        project = project_manager.current_project
        if project is None:
            show_warning(self, "提示", "请先打开项目")
            return

        if project.is_modified:
            dlg = MessageBox("项目已修改", "当前项目有未保存的更改，是否保存？", self)
            dlg.yesButton.setText("保存")
            dlg.cancelButton.setText("不保存")
            if dlg.exec() and not self._save_current_project_from_panel():
                return

        project_manager.close_current_project()
        self.data_page.refresh()
        self.digitize_page.clear_current_image()
        self.digitize_page.refresh_project_tree()
        self._tree_panel.tree.refresh()
        self.settings_page.refresh_templates()
        self._update_window_title()
        if project_manager.current_project is None:
            self.switchTo(self.home_page)

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

    def _dispatch_tree_node_selected(self, kind: str, node_id: str) -> None:
        self._tree_action_dispatcher.dispatch_selected(kind, node_id)

    def _dispatch_tree_node_activated(self, kind: str, node_id: str) -> None:
        self._tree_action_dispatcher.dispatch_activated(kind, node_id)

    def _handle_tree_app_command(self, command: AppCommand) -> None:
        if command.command_type != AppCommandType.TREE or command.tree_command is None:
            return
        tree_command = command.tree_command
        if tree_command.command_type.value == "select":
            self._on_tree_node_selected_command(tree_command)
            return
        if tree_command.command_type.value == "activate":
            self._on_tree_node_activated_command(tree_command)

    def _dispatch_activation_to_current_page(self, kind: str, node_id: str) -> bool:
        page = self.stackedWidget.currentWidget()
        if kind == "data_file" and page is not self.process_page:
            return False
        if page is self.digitize_page and kind == "image_work":
            if hasattr(self.digitize_page, 'load_image_by_id'):
                self.digitize_page.load_image_by_id(node_id)
                return True
            return False

        if hasattr(page, 'on_tree_node_activated'):
            cast(_TreeActivatablePage, page).on_tree_node_activated(kind, node_id)
            return True
        if hasattr(page, 'on_tree_node_selected'):
            cast(_TreeSelectablePage, page).on_tree_node_selected(kind, node_id)
            return True
        return False

    def _on_tree_node_activated_command(self, tree_command: TreeCommand) -> None:
        """双击节点 → 在当前页面执行主动作；显式发送动作才跨页。"""
        kind = tree_command.node.kind
        node_id = tree_command.node.node_id
        self._update_window_title()
        if kind == "project":
            self._tree_panel.tree.refresh()
            self.settings_page.refresh_templates()
            return
        if kind == "image_work":
            self.switchTo(self.digitize_page)
            if hasattr(self.digitize_page, 'load_image_by_id'):
                self.digitize_page.load_image_by_id(node_id)
            return
        if kind == "image_work_add_curve":
            self.switchTo(self.digitize_page)
            if hasattr(self.digitize_page, 'load_image_by_id'):
                self.digitize_page.load_image_by_id(node_id)
            self.digitize_page.add_curve_from_shell()
            return
        if kind == "curve_export_to_data_file":
            self.switchTo(self.digitize_page)
            if hasattr(self.digitize_page, 'load_curve_by_id'):
                self.digitize_page.load_curve_by_id(node_id)
            self.digitize_page.export_current_curve_to_data_file()
            return
        if kind in ("data_file", "series", "curve"):
            if self._dispatch_activation_to_current_page(kind, node_id):
                return
        if kind in ("source_file", "source_file_to_data"):
            self.switchTo(self.data_page)
            self.data_page.on_tree_node_selected("source_file", node_id)
            if kind == "source_file_to_data":
                self.data_page.import_current_source_file_to_dataset()
            return
        if kind == "source_file_to_digitize":
            source_node = project_manager.get_node_by_id(node_id)
            source_path = ""
            source_name = ""
            if source_node is not None and getattr(source_node, "kind", None) == "source_file":
                source_path = project_manager.get_source_file_path(getattr(source_node, "source_file_id", ""))
                source_name = getattr(source_node, "name", "")
            if source_path:
                self.switchTo(self.digitize_page)
                self.digitize_page.import_source_image(source_path, name=source_name)
            return
        if kind == "pipeline":
            if hasattr(self.process_page, 'load_pipeline'):
                self.process_page.load_pipeline(node_id)
            self.switchTo(self.process_page)
        elif kind == "global_pipeline":
            if hasattr(self.process_page, 'load_pipeline'):
                self.process_page.load_pipeline(node_id)
            self.switchTo(self.process_page)
        elif kind == "global_figure_template":
            if hasattr(self.chart_page, 'load_template'):
                self.chart_page.load_template(node_id)
            self.switchTo(self.chart_page)
        elif kind in ("figure_template",):
            if hasattr(self.chart_page, 'load_template'):
                self.chart_page.load_template(node_id)
            self.switchTo(self.chart_page)
        elif kind == "global_curve_style_template":
            self.switchTo(self.chart_page)
            if hasattr(self.chart_page, 'load_curve_style_template'):
                self.chart_page.load_curve_style_template(node_id)
        elif kind in ("global_plot_style", "global_plot_theme"):
            self.switchTo(self.chart_page)
            if hasattr(self.chart_page, 'load_plot_style'):
                self.chart_page.load_plot_style(node_id)
        elif kind == "global_report_template":
            self.switchTo(self.analysis_page)
            if hasattr(self.analysis_page, 'load_report_template'):
                self.analysis_page.load_report_template(node_id)
        elif kind == "global_extension_config":
            self._open_extension_config_node(node_id)
        elif kind == "report_template":
            self.switchTo(self.analysis_page)
            if hasattr(self.analysis_page, 'load_report_template'):
                self.analysis_page.load_report_template(node_id)
        elif kind == "analysis_result":
            self.switchTo(self.analysis_page)
            if hasattr(self.analysis_page, 'load_analysis_result'):
                self.analysis_page.load_analysis_result(node_id)
        elif kind in ("data_file_to_chart", "image_work_to_chart",
                       "series_to_chart", "curve_to_chart", "picture_to_chart", "picture"):
            self.switchTo(self.chart_page)
            if hasattr(self.chart_page, 'on_tree_node_activated'):
                self.chart_page.on_tree_node_activated(kind, node_id)
        elif kind in ("data_file_to_process", "series_to_process", "curve_to_process"):
            self.switchTo(self.process_page)
            if hasattr(self.process_page, 'on_tree_node_activated'):
                self.process_page.on_tree_node_activated(kind, node_id)
        elif kind in ("data_file_to_analysis", "series_to_analysis", "curve_to_analysis"):
            self.switchTo(self.analysis_page)
            if hasattr(self.analysis_page, 'on_tree_node_activated'):
                self.analysis_page.on_tree_node_activated(kind, node_id)

    def _open_extension_config_node(self, config_id: str) -> bool:
        config_item = global_assets.get_extension_config(config_id)
        if config_item is None:
            return False
        self.switchTo(self.data_page)
        if hasattr(self.data_page, "open_extension_config"):
            return bool(self.data_page.open_extension_config(config_id))
        self.data_page.on_tree_node_selected("global_extension_config", config_id)
        return True

    def _on_tree_node_selected_command(self, tree_command: TreeCommand) -> None:
        """单击节点 → 通知当前页面。"""
        kind = tree_command.node.kind
        node_id = tree_command.node.node_id
        self._update_window_title()
        if kind == "project":
            self._tree_panel.tree.refresh()
            self.settings_page.refresh_templates()
            return
        page = self.stackedWidget.currentWidget()
        if hasattr(page, 'on_tree_node_selected'):
            cast(_TreeSelectablePage, page).on_tree_node_selected(kind, node_id)

    # ─────────────────────────────────────────────────────────
    # 数据页路由（保留）
    # ─────────────────────────────────────────────────────────

    def _on_send_to_visualize(self, data_type: str, obj_id: str):
        self.switchTo(self.chart_page)
        if data_type == "picture" and hasattr(self.chart_page, "on_tree_node_activated"):
            self.chart_page.on_tree_node_activated("picture", obj_id)
            return
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
        self.settings_page.update_theme_colors()
        self.digitize_page.update_theme_colors()
        self.chart_page.request_redraw()
        self.data_page.update_theme()
        self.process_page.update_theme()
        self.analysis_page.update_theme()
