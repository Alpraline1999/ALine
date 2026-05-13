from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional, cast

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy, QSplitter, QFileDialog, QTreeWidgetItem, QAbstractItemView, QTableWidgetItem, QHeaderView
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QFont, QColor
from qfluentwidgets import (CardWidget, ToolButton, ToggleToolButton, TogglePushButton,
    LineEdit, SpinBox, ColorPickerButton, BodyLabel,
    PushButton as FPushButton, TableWidget, ComboBox, TreeWidget,
    Slider, TabCloseButtonDisplayMode, PrimaryPushButton,
    MessageBox, InfoBar, InfoBarPosition, RoundMenu,
    ToolTipFilter, ToolTipPosition, TeachingTipTailPosition, Action, FluentIcon as FIF)

from core.exporter import Exporter
from ui.theme import WORKBENCH_TOOL_PANEL_WIDTH, border_color, text_color, placeholder_color, make_section_label, make_hsep, make_vsep
from ui.widgets import ImageViewer
from ui.widgets.extension_panel import ExtensionConfigPanel
from ui.widgets.navigation_stack import SegmentedStackWidget
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController
from ui.dialogs import CalibrationDialog, CoordTypeDialog, PolarCalibrationDialog
from ui.dialogs.project_close_dialog import ProjectCloseDecision, confirm_unsaved_project_close
from ui.dialogs.export_flow import DataCreateTargetOption, choose_curve_file_export_plan, choose_data_export_plan, curve_export_file_filter
from ui.pages.save_export_coordinator import SaveExportCoordinator
from core.extension_api import build_extension_entry, extension_registry, reload_configured_extensions
from core.shortcut_manager import ShortcutBindingSet
from core.app_context import get_app_context
from core.extension_runtime import invoke_digitize_extension_handler
from extensions.digitize.color_detect import COLOR_DIGITIZE_EXTENSION_TYPE
from extensions.digitize.shape_detect import SHAPE_DIGITIZE_EXTENSION_TYPE
from models.schemas import CalibrationData, DataFile, DataSeries
from app.workspaces.digitize_workspace import DigitizeWorkspaceController, DigitizeWorkspaceState
from processing.extension_tools import line_xy
from ui.page_view_state import DigitizePageViewState


class _PMProxy:
    __slots__ = ()

    def __getattr__(self, name):
        pm = get_app_context().project_manager
        if pm is None:
            import core.project_manager as _pm_module
            pm = _pm_module.project_manager
        return getattr(pm, name)


project_manager = _PMProxy()
from .page_shell_helpers import ExtensionPanelShellMixin, sync_vertical_splitter_sizes
from .digitize_page_support import _InputDialog, _SUPPORTED_SOURCE_IMAGE_SUFFIXES


def _build_digitize_auto_preview_points(
    invoke_handler: Callable[[Any, str, dict[str, Any]], Any],
    line_xy_fn: Callable[[Any], tuple[Any, Any]],
    handler: Any,
    image_path: str,
    params: dict[str, Any],
) -> list[tuple[Any, Any]]:
    result_line = invoke_handler(handler, image_path, params)
    xs, ys = line_xy_fn(result_line)
    return list(zip(list(xs), list(ys)))


class DigitizePage(ExtensionPanelShellMixin, QWidget):
    """工作区页面 - 主功能区"""

    project_modified = Signal()  # 项目修改信号
    project_saved = Signal()     # 项目保存信号（不触发 is_modified=True）
    current_project_changed = Signal(object)  # 当前项目切换信号
    current_image_changed = Signal(object)  # 当前图片切换信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workspace_state = DigitizeWorkspaceState()
        self._workspace_controller = DigitizeWorkspaceController(self._workspace_state)
        self._view_state = DigitizePageViewState()
        self._splitter = None
        self._left_panel = None
        self._right_panel = None
        self._right_tabs = None
        self._image_viewer: ImageViewer = cast(ImageViewer, None)
        self._tool_buttons = []
        self._project_tree: TreeWidget = cast(TreeWidget, None)
        self._current_project_item = None
        self._current_image_item = None
        self._current_image_id = None
        self._current_curve_id = None
        self._export_target_kind = None
        self._export_target_id = None
        self._last_export_suggestion = ""
        self._current_curve_points = []
        self._active_tool = None  # 当前激活的工具按钮
        self._hidden_curves = set()  # 隐藏的曲线ID集合
        # 撤销/重做系统
        self._undo_stack = []  #撤销栈
        self._redo_stack = []  #重做栈
        self._max_history = 50  #最大历史记录数
        self._is_undo_redo = False  #防止在撤销/重做中重复记录
        # 自动选点
        self._sampled_color = None  # 采样颜色 (QColor)
        self._auto_preview_points = []  # 自动检测预览点
        self._auto_detect_executor: ThreadPoolExecutor | None = None
        self._auto_detect_future = None
        self._auto_detect_job_id = 0
        # 图形识别模板
        self._shape_template: dict | None = None  # preprocess_region() 返回的字典
        self._auto_mode_type_ids: list[str] = []
        self._digitize_extension_controls: ExtensionConfigPanel = cast(ExtensionConfigPanel, None)
        self._pending_digitize_field_key: str | None = None
        self._pending_digitize_field_type: str | None = None
        # 表格排序
        self._sort_col = -1  # -1表示未排序
        self._sort_order = Qt.SortOrder.AscendingOrder
        self._shortcut_bindings = ShortcutBindingSet()
        self._save_export_coordinator = SaveExportCoordinator(
            get_children=project_manager.get_children,
            add_folder=project_manager.add_folder,
            notify_info=lambda title, msg: InfoBar.info(title, msg, parent=self, position=InfoBarPosition.TOP),
            notify_warning=lambda title, msg: InfoBar.warning(title, msg, parent=self, position=InfoBarPosition.TOP),
            notify_error=lambda title, msg: InfoBar.error(title, msg, parent=self, position=InfoBarPosition.TOP),
        )
        self.setup_ui()
        self._setup_viewer_signals()
        self._setup_shortcuts()
        # 初始化点大小
        self._image_viewer.set_point_size(self._point_size_spin.value())
        # 为所有带 tooltip 的 widget 安装 Fluent 样式过滤器
        self._install_tooltip_filters()
        self._onboarding_controller = PageOnboardingController(self, "digitize", self._digitize_onboarding_steps)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_right_panel_splitter_sizes)
        self._onboarding_controller.schedule_auto_start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._view_state.right_splitter_user_resized:
            QTimer.singleShot(0, self._sync_right_panel_splitter_sizes)

    def _sync_right_panel_splitter_sizes(self) -> None:
        sync_vertical_splitter_sizes(
            getattr(self, "_right_content_splitter", None),
            user_resized=self._view_state.right_splitter_user_resized,
            upper_ratio=0.35,
        )
        if self._right_content_splitter is not None and not self._view_state.right_splitter_user_resized:
            self._view_state.right_splitter_initialized = True

    def _set_tool_status(self, text: str = "") -> None:
        if not hasattr(self, "_status_label") or self._status_label is None:
            return
        self._status_label.setText(text or "工具状态栏")

    def _install_tooltip_filters(self):
        """为所有带 tooltip 的子 widget 安装 Fluent ToolTipFilter"""
        for w in self.findChildren(QWidget):
            if w.toolTip():
                w.installEventFilter(ToolTipFilter(w, 500, ToolTipPosition.TOP))

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(12, 12, 12, 12)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(4)

        center_panel = CardWidget(self)
        # center_panel.setFrameShape(QFrame.Shape.StyledPanel)
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(14, 14, 14, 14)
        center_layout.setSpacing(8)

        # 图片查看器上方工具栏（橡皮/清空/撤销/重做，靠右）
        self._top_viewer_toolbar = self._create_top_viewer_toolbar(center_panel)
        center_layout.addWidget(self._top_viewer_toolbar)

        self._image_viewer = ImageViewer(center_panel)
        self._image_viewer.image_loaded.connect(self._on_image_loaded)
        center_layout.addWidget(self._image_viewer, 1)

        # 图片查看器下方工具栏（颜色/形状/大小/平滑）
        self._viewer_toolbar = self._create_viewer_toolbar(center_panel)
        center_layout.addWidget(self._viewer_toolbar)

        # 状态栏：图片路径 + 鼠标坐标
        self._viewer_status_bar = self._create_viewer_status_bar(center_panel)
        center_layout.addWidget(self._viewer_status_bar)

        self._right_panel = self._create_right_panel()
        self._splitter.addWidget(self._right_panel)

        self._splitter.addWidget(center_panel)

        self._extension_panel = ExtensionConfigPanel("数字化扩展", "应用扩展", self, mode="help_only", framed=True)
        self._extension_panel.set_status_context("digitize", "数字化扩展")
        self._extension_panel.setMinimumWidth(self._view_state.extension_panel_width)
        self._extension_panel.setMaximumWidth(self._view_state.extension_panel_width)
        self._splitter.addWidget(self._extension_panel)

        self._splitter.setSizes([320, 760, 0])
        self._splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._splitter)
        self._refresh_digitize_extension_panel()
        self.set_extension_panel_visible(self._view_state.extension_panel_visible)

    def _extension_panel_splitter(self) -> QSplitter | None:
        return getattr(self, "_splitter", None)

    def _extension_panel_visible_sizes(self) -> tuple[int, int, int]:
        return (
            320,
            max(self.width() - 320 - self._view_state.extension_panel_width - 24, 640),
            self._view_state.extension_panel_width,
        )

    def _extension_panel_hidden_sizes(self) -> tuple[int, int, int]:
        return (320, max(self.width() - 320 - 12, 760), 0)

    def _setup_viewer_signals(self):
        self._image_viewer.calibration_complete.connect(self._on_calibration_complete)
        self._image_viewer.curve_point_added.connect(self._on_curve_point_added)
        self._image_viewer.calibration_step.connect(self._on_calibration_step)
        self._image_viewer.calibration_nudge.connect(self._on_calibration_nudge)
        self._image_viewer.eraser_point.connect(self._on_eraser_point)
        self._image_viewer.toggle_eraser_mode.connect(self._on_toggle_eraser_mode)
        self._image_viewer.mask_changed.connect(self._on_mask_changed)
        self._image_viewer.mask_about_to_add.connect(self._on_mask_about_to_add)
        self._image_viewer.color_picked.connect(self._on_color_picked)
        self._image_viewer.file_dropped.connect(self._on_image_file_dropped)
        self._image_viewer.assisted_region_selected.connect(self._on_assisted_region)
        self._image_viewer.crop_region_selected.connect(self._on_crop_region_selected)
        self._image_viewer.curve_point_moved.connect(self._on_curve_point_moved)
        self._image_viewer.mouse_moved.connect(self._on_viewer_mouse_moved)

    def _setup_shortcuts(self):
        """设置键盘快捷键（可在设置页自定义）"""
        context = Qt.ShortcutContext.WidgetWithChildrenShortcut
        self._shortcut_bindings.bind("undo", self, self._undo, context=context)
        self._shortcut_bindings.bind("redo", self, self._redo, context=context)
        self._shortcut_bindings.bind("add_image", self, self._on_add_image, context=context)
        self._shortcut_bindings.bind("add_curve", self, self._on_add_curve, context=context)
        self._shortcut_bindings.bind("extract", self, lambda: self._on_tool_clicked("extract"), context=context)
        self._shortcut_bindings.bind("calibrate", self, lambda: self._on_tool_clicked("calibrate"), context=context)
        self._shortcut_bindings.bind("eraser", self, lambda: self._on_tool_clicked("eraser"), context=context)
        self._shortcut_bindings.bind("auto_detect", self, self._on_auto_detect, context=context)
        self._shortcut_bindings.bind("apply_auto", self, self._on_apply_auto_points, context=context)
        self._shortcut_bindings.bind("clear_points", self, self._on_clear_all_points, context=context)
        self._shortcut_bindings.bind("clear_masks", self, self._on_clear_masks, context=context)
        self._shortcut_bindings.bind("escape_tool", self, self._on_escape_tool, context=context)
        self._shortcut_bindings.bind("zoom_in", self._image_viewer, self._image_viewer.zoom_in, context=context)
        self._shortcut_bindings.bind("zoom_out", self._image_viewer, self._image_viewer.zoom_out, context=context)
        self._shortcut_bindings.bind("zoom_fit", self._image_viewer, self._image_viewer.fit_to_window, context=context)
        self._shortcut_bindings.bind("delete_rows", self._curve_table, self._delete_selected_table_rows, context=context)

    def apply_shortcuts(self):
        """由设置页调用，用新配置刷新所有快捷键绑定"""
        self._shortcut_bindings.apply()

    def start_onboarding(self, force: bool = False) -> None:
        self._onboarding_controller.start(force=force)

    def _digitize_onboarding_steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                lambda: self._image_viewer,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "中心画布是主工作区",
                "校准、取点、擦除和自动识别都直接作用在这里。",
            ),
            OnboardingStep(
                lambda: self._calibrate_btn,
                TeachingTipTailPosition.BOTTOM,
                "先做校准",
                "先建立像素到真实坐标的映射，后续取点才有数值意义。",
            ),
            OnboardingStep(
                lambda: self._auto_detect_btn,
                TeachingTipTailPosition.BOTTOM,
                "轨迹清晰时先自动识别",
                "自动取点后再做少量手动修正，效率更高。",
            ),
            OnboardingStep(
                lambda: self._right_tabs,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "右侧负责整理与导出",
                "取点结果和数据导出都收在右侧标签页。",
            ),
        ]

    def _create_left_panel(self) -> CardWidget:
        panel = CardWidget(self)
        panel.setFixedWidth(260)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        toolbar_widget = QWidget(panel)
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(2)

        self._new_project_btn = ToolButton(FIF.ADD, toolbar_widget)
        self._new_project_btn.setToolTip("新建项目")
        self._new_project_btn.clicked.connect(self._on_new_project)
        toolbar_layout.addWidget(self._new_project_btn)

        self._open_project_btn = ToolButton(FIF.FOLDER, toolbar_widget)
        self._open_project_btn.setToolTip("打开项目")
        self._open_project_btn.clicked.connect(self._on_open_project)
        toolbar_layout.addWidget(self._open_project_btn)

        self._save_project_btn = ToolButton(FIF.SAVE, toolbar_widget)
        self._save_project_btn.setToolTip("保存项目 (Ctrl+S)")
        self._save_project_btn.clicked.connect(self._on_save_project)
        toolbar_layout.addWidget(self._save_project_btn)

        self._close_project_btn = ToolButton(FIF.CLOSE, toolbar_widget)
        self._close_project_btn.setToolTip("关闭项目")
        self._close_project_btn.clicked.connect(self._on_close_project)
        toolbar_layout.addWidget(self._close_project_btn)

        line = QFrame(toolbar_widget)
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        line.setStyleSheet(f"background-color: {self._border_color()};")
        toolbar_layout.addWidget(line)

        self._tree_add_image_btn = ToolButton(FIF.IMAGE_EXPORT, toolbar_widget)
        self._tree_add_image_btn.setToolTip("添加图片到当前项目")
        self._tree_add_image_btn.clicked.connect(self._on_add_image)
        toolbar_layout.addWidget(self._tree_add_image_btn)

        self._tree_add_curve_btn = ToolButton(FIF.ADD_TO, toolbar_widget)
        self._tree_add_curve_btn.setToolTip("添加新曲线到选中图片")
        self._tree_add_curve_btn.clicked.connect(self._on_add_curve)
        toolbar_layout.addWidget(self._tree_add_curve_btn)

        toolbar_layout.addStretch()
        layout.addWidget(toolbar_widget)

        self._shared_tree_hint = BodyLabel("图片选择与导出目标请使用共享项目树；此处不再作为第二入口。", panel)
        self._shared_tree_hint.setWordWrap(True)
        self._shared_tree_hint.hide()
        layout.addWidget(self._shared_tree_hint)

        self._project_tree = TreeWidget(panel)
        self._project_tree.setHeaderHidden(True)
        self._project_tree.setIndentation(15)
        self._project_tree.setFont(QFont("Microsoft YaHei", 10))
        self._project_tree.setIconSize(QSize(20, 20))
        self._project_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._project_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self._project_tree.itemClicked.connect(self._on_tree_item_clicked)
        self._project_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        # 支持图片节点拖放到其他项目
        self._project_tree.setDragEnabled(True)
        self._project_tree.setAcceptDrops(True)
        self._project_tree.setDropIndicatorShown(True)
        self._project_tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._project_tree.dropEvent = self._on_tree_drop_event
        self._refresh_project_tree()
        self._project_tree.hide()
        layout.addWidget(self._project_tree)

        return panel

    def _create_right_panel(self) -> CardWidget:
        panel = CardWidget(self)
        self._tool_panel = panel
        panel.setFixedWidth(WORKBENCH_TOOL_PANEL_WIDTH)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(6)
        self._add_image_btn = FPushButton("导入图片", panel)
        self._add_image_btn.setIcon(FIF.DOWNLOAD)
        self._add_image_btn.setToolTip("导入图片到当前项目")
        self._add_image_btn.clicked.connect(self._on_add_image)
        actions_row.addWidget(self._add_image_btn)

        self._add_curve_btn = FPushButton("新增曲线", panel)
        self._add_curve_btn.setIcon(FIF.ADD_TO)
        self._add_curve_btn.setToolTip("添加新曲线到当前图片")
        self._add_curve_btn.clicked.connect(self._on_add_curve)
        actions_row.addWidget(self._add_curve_btn)
        actions_row.addStretch()
        layout.addLayout(actions_row)

        self._curve_panel_title = make_section_label("曲线数据", panel)
        layout.addWidget(self._curve_panel_title)

        self._right_content_splitter = QSplitter(Qt.Orientation.Vertical, panel)
        self._right_content_splitter.setHandleWidth(6)
        self._right_content_splitter.splitterMoved.connect(self._on_right_content_splitter_moved)

        curve_section = QWidget(self._right_content_splitter)
        curve_section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        curve_layout = QVBoxLayout(curve_section)
        curve_layout.setContentsMargins(0, 0, 0, 0)
        curve_layout.setSpacing(8)

        self._curve_table = TableWidget(curve_section)
        self._curve_table.setColumnCount(2)
        self._curve_table.setHorizontalHeaderLabels(["X", "Y"])
        self._curve_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._curve_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._curve_table.horizontalHeader().setSectionsClickable(True)
        self._curve_table.horizontalHeader().sectionClicked.connect(self._on_header_sort)
        self._curve_table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self._curve_table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self._curve_table.setAlternatingRowColors(True)
        self._curve_table.setFont(QFont("Noto Sans", 9))
        self._curve_table.verticalHeader().setDefaultSectionSize(22)
        self._curve_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._curve_table.customContextMenuRequested.connect(self._on_curve_table_context_menu)
        curve_layout.addWidget(self._curve_table, 1)

        lower_section = QWidget(self._right_content_splitter)
        lower_section.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        lower_layout = QVBoxLayout(lower_section)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(8)

        line = QFrame(lower_section)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"color: {self._border_color()};")
        lower_layout.addWidget(line)

        # 功能区页面
        self._right_tabs = SegmentedStackWidget(lower_section, fill_width=True)
        self._right_tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._right_tabs.tabBar.setAddButtonVisible(False)
        self._right_tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        combined_tab = self._create_combined_tab()
        self._right_tabs.addTab(combined_tab, "图片选点")
        export_tab = self._create_export_tab()
        self._right_tabs.addTab(export_tab, "数据导出")
        lower_layout.addWidget(self._right_tabs, 1)

        # 提示标签
        self._status_label = BodyLabel("工具状态栏", lower_section)
        self._status_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px; padding: 2px 0;")
        self._status_label.setWordWrap(True)
        lower_layout.addWidget(self._status_label)

        self._right_content_splitter.addWidget(curve_section)
        self._right_content_splitter.addWidget(lower_section)
        self._right_content_splitter.setStretchFactor(0, 1)
        self._right_content_splitter.setStretchFactor(1, 1)
        self._right_content_splitter.setSizes([520, 520])
        layout.addWidget(self._right_content_splitter, 1)
        self._set_tool_status()

        return panel

    def _on_right_content_splitter_moved(self, _pos: int, _index: int) -> None:
        if self._view_state.right_splitter_initialized:
            self._view_state.right_splitter_user_resized = True

    def _create_top_viewer_toolbar(self, parent) -> QWidget:
        """创建图片查看器上方工具栏。"""
        bar = QWidget(parent)
        bar.setFixedHeight(36)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 2, 4, 2)
        bar_layout.setSpacing(2)

        # 橡皮擦
        self._eraser_btn = ToggleToolButton(FIF.ERASE_TOOL, bar)
        self._eraser_btn.setToolTip("橡皮擦 (E)")
        self._eraser_btn.setFixedSize(32, 32)
        self._eraser_btn.clicked.connect(lambda: self._on_tool_clicked("eraser"))
        bar_layout.addWidget(self._eraser_btn)

        bar_layout.addWidget(make_vsep(bar))

        # 清除所有点
        self._clear_points_btn = ToolButton(FIF.DELETE, bar)
        self._clear_points_btn.setToolTip("清除所有点")
        self._clear_points_btn.setFixedSize(32, 32)
        self._clear_points_btn.clicked.connect(self._on_clear_all_points)
        bar_layout.addWidget(self._clear_points_btn)

        # 撤销
        self._undo_btn = ToolButton(FIF.LEFT_ARROW, bar)
        self._undo_btn.setToolTip("撤销 (Ctrl+Z)")
        self._undo_btn.setFixedSize(32, 32)
        self._undo_btn.clicked.connect(self._undo)
        bar_layout.addWidget(self._undo_btn)

        # 重做
        self._redo_btn = ToolButton(FIF.RIGHT_ARROW, bar)
        self._redo_btn.setToolTip("重做 (Ctrl+Y)")
        self._redo_btn.setFixedSize(32, 32)
        self._redo_btn.clicked.connect(self._redo)
        bar_layout.addWidget(self._redo_btn)

        bar_layout.addStretch()

        return bar

    def _create_viewer_toolbar(self, parent) -> QWidget:
        """创建图片查看器下方工具栏（颜色/形状/大小/平滑）"""
        from qfluentwidgets import PushButton as FPushButton, ComboBox as FComboBox
        from qfluentwidgets import ColorPickerButton

        bar = QWidget(parent)
        bar.setFixedHeight(40)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 2, 4, 2)
        bar_layout.setSpacing(3)

        # 颜色
        self._color_btn = ColorPickerButton(QColor("#0078D4"), "", bar)
        self._color_btn.setToolTip("曲线颜色")
        self._color_btn.setFixedSize(32, 32)
        self._color_btn.colorChanged.connect(self._on_color_changed)
        bar_layout.addWidget(self._color_btn)

        # 形状
        self._shape_combo = ComboBox(bar)
        self._shape_combo.addItems(["●", "■", "▲", "◆", "▼", "✕", "★"])
        self._shape_combo.setToolTip("曲线点形状")
        self._shape_combo.setFixedWidth(75)
        self._shape_combo.currentIndexChanged.connect(self._on_shape_changed)
        bar_layout.addWidget(self._shape_combo)

        bar_layout.addWidget(make_vsep(bar))

        # 点大小
        _lbl_size = BodyLabel("大小:", bar)
        _lbl_size.setStyleSheet(f"color: {text_color()};")
        bar_layout.addWidget(_lbl_size)
        self._point_size_spin = SpinBox(bar)
        self._point_size_spin.setRange(1, 50)
        self._point_size_spin.setValue(3)
        self._point_size_spin.setFixedWidth(60)
        self._point_size_spin.valueChanged.connect(self._on_point_size_changed)
        self._point_size_value_label = BodyLabel("3px", bar)
        self._point_size_value_label.setFixedWidth(24)
        self._point_size_value_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 10px;")
        bar_layout.addWidget(self._point_size_spin)
        bar_layout.addWidget(self._point_size_value_label)

        # 橡皮大小
        _lbl_eraser = BodyLabel("橡皮:", bar)
        _lbl_eraser.setStyleSheet(f"color: {text_color()};")
        bar_layout.addWidget(_lbl_eraser)
        self._eraser_size_spin = SpinBox(bar)
        self._eraser_size_spin.setRange(1, 100)
        self._eraser_size_spin.setValue(15)
        self._eraser_size_spin.setFixedWidth(60)
        self._eraser_size_spin.valueChanged.connect(self._on_eraser_size_changed)
        self._eraser_size_value_label = BodyLabel("15px", bar)
        self._eraser_size_value_label.setFixedWidth(24)
        self._eraser_size_value_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 10px;")
        bar_layout.addWidget(self._eraser_size_spin)
        bar_layout.addWidget(self._eraser_size_value_label)

        bar_layout.addWidget(make_vsep(bar))

        # 平滑
        self._smooth_method_combo = FComboBox(bar)
        self._smooth_method_combo.addItems(["移动平均", "Savitzky-Golay"])
        self._smooth_method_combo.setFixedWidth(130)
        bar_layout.addWidget(self._smooth_method_combo)

        self._smooth_btn = FPushButton("平滑", bar)
        self._smooth_btn.setIcon(FIF.EDIT)
        self._smooth_btn.setFixedHeight(33)
        self._smooth_btn.clicked.connect(self._on_smooth_curve)
        bar_layout.addWidget(self._smooth_btn)

        bar_layout.addStretch()
        return bar

    def _create_viewer_status_bar(self, parent) -> QWidget:
        """创建图片查看器底部状态栏（图片路径 + 鼠标坐标）"""
        bar = QWidget(parent)
        bar.setFixedHeight(22)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(4, 0, 4, 0)
        bar_layout.setSpacing(8)
        bar.setStyleSheet(f"background: transparent;")

        self._status_path_label = BodyLabel("", bar)
        self._status_path_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 10px;")
        self._status_path_label.setMaximumWidth(300)
        self._status_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        bar_layout.addWidget(self._status_path_label)

        bar_layout.addStretch()

        self._status_coord_label = BodyLabel("", bar)
        self._status_coord_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 10px;")
        self._status_coord_label.setMinimumWidth(180)
        bar_layout.addWidget(self._status_coord_label)

        return bar

    def _create_combined_tab(self) -> QWidget:
        """创建合并的图片选点功能区（手动/自动/辅助三节）"""
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)
        layout = outer

        # ══════════ 手动选点 ══════════
        layout.addWidget(make_section_label("手动选点", tab))

        manual_row = QWidget(tab)
        self._manual_tools_row = manual_row
        ml = QHBoxLayout(manual_row)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(4)

        self._crosshair_color_btn = ColorPickerButton(QColor("#00C2FF"), "", manual_row, enableAlpha=False)
        self._crosshair_color_btn.setToolTip("十字颜色")
        self._crosshair_color_btn.setFixedSize(34, 34)
        self._crosshair_color_btn.colorChanged.connect(self._on_crosshair_color_changed)
        ml.addWidget(self._crosshair_color_btn)

        self._calibrate_btn = TogglePushButton(FIF.UNIT, "校准", manual_row)
        self._calibrate_btn.setToolTip("校准 (C)")
        self._calibrate_btn.setFixedHeight(34)
        self._calibrate_btn.clicked.connect(lambda: self._on_tool_clicked("calibrate"))
        ml.addWidget(self._calibrate_btn)

        self._extract_btn = TogglePushButton(FIF.PENCIL_INK, "手动取点", manual_row)
        self._extract_btn.setToolTip("手动提取曲线 (Q)")
        self._extract_btn.setFixedHeight(34)
        self._extract_btn.clicked.connect(lambda: self._on_tool_clicked("extract"))
        ml.addWidget(self._extract_btn)

        ml.addStretch()
        layout.addWidget(manual_row)

        # --- 十字辅助配置 ---
        cross_row = QWidget(tab)
        cl = QHBoxLayout(cross_row)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)
        cl.addWidget(BodyLabel("十字大小:", cross_row))
        self._crosshair_size_slider = Slider(Qt.Orientation.Horizontal, cross_row)
        self._crosshair_size_slider.setRange(4, 24)
        self._crosshair_size_slider.setValue(8)
        self._crosshair_size_slider.setSingleStep(1)
        self._crosshair_size_slider.setPageStep(1)
        self._crosshair_size_slider.valueChanged.connect(self._on_crosshair_size_changed)
        cl.addWidget(self._crosshair_size_slider, 1)
        self._crosshair_size_value_label = BodyLabel("8", cross_row)
        self._crosshair_size_value_label.setFixedWidth(24)
        self._crosshair_size_value_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        cl.addWidget(self._crosshair_size_value_label)
        layout.addWidget(cross_row)

        # --- 微调步长 ---
        nudge_row = QWidget(tab)
        nl = QHBoxLayout(nudge_row)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(4)
        nl.addWidget(BodyLabel("微调步长:", nudge_row))
        self._select_area_slider = Slider(Qt.Orientation.Horizontal, nudge_row)
        self._select_area_slider.setRange(1, 10)
        self._select_area_slider.setValue(3)
        self._select_area_slider.setSingleStep(1)
        self._select_area_slider.setPageStep(1)
        nl.addWidget(self._select_area_slider, 1)
        self._select_area_value_label = BodyLabel("3", nudge_row)
        self._select_area_value_label.setFixedWidth(24)
        self._select_area_value_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        nl.addWidget(self._select_area_value_label)
        self._select_area_slider.valueChanged.connect(self._on_select_area_changed)
        layout.addWidget(nudge_row)

        # ══════════ 自动选点（置于辅助选点之前）══════════
        layout.addWidget(make_hsep(tab))
        layout.addWidget(make_section_label("自动选点", tab))

        # --- 公共检测工具 ---
        auto_btn_row = QWidget(tab)
        self._auto_tools_row = auto_btn_row
        abl = QHBoxLayout(auto_btn_row)
        abl.setContentsMargins(0, 0, 0, 0)
        abl.setSpacing(4)

        self._box_mask_btn = ToggleToolButton(FIF.ZOOM, auto_btn_row)
        self._box_mask_btn.setToolTip("框选蒙版")
        self._box_mask_btn.setFixedSize(34, 34)
        self._box_mask_btn.clicked.connect(lambda: self._on_tool_clicked("box_mask"))
        abl.addWidget(self._box_mask_btn)

        self._brush_mask_btn = ToggleToolButton(FIF.BRUSH, auto_btn_row)
        self._brush_mask_btn.setToolTip("画笔蒙版")
        self._brush_mask_btn.setFixedSize(34, 34)
        self._brush_mask_btn.clicked.connect(lambda: self._on_tool_clicked("brush_mask"))
        abl.addWidget(self._brush_mask_btn)

        self._invert_mask_btn = ToggleToolButton(FIF.UPDATE, auto_btn_row)
        self._invert_mask_btn.setToolTip("反转蒙版\n关闭时蒙版内不识别（默认/规避）。\n开启后蒙版内才识别（感兴趣区域）")
        self._invert_mask_btn.setFixedSize(34, 34)
        self._invert_mask_btn.clicked.connect(self._on_invert_mask)
        abl.addWidget(self._invert_mask_btn)

        self._clear_masks_btn = ToolButton(FIF.CLEAR_SELECTION, auto_btn_row)
        self._clear_masks_btn.setToolTip("清除蒙版 (Ctrl+Shift+Delete)")
        self._clear_masks_btn.setFixedSize(34, 34)
        self._clear_masks_btn.clicked.connect(self._on_clear_masks)
        abl.addWidget(self._clear_masks_btn)

        self._auto_detect_btn = ToolButton(FIF.SEARCH, auto_btn_row)
        self._auto_detect_btn.setToolTip("自动检测 (A)")
        self._auto_detect_btn.setFixedSize(34, 34)
        self._auto_detect_btn.clicked.connect(self._on_auto_detect)
        abl.addWidget(self._auto_detect_btn)

        self._cancel_auto_btn = ToolButton(FIF.CLOSE, auto_btn_row)
        self._cancel_auto_btn.setToolTip("放弃检测结果")
        self._cancel_auto_btn.setFixedSize(34, 34)
        self._cancel_auto_btn.clicked.connect(self._on_cancel_auto_preview)
        abl.addWidget(self._cancel_auto_btn)

        self._apply_auto_btn = ToolButton(FIF.ACCEPT, auto_btn_row)
        self._apply_auto_btn.setToolTip("应用自动检测结果 (Ctrl+Enter)")
        self._apply_auto_btn.setFixedSize(34, 34)
        self._apply_auto_btn.clicked.connect(self._on_apply_auto_points)
        abl.addWidget(self._apply_auto_btn)

        abl.addStretch()
        layout.addWidget(auto_btn_row)

        brush_size_row = QWidget(tab)
        self._mask_brush_size_row = brush_size_row
        bsl = QHBoxLayout(brush_size_row)
        bsl.setContentsMargins(0, 0, 0, 0)
        bsl.setSpacing(4)
        bsl.addWidget(BodyLabel("画笔尺寸:", brush_size_row))
        self._mask_brush_size_slider = Slider(Qt.Orientation.Horizontal, brush_size_row)
        self._mask_brush_size_slider.setRange(4, 80)
        self._mask_brush_size_slider.setValue(20)
        self._mask_brush_size_slider.setSingleStep(1)
        self._mask_brush_size_slider.setPageStep(4)
        self._mask_brush_size_slider.valueChanged.connect(self._on_mask_brush_size_changed)
        bsl.addWidget(self._mask_brush_size_slider, 1)
        self._mask_brush_size_value_label = BodyLabel("20 px", brush_size_row)
        self._mask_brush_size_value_label.setFixedWidth(44)
        self._mask_brush_size_value_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        bsl.addWidget(self._mask_brush_size_value_label)
        layout.addWidget(brush_size_row)

        self._digitize_extension_controls = ExtensionConfigPanel(
            "自动选点扩展",
            "执行检测",
            tab,
            mode="compact",
            framed=False,
        )
        self._digitize_extension_controls.set_status_context("digitize", "自动选点扩展")
        self._digitize_extension_controls.selection_changed.connect(self._on_digitize_extension_selection_changed)
        self._digitize_extension_controls.reload_requested.connect(self._reload_digitize_extensions)
        self._digitize_extension_controls.configs_changed.connect(self.project_modified.emit)
        self._digitize_extension_controls._editor.interactiveFieldRequested.connect(
            self._on_digitize_interactive_field_requested
        )
        self._auto_mode_combo = self._digitize_extension_controls._selector
        self._digitize_auto_config_scroll = self._digitize_extension_controls._editor._scroll_area
        self._digitize_extension_controls.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._digitize_extension_controls.setMinimumHeight(0)
        self._digitize_extension_controls._editor.setMinimumHeight(0)
        self._digitize_extension_controls._editor.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._digitize_auto_config_scroll.setMinimumHeight(0)
        self._digitize_auto_config_scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._digitize_extension_controls, 1)

        self._refresh_digitize_extension_choices()

        # ══════════ 辅助选点（暂时隐藏，功能待完善）══════════
        # 创建所有辅助选点控件，但包装在隐藏容器中
        _assist_container = QWidget(tab)
        _assist_container.setVisible(False)
        ac_layout = QVBoxLayout(_assist_container)
        ac_layout.setContentsMargins(0, 0, 0, 0)
        ac_layout.setSpacing(4)

        assist_sep = QFrame(_assist_container)
        assist_sep.setFrameShape(QFrame.Shape.HLine)
        assist_sep.setStyleSheet(f"color: {self._border_color()};")
        ac_layout.addWidget(assist_sep)
        assist_lbl = BodyLabel("辅助选点", _assist_container)
        assist_lbl.setStyleSheet(f"color: {text_color()}; font-weight: bold; font-size: 11px;")
        ac_layout.addWidget(assist_lbl)

        assist_btn_row = QWidget(_assist_container)
        al = QHBoxLayout(assist_btn_row)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(4)

        self._assist_btn = ToggleToolButton(FIF.ZOOM, assist_btn_row)
        self._assist_btn.setToolTip("辅助选点：点击两个端点定义区域")
        self._assist_btn.setFixedSize(34, 34)
        self._assist_btn.clicked.connect(lambda: self._on_tool_clicked("assisted"))
        al.addWidget(self._assist_btn)

        self._assist_shape_combo = ComboBox(assist_btn_row)
        self._assist_shape_combo.addItems(["▭", "◯"])
        self._assist_shape_combo.setFixedWidth(70)
        self._assist_shape_combo.setToolTip("辅助区域形状")
        al.addWidget(self._assist_shape_combo)

        self._assist_apply_btn = ToolButton(FIF.ACCEPT, assist_btn_row)
        self._assist_apply_btn.setToolTip("应用辅助预览结果")
        self._assist_apply_btn.setFixedSize(34, 34)
        self._assist_apply_btn.clicked.connect(self._on_apply_auto_points)
        al.addWidget(self._assist_apply_btn)

        al.addStretch()
        ac_layout.addWidget(assist_btn_row)

        self._assist_status_label = BodyLabel("", _assist_container)
        self._assist_status_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        self._assist_status_label.setWordWrap(True)
        ac_layout.addWidget(self._assist_status_label)

        layout.addWidget(_assist_container)
        return tab

    def _digitize_extension_entries(self) -> list[dict]:
        entries: list[dict] = []
        for extension in extension_registry.list_digitize():
            entry = build_extension_entry(extension)
            if not entry.get("listed", True):
                continue
                entry["label"] = str(entry.get("name") or entry.get("type") or "数字化扩展")
            entries.append(entry)
        return entries

    def _digitize_extension_entries_with_fallback(self) -> tuple[list[dict], list[str]]:
        entries = self._digitize_extension_entries()
        if entries:
            return entries, [str(entry.get("type") or "") for entry in entries if str(entry.get("type") or "")]
        fallback_entries = [
            {"type": COLOR_DIGITIZE_EXTENSION_TYPE, "label": "颜色识别", "name": "颜色识别"},
            {"type": SHAPE_DIGITIZE_EXTENSION_TYPE, "label": "图形识别", "name": "图形识别"},
        ]
        return fallback_entries, [COLOR_DIGITIZE_EXTENSION_TYPE, SHAPE_DIGITIZE_EXTENSION_TYPE]

    def _refresh_digitize_extension_choices(self) -> None:
        if self._digitize_extension_controls is None:
            return
        current_type = self._current_digitize_extension_type()
        entries, auto_mode_type_ids = self._digitize_extension_entries_with_fallback()
        self._auto_mode_type_ids = auto_mode_type_ids
        target_type = current_type if current_type in self._auto_mode_type_ids else self._auto_mode_type_ids[0]
        self._digitize_extension_controls.set_entries(entries, current_type=target_type)
        self._refresh_digitize_extension_panel()

    def _refresh_digitize_extension_panel(self, current_type: str | None = None) -> None:
        if not hasattr(self, "_extension_panel"):
            return
        type_id = current_type if current_type is not None else self._current_digitize_extension_type()
        entries, _ = self._digitize_extension_entries_with_fallback()
        self._extension_panel.set_entries(
            entries,
            current_type=type_id,
        )

    def _current_digitize_extension_type(self) -> str:
        if self._digitize_extension_controls is not None:
            current_type = str(self._digitize_extension_controls.current_type() or "").strip()
            if current_type:
                return current_type
        idx = self._auto_mode_combo.currentIndex() if hasattr(self, "_auto_mode_combo") else -1
        if 0 <= idx < len(self._auto_mode_type_ids):
            return self._auto_mode_type_ids[idx]
        return COLOR_DIGITIZE_EXTENSION_TYPE

    def _current_digitize_extension_options(self) -> dict[str, Any]:
        if self._digitize_extension_controls is None:
            return {}
        options = self._digitize_extension_controls.current_options()
        return dict(options or {})

    def _current_digitize_extension_params(
        self,
        type_id: str,
        *,
        mask_polygons,
        mask_include_mode: bool,
    ) -> dict[str, Any]:
        params: dict[str, Any] = self._current_digitize_extension_options()
        params.update({
            "mask_polygons": mask_polygons,
            "mask_include_mode": bool(mask_include_mode),
        })
        params["step"] = int(params.get("step", 5) or 5)

        color_value = params.get("sampled_color")
        if isinstance(color_value, dict):
            try:
                self._sampled_color = QColor(
                    int(color_value.get("r", 0) or 0),
                    int(color_value.get("g", 0) or 0),
                    int(color_value.get("b", 0) or 0),
                )
            except (TypeError, ValueError):
                self._sampled_color = None
        elif type_id != COLOR_DIGITIZE_EXTENSION_TYPE:
            self._sampled_color = None

        template_info = params.get("template_info")
        self._shape_template = dict(template_info) if isinstance(template_info, dict) else None
        return params

    def _clear_pending_digitize_interaction(self) -> None:
        self._workspace_controller.clear_pending_interaction()

    def _set_digitize_interactive_field_value(self, key: str | None, value: Any) -> bool:
        if not key or self._digitize_extension_controls is None:
            return False
        return self._digitize_extension_controls._editor.set_field_value(key, value)

    def _reload_digitize_extensions(self) -> None:
        report = reload_configured_extensions()
        self._refresh_digitize_extension_choices()
        self.project_modified.emit()
        if report.get("errors"):
            InfoBar.warning(
                title="重载完成",
                content=f"已加载 {len(report.get('loaded', []))} 个扩展，{len(report.get('errors', []))} 个失败",
                parent=self,
                duration=3000,
            )
            return
        InfoBar.success(
            title="已重载",
            content=f"已重新加载 {len(report.get('loaded', []))} 个扩展",
            parent=self,
            duration=2500,
        )

    def _on_digitize_extension_selection_changed(self, type_id: str) -> None:
        selected_type = str(type_id or "").strip() or None
        if self._active_tool in {"color_pick", "crop_template"}:
            self._on_tool_clicked(None)
        self._clear_pending_digitize_interaction()
        self._refresh_digitize_extension_panel(selected_type)

    def _on_digitize_interactive_field_requested(self, key: str, field: object) -> None:
        if self._current_image_id is None:
            InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
            return
        field_info = dict(field or {}) if isinstance(field, dict) else {}
        field_type = str(field_info.get("field_type") or "").strip().lower()
        self._pending_digitize_field_key = str(key or "").strip() or None
        self._pending_digitize_field_type = field_type or None
        if field_type == "pickcolor":
            self._on_tool_clicked("color_pick")
            self._set_tool_status("请在图片上点击取色，完成后会自动写回当前扩展参数")
            return
        if field_type == "shot":
            self._on_tool_clicked("crop_template")
            self._set_tool_status("请在图片上拖拽截图，完成后会自动写回当前扩展参数")
            return
        self._clear_pending_digitize_interaction()

    def _create_export_tab(self) -> QWidget:
        """创建数据导出功能区"""
        from qfluentwidgets import PushButton
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 导出范围
        scope_row = QHBoxLayout()
        self._export_scope_label = self._make_export_row_label("导出范围:", tab)
        scope_row.addWidget(self._export_scope_label)
        self._export_scope_combo = ComboBox(tab)
        self._export_scope_combo.addItems(["当前曲线", "全部曲线"])
        self._export_scope_combo.currentIndexChanged.connect(self._on_export_scope_changed)
        scope_row.addWidget(self._export_scope_combo)
        layout.addLayout(scope_row)

        name_row = QHBoxLayout()
        self._export_name_label = self._make_export_row_label("结果名称:", tab)
        name_row.addWidget(self._export_name_label)
        self._export_name_edit = LineEdit(tab)
        self._export_name_edit.setPlaceholderText("不填写时自动生成")
        name_row.addWidget(self._export_name_edit)
        layout.addLayout(name_row)

        export_btn = PushButton("导出曲线...", tab)
        export_btn.clicked.connect(self._on_export_curves)
        self._export_curve_btn = export_btn
        layout.addWidget(export_btn)

        self._export_target_label = BodyLabel("导出目标: 共享树中选择数据文件或数据目录", tab)
        self._export_target_label.hide()

        export_data_btn = PrimaryPushButton("导出为数据列", tab)
        export_data_btn.clicked.connect(self._on_export_to_data_file)
        layout.addWidget(export_data_btn)

        layout.addStretch()
        self._refresh_export_name_suggestion(force=True)
        return tab

    def _on_export_scope_changed(self, index: int) -> None:
        del index
        self._refresh_export_name_suggestion()

    def _border_color(self):
        return border_color()

    @staticmethod
    def _make_export_row_label(text: str, parent: QWidget) -> BodyLabel:
        label = BodyLabel(text, parent)
        label.setMinimumWidth(label.sizeHint().width())
        label.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        return label

    def _update_curve_table(self):
        """更新曲线数据表格 - 显示选中曲线的实时数据"""
        self._curve_table.setRowCount(0)

        # 如果有选中的曲线，显示该曲线的数据
        if self._current_curve_id:
            curve = project_manager.get_curve(self._current_curve_id)
            if curve and curve.x_data:
                # 如果曲线有校准数据，显示实际坐标；否则显示像素坐标
                has_calibration = curve.calibration is not None
                # 更新表头
                if has_calibration:
                    coord_type = curve.calibration.coord_type if curve.calibration else "linear"
                    if coord_type == "polar":
                        self._curve_table.setHorizontalHeaderLabels(["\u03b8 (角度)", "r (极径)"])
                    else:
                        self._curve_table.setHorizontalHeaderLabels(["X (实际)", "Y (实际)"])
                else:
                    self._curve_table.setHorizontalHeaderLabels(["X (像素)", "Y (像素)"])

                for i in range(len(curve.x_data)):
                    row = self._curve_table.rowCount()
                    self._curve_table.insertRow(row)

                    if has_calibration:
                        # 重新从像素坐标实时计算确保与导出一致
                        try:
                            xa, ya = project_manager.pixel_to_actual_coords(
                                self._current_curve_id, curve.x_data[i], curve.y_data[i]
                            )
                            x_item = QTableWidgetItem(f"{xa:.4f}")
                            y_item = QTableWidgetItem(f"{ya:.4f}")
                        except Exception:
                            x_item = QTableWidgetItem(f"{curve.x_data[i]:.4f}")
                            y_item = QTableWidgetItem(f"{curve.y_data[i]:.4f}")
                    else:
                        x_item = QTableWidgetItem(f"{curve.x_data[i]:.4f}")
                        y_item = QTableWidgetItem(f"{curve.y_data[i]:.4f}")
                    self._curve_table.setItem(row, 0, x_item)
                    self._curve_table.setItem(row, 1, y_item)
        elif self._current_image_id:
            # 如果没有选中曲线但有选中图片，显示该图片所有曲线的数据预览
            img = project_manager.get_image(self._current_image_id)
            if img:
                self._curve_table.setHorizontalHeaderLabels(["X", "Y"])
                for curve in img.curves:
                    for i in range(len(curve.x_data)):
                        row = self._curve_table.rowCount()
                        self._curve_table.insertRow(row)

                        x_item = QTableWidgetItem(f"{curve.x_data[i]:.4f}")
                        y_item = QTableWidgetItem(f"{curve.y_data[i]:.4f}")
                        self._curve_table.setItem(row, 0, x_item)
                        self._curve_table.setItem(row, 1, y_item)

    def _refresh_project_tree(self, show_indicator: bool = False):
        if self._project_tree is None:
            return
        self._project_tree.clear()

        current_img_id = self._current_image_id
        current_curve_id = self._current_curve_id

        # 记录需要选中的节点（用于 setCurrentItem）
        _target_item = None

        for project in project_manager.projects:
            project_item = QTreeWidgetItem(self._project_tree)
            project_item.setText(0, f"📁 {project.name}")
            project_item.setData(0, Qt.ItemDataRole.UserRole, ("project", project.id))
            project_item.setExpanded(True)

            if project.id == project_manager.current_project_id:
                font = project_item.font(0)
                font.setBold(True)
                project_item.setFont(0, font)
                self._current_project_item = project_item
                if show_indicator and current_img_id is None and current_curve_id is None:
                    _target_item = project_item

            for img in project.images:
                img_item = QTreeWidgetItem(project_item)
                img_item.setText(0, f"🖼️ {img.name}")
                img_item.setData(0, Qt.ItemDataRole.UserRole, ("image", img.id, project.id))
                img_item.setExpanded(True)
                if show_indicator and img.id == current_img_id and current_curve_id is None:
                    _target_item = img_item

                # 图片的曲线作为图片的子节点
                for curve in img.curves:
                    curve_item = QTreeWidgetItem(img_item)
                    # 如果曲线被隐藏，使用不同的图标
                    if curve.id in self._hidden_curves:
                        curve_item.setText(0, f"🔵 {curve.name} (已隐藏)")
                    else:
                        curve_item.setText(0, f"📈 {curve.name}")
                    curve_item.setData(0, Qt.ItemDataRole.UserRole, ("curve", curve.id, project.id, img.id))
                    if show_indicator and curve.id == current_curve_id:
                        _target_item = curve_item

            # 项目级别的导入曲线
            for curve in project.imported_curves:
                curve_item = QTreeWidgetItem(project_item)
                if curve.id in self._hidden_curves:
                    curve_item.setText(0, f"🔵 {curve.name} (已隐藏)")
                else:
                    curve_item.setText(0, f"📈 {curve.name}")
                curve_item.setData(0, Qt.ItemDataRole.UserRole, ("curve", curve.id, project.id))
                if show_indicator and curve.id == current_curve_id:
                    _target_item = curve_item

        # 使用 TreeWidget 原生选中高亮（TreeItemDelegate 会正确绘制）
        if _target_item is not None:
            self._project_tree.setCurrentItem(_target_item)

    def refresh_project_tree(self, show_indicator: bool = False) -> None:
        self._refresh_project_tree(show_indicator=show_indicator)

    def _on_tool_clicked(self, tool_name: Optional[str]):
        """处理工具按钮点击"""
        # 如果已经激活了同一个工具，检查是否需要完成校准
        if self._active_tool == tool_name:
            # 校准模式下，检查是否已完成点设置
            if tool_name == "calibrate":
                calib = self._image_viewer.get_calibration()
                if calib.is_complete():
                    # 校准点已设置完成，弹出对话框完成校准
                    self._on_calibration_complete(calib)
                    return
                else:
                    # 校准未完成，提示用户
                    next_type = calib.next_point_type()
                    hints = {
                        "x_start": "请先完成X轴起点的设置",
                        "x_end": "请先完成X轴终点的设置",
                        "y_start": "请先完成Y轴起点的设置",
                        "y_end": "请先完成Y轴终点的设置",
                        "origin": "请先完成原点的设置",
                        "angle_point1": "请先完成A点(角度θ1)的设置",
                        "angle_point2": "请先完成B点(角度θ2)的设置",
                        "radius_point": "请先完成C点(极径r1)的设置",
                        "complete": "校准点已设置完成，请再次点击校准按钮",
                    }
                    self._status_label.setText(hints.get(next_type, "请继续设置校准点"))
                    return
            # 取消当前工具
            self._deactivate_all_tools()
            self._image_viewer.set_select_mode()
            self._active_tool = None
            self._set_tool_status()
            return

        self._deactivate_all_tools()

        if tool_name == "calibrate":
            # 校准需要选中一个曲线
            if self._current_curve_id is None:
                InfoBar.warning(title="警告", content="请先选择一个曲线进行校准", parent=self, duration=3000)
                return

            # 检查是否有现有校准坐标
            calib = self._image_viewer.get_calibration()
            if calib.is_complete():
                if not MessageBox("确认", "开始校准将清除当前的校准坐标，确定要继续吗？", self).exec():
                    return
                # 重置校准坐标
                calib.reset()

            # 弹出坐标类型选择对话框
            coord_dialog = CoordTypeDialog(self)
            if coord_dialog.exec():
                coord_type = coord_dialog.get_coord_type()
            else:
                return

            self._activate_tool_button(self._calibrate_btn)
            self._image_viewer.set_calibrate_mode(coord_type)
            self._active_tool = tool_name
            self._current_curve_points = []

            if coord_type == "linear":
                self._status_label.setText("请点击设置 X 轴起点 (第1/4)")
            elif coord_type == "log":
                self._status_label.setText("请点击设置 X 轴起点 (第1/4) (对数刻度)")
            elif coord_type == "polar":
                self._status_label.setText("请点击设置原点 O (第1/2)")
        elif tool_name == "extract":
            # 提取曲线需要先选择或创建一个曲线
            if self._current_image_id is None:
                InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            if self._current_curve_id is None:
                InfoBar.warning(title="警告", content="请先选择一条曲线", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            self._activate_tool_button(self._extract_btn)
            _curve_color = "#0078D4"
            _curve_shape = "circle"
            if self._current_curve_id:
                _c = project_manager.get_curve(self._current_curve_id)
                if _c:
                    _curve_color = _c.color
                    _curve_shape = getattr(_c, 'point_shape', 'circle')
            self._image_viewer.set_extract_mode(_curve_color, _curve_shape)
            self._active_tool = tool_name
            self._current_curve_points = []
            self._status_label.setText("点击添加点，E键切换橡皮擦模式")
        elif tool_name == "eraser":
            # 橡皮擦需要先选择一条曲线
            if self._current_image_id is None or self._current_curve_id is None:
                InfoBar.warning(title="警告", content="请先选择一张图片和一条曲线", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            self._activate_tool_button(self._eraser_btn)
            self._image_viewer.set_eraser_mode()
            self._active_tool = tool_name
            eraser_size = int(self._eraser_size_spin.value())
            self._status_label.setText(f"橡皮擦范围: {eraser_size}px，点击或拖动擦除")
        elif tool_name == "box_mask":
            # 框选蒙版需要先选择一张图片
            if self._current_image_id is None:
                InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            self._activate_tool_button(self._box_mask_btn)
            self._image_viewer.set_box_mask_mode()
            self._active_tool = tool_name
            self._status_label.setText("拖动绘制矩形蒙版区域")
        elif tool_name == "brush_mask":
            # 画笔蒙版需要先选择一张图片
            if self._current_image_id is None:
                InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            self._activate_tool_button(self._brush_mask_btn)
            self._image_viewer.set_brush_mask_mode()
            self._active_tool = tool_name
            brush_size = int(self._mask_brush_size_slider.value()) if hasattr(self, "_mask_brush_size_slider") else 20
            self._status_label.setText(f"涂刷蒙版：按住拖动涂抹遮罩区域（画笔 {brush_size}px）")
        elif tool_name == "color_pick":
            if self._current_image_id is None:
                InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            self._activate_tool_button(getattr(self, "_screen_pick_btn", None))
            self._image_viewer.set_color_pick_mode()
            self._active_tool = tool_name
            self._status_label.setText("取色模式：点击图片上曲线的颜色")
        elif tool_name == "crop_template":
            if self._current_image_id is None:
                InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            self._activate_tool_button(getattr(self, "_crop_template_btn", None))
            self._image_viewer.set_crop_mode()
            self._active_tool = tool_name
            self._status_label.setText("截图模式：拖拽选取图例区域")
        elif tool_name == "assisted":
            if self._current_image_id is None:
                InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            if self._current_curve_id is None:
                InfoBar.warning(title="警告", content="请先选择一条曲线", parent=self, duration=3000)
                self._deactivate_all_tools()
                return
            self._activate_tool_button(self._assist_btn)
            shape = "ellipse" if self._assist_shape_combo.currentText() == "◯" else "rect"
            self._image_viewer.set_assisted_mode(shape=shape)
            self._active_tool = tool_name
            self._status_label.setText("辅助选点：点击两个端点，提取其间矩形/椭圆区域")
        else:
            self._image_viewer.set_select_mode()
            self._active_tool = None
            self._set_tool_status()

    def _activate_tool_button(self, btn):
        """激活工具按钮"""
        if btn is not None:
            btn.setChecked(True)

    def _deactivate_all_tools(self):
        """取消所有工具按钮的激活状态"""
        for button_name in (
            "_box_mask_btn",
            "_brush_mask_btn",
            "_eraser_btn",
            "_calibrate_btn",
            "_extract_btn",
            "_screen_pick_btn",
            "_assist_btn",
            "_crop_template_btn",
        ):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setChecked(False)

    def _on_escape_tool(self):
        """取消当前工具，恢复到选择模式（Escape 快捷键）"""
        if self._active_tool is not None:
            self._deactivate_all_tools()
            self._image_viewer.set_select_mode()
            self._active_tool = None
            self._clear_pending_digitize_interaction()
            self._set_tool_status()

    def _on_clear_masks(self):
        """清除所有蒙版区域"""
        mask = self._image_viewer.get_mask()
        if mask:
            mask.reset()
            self._image_viewer.update()
            self._status_label.setText("已清除所有蒙版区域")
            self.project_modified.emit()

    def _on_invert_mask(self):
        """切换蒙版模式（感兴趣区域 / 屏蔽区域）"""
        mask = self._image_viewer.get_mask()
        if mask:
            inverted = self._invert_mask_btn.isChecked()
            mask.include_mode = inverted  # 选中=感兴趣(include), 未选中=屏蔽(默认)
            self._image_viewer.update()
            mode_text = "感兴趣区域（蒙版内才识别）" if inverted else "屏蔽区域（蒙版内不识别）"
            self._status_label.setText(f"蒙版模式已切换为: {mode_text}")

    def _on_image_file_dropped(self, file_path: str):
        """处理图片拖放到图片查看器"""
        import os
        # 判断是否是图片文件
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif', '.webp'):
            self._status_label.setText("不支持的文件格式")
            return

        # 若无当前项目，自动新建默认项目
        if project_manager.current_project is None:
            import os as _os
            default_name = _os.path.splitext(_os.path.basename(file_path))[0]
            project_manager.create_new(default_name, parent_dir=_os.path.dirname(file_path), create_structure=True)
            self._refresh_project_tree()

        image_work = project_manager.add_image(file_path)
        self._workspace_controller.set_current_image(image_work.id)
        self._workspace_controller.set_current_curve(None)
        self._image_viewer.load_image(project_manager.get_image_path(image_work.id))
        self._refresh_project_tree()
        self.project_modified.emit()
        self._status_label.setText(f"已添加图片: {os.path.basename(file_path)}")

    def _on_assisted_region(self, x1: float, y1: float, x2: float, y2: float):
        """辅助选点：在矩形/椭圆区域内使用自动颜色识别提取点"""
        options = self._current_digitize_extension_options()
        sampled_color = options.get("sampled_color")
        if isinstance(sampled_color, dict):
            try:
                self._sampled_color = QColor(
                    int(sampled_color.get("r", 0) or 0),
                    int(sampled_color.get("g", 0) or 0),
                    int(sampled_color.get("b", 0) or 0),
                )
            except (TypeError, ValueError):
                self._sampled_color = None
        if self._sampled_color is None:
            InfoBar.warning(title="警告", content="请先在「自动选点」区取色后再使用辅助选点", parent=self, duration=3000)
            self._deactivate_all_tools()
            self._image_viewer.set_select_mode()
            self._active_tool = None
            return
        if self._current_curve_id is None:
            return

        image_path = self._image_viewer.get_image_path()
        if not image_path:
            return

        from extensions.digitize._extractors import AutoExtractor
        tol = int(options.get("tolerance", 20) or 20)
        h_tol = max(5, tol // 2)
        s_tol = min(255, tol * 4)
        v_tol = min(255, tol * 4)
        step = int(options.get("step", 5) or 5)

        # 构建区域蒙版（两点对角线的矩形或椭圆近似多边形）
        x_lo, x_hi = min(x1, x2), max(x1, x2)
        y_lo, y_hi = min(y1, y2), max(y1, y2)
        if self._assist_shape_combo.currentText() == "◯":
            import math
            cx = (x_lo + x_hi) / 2.0
            cy = (y_lo + y_hi) / 2.0
            rx = max(1.0, (x_hi - x_lo) / 2.0)
            ry = max(1.0, (y_hi - y_lo) / 2.0)
            region_mask = [
                (cx + rx * math.cos(2 * math.pi * i / 36.0),
                 cy + ry * math.sin(2 * math.pi * i / 36.0))
                for i in range(36)
            ]
        else:
            region_mask = [(x_lo, y_lo), (x_hi, y_lo), (x_hi, y_hi), (x_lo, y_hi)]

        self._assist_status_label.setText("辅助检测中...")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            points = AutoExtractor.extract(
                image_path,
                target_r=self._sampled_color.red(),
                target_g=self._sampled_color.green(),
                target_b=self._sampled_color.blue(),
                h_tol=h_tol, s_tol=s_tol, v_tol=v_tol,
                mask_polygons=[region_mask],
                step=step,
            )
        except Exception as e:
            self._assist_status_label.setText(f"检测失败: {e}")
            return

        self._auto_preview_points = points
        self._image_viewer.set_preview_points(points)
        self._assist_status_label.setText(f"辅助选点检测到 {len(points)} 个点，点击 ✓ 写入")

        # 回到正常模式
        self._deactivate_all_tools()
        self._image_viewer.set_select_mode()
        self._active_tool = None

    def _on_header_sort(self, col: int):
        """点击表头排序（含撤销支持）"""
        if self._current_curve_id is None:
            return
        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None or not curve.x_data:
            return

        if self._sort_col == col:
            self._sort_order = (Qt.SortOrder.DescendingOrder
                                if self._sort_order == Qt.SortOrder.AscendingOrder
                                else Qt.SortOrder.AscendingOrder)
        else:
            self._sort_col = col
            self._sort_order = Qt.SortOrder.AscendingOrder

        reverse = (self._sort_order == Qt.SortOrder.DescendingOrder)
        is_polar = bool(curve.calibration and curve.calibration.coord_type == "polar")
        if is_polar:
            if col == 0:
                base_values = curve.x_actual if len(curve.x_actual) == len(curve.x_data) else [
                    project_manager.pixel_to_actual_coords(self._current_curve_id, curve.x_data[i], curve.y_data[i])[0]
                    for i in range(len(curve.x_data))
                ]
            else:
                base_values = curve.y_actual if len(curve.y_actual) == len(curve.y_data) else [
                    project_manager.pixel_to_actual_coords(self._current_curve_id, curve.x_data[i], curve.y_data[i])[1]
                    for i in range(len(curve.y_data))
                ]
            def key_fn(i):
                return base_values[i]
        else:
            if col == 0:
                def key_fn(i):
                    return curve.x_data[i]
            else:
                def key_fn(i):
                    return curve.y_data[i]
        indices = sorted(range(len(curve.x_data)), key=key_fn, reverse=reverse)

        # 记录到撤销栈（保存完整数据）
        self._record_state("clear_curve", self._current_curve_id, {
            "points": list(zip(curve.x_data, curve.y_data)),
            "x_actual": list(curve.x_actual) if curve.x_actual else [],
            "y_actual": list(curve.y_actual) if curve.y_actual else [],
        })

        curve.x_data = [curve.x_data[i] for i in indices]
        curve.y_data = [curve.y_data[i] for i in indices]
        if curve.x_actual and curve.y_actual and len(curve.x_actual) == len(indices):
            curve.x_actual = [curve.x_actual[i] for i in indices]
            curve.y_actual = [curve.y_actual[i] for i in indices]

        self._display_current_curve_on_image()
        self._update_curve_table()
        self.project_modified.emit()
        order_str = "升序" if not reverse else "降序"
        if is_polar:
            col_str = "角度" if col == 0 else "极径"
        else:
            col_str = "X" if col == 0 else "Y"
        self._status_label.setText(f"已按 {col_str} {order_str} 排序（可撤销）")

    def _on_curve_table_context_menu(self, pos):
        """曲线数据表右键菜单"""
        index = self._curve_table.indexAt(pos)
        if index.isValid() and not self._curve_table.selectionModel().isRowSelected(index.row(), index.parent()):
            self._curve_table.selectRow(index.row())
        menu = RoundMenu(parent=self)
        delete_action = Action("删除选中行")
        delete_action.triggered.connect(self._delete_selected_table_rows)
        menu.addAction(delete_action)
        menu.exec(self._curve_table.viewport().mapToGlobal(pos))

    def _delete_selected_table_rows(self):
        """删除表格选中行（可撤销/重做）"""
        if self._current_curve_id is None:
            return
        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None or not curve.x_data:
            return

        rows = sorted({idx.row() for idx in self._curve_table.selectionModel().selectedRows()})
        if not rows:
            return

        deleted = []
        for i in rows:
            if 0 <= i < len(curve.x_data):
                deleted.append({
                    "index": i,
                    "x": curve.x_data[i],
                    "y": curve.y_data[i],
                    "x_actual": curve.x_actual[i] if curve.x_actual and i < len(curve.x_actual) else None,
                    "y_actual": curve.y_actual[i] if curve.y_actual and i < len(curve.y_actual) else None,
                })
        if not deleted:
            return

        self._record_state("remove_points_batch", self._current_curve_id, {"points": deleted})

        for i in sorted(rows, reverse=True):
            if 0 <= i < len(curve.x_data):
                del curve.x_data[i]
                del curve.y_data[i]
                if curve.x_actual and i < len(curve.x_actual):
                    del curve.x_actual[i]
                    del curve.y_actual[i]

        self._display_current_curve_on_image()
        self._update_curve_table()
        self.project_modified.emit()
        self._status_label.setText(f"已删除 {len(deleted)} 行（可撤销）")

    # ==================== 自动选点槽函数 ====================

    def _on_auto_mode_changed(self, index: int):
        """识别模式切换。"""
        del index
        self._refresh_digitize_extension_panel()

    def _on_crop_template(self):
        """进入截图模板模式——在图片上框选图例形状"""
        if self._current_image_id is None:
            InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
            self._clear_pending_digitize_interaction()
            return
        self._on_tool_clicked("crop_template")

    def _on_crop_region_selected(self, x1: float, y1: float, x2: float, y2: float):
        """收到 ImageViewer 的截图区域信号，预处理形状模板"""
        # 退出截图模式
        self._deactivate_all_tools()
        self._image_viewer.set_select_mode()
        self._active_tool = None

        image_path = self._image_viewer.get_image_path()
        if not image_path:
            return

        self._set_tool_status("正在预处理图例模板…")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

        try:
            from extensions.digitize._extractors import ShapeExtractor
            self._shape_template = ShapeExtractor.preprocess_region(
                image_path, x1, y1, x2, y2
            )
            w, h = self._shape_template["size"]
            field_key = self._pending_digitize_field_key
            if not field_key and self._current_digitize_extension_type() == SHAPE_DIGITIZE_EXTENSION_TYPE:
                field_key = "template_info"
            self._set_digitize_interactive_field_value(field_key, self._shape_template)
            self._clear_pending_digitize_interaction()
            self._set_tool_status(
                f"图例模板已截取 ({w}×{h}px)，点击「识别」搜索匹配形状"
            )
        except Exception as e:
            self._shape_template = None
            self._clear_pending_digitize_interaction()
            self._set_tool_status(f"截图处理失败: {e}")

    def _on_cancel_auto_preview(self):
        """放弃自动检测结果，清除预览点，不写入曲线"""
        if self._auto_detect_future is not None and not self._auto_detect_future.done():
            self._auto_detect_job_id += 1
            self._auto_detect_future = None
            self._auto_preview_points = []
            self._image_viewer.clear_preview_points()
            self._set_tool_status("已取消检测，结果将被忽略")
            return
        if not self._auto_preview_points:
            self._set_tool_status("没有待取消的预览结果")
            return
        self._auto_preview_points = []
        self._image_viewer.clear_preview_points()
        self._set_tool_status("已放弃检测结果")

    def _on_color_pick(self):
        """进入图片取色模式"""
        if self._current_image_id is None:
            InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
            self._clear_pending_digitize_interaction()
            return
        self._on_tool_clicked("color_pick")

    def _set_sample_color_card(self, color: QColor):
        """更新自动选点颜色按钮的颜色显示"""
        self._sampled_color = color

    def _on_color_picked(self, color):
        """收到图片取色信号，更新颜色显示"""
        from PySide6.QtGui import QColor as _QColor
        if not isinstance(color, _QColor):
            color = _QColor(color)
        self._sampled_color = color
        hex_str = color.name(_QColor.NameFormat.HexRgb)
        field_key = self._pending_digitize_field_key
        if not field_key and self._current_digitize_extension_type() == COLOR_DIGITIZE_EXTENSION_TYPE:
            field_key = "sampled_color"
        self._set_digitize_interactive_field_value(
            field_key,
            {"r": color.red(), "g": color.green(), "b": color.blue()},
        )
        self._clear_pending_digitize_interaction()
        # 取色完成后恢复 select 模式
        self._deactivate_all_tools()
        self._image_viewer.set_select_mode()
        self._active_tool = None
        self._set_tool_status(f"已采样: {hex_str}")

    def _on_sample_color_changed_direct(self, color):
        """通过颜色对话框直接修改采样颜色"""
        if not isinstance(color, QColor):
            color = QColor(color)
        self._sampled_color = color
        hex_str = color.name(QColor.NameFormat.HexRgb)
        self._set_digitize_interactive_field_value(
            "sampled_color",
            {"r": color.red(), "g": color.green(), "b": color.blue()},
        )
        self._set_tool_status(f"已采样: {hex_str}")

    def _on_auto_detect(self):
        """执行自动识别检测。"""
        if self._current_image_id is None:
            InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
            return

        image_path = self._image_viewer.get_image_path()
        if not image_path:
            InfoBar.warning(title="警告", content="无法获取图片路径", parent=self, duration=3000)
            return

        type_id = self._current_digitize_extension_type()
        extension = extension_registry.get_digitize(type_id)
        if extension is None:
            InfoBar.warning(title="警告", content="当前数字化扩展不可用，请重试", parent=self, duration=3000)
            self._set_tool_status()
            return

        if self._auto_detect_future is not None and not self._auto_detect_future.done():
            InfoBar.info(title="提示", content="自动检测正在进行，请先取消或等待完成", parent=self, duration=3000)
            return

        # 获取蒙版多边形和模式
        mask = self._image_viewer.get_mask()
        mask_polygons = mask.polygons if mask and mask.enabled else None
        mask_include_mode = mask.include_mode if mask else True

        self._set_tool_status("检测中…")
        params = self._current_digitize_extension_params(
            type_id,
            mask_polygons=mask_polygons,
            mask_include_mode=mask_include_mode,
        )
        self._auto_detect_job_id += 1
        job_id = self._auto_detect_job_id
        if self._auto_detect_executor is None:
            self._auto_detect_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="digitize-auto-detect")
        self._auto_detect_future = self._auto_detect_executor.submit(
            _build_digitize_auto_preview_points,
            invoke_digitize_extension_handler,
            line_xy,
            extension.handler,
            image_path,
            params,
        )
        try:
            self._auto_detect_future.result(timeout=0.02)
        except TimeoutError:
            pass
        self._poll_auto_detect(job_id, extension.name)
        QTimer.singleShot(0, partial(self._poll_auto_detect, job_id, extension.name))


    def _on_apply_auto_points(self):
        """将预览点写入当前曲线"""
        if not self._auto_preview_points:
            InfoBar.info(title="提示", content="没有可应用的检测结果，请先执行自动检测", parent=self, duration=3000)
            return
        if self._current_curve_id is None:
            InfoBar.warning(title="警告", content="请先选择一条曲线", parent=self, duration=3000)
            return

        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None:
            return

        # 记录应用前的状态到撤销栈
        self._record_state("clear_curve", self._current_curve_id, {
            "points": list(zip(curve.x_data, curve.y_data)),
            "x_actual": list(curve.x_actual) if curve.x_actual else [],
            "y_actual": list(curve.y_actual) if curve.y_actual else [],
        })

        # 追加预览点到曲线（保留已有点）
        for px, py in self._auto_preview_points:
            curve.x_data.append(px)
            curve.y_data.append(py)
            if curve.calibration:
                xa, ya = project_manager.pixel_to_actual_coords(self._current_curve_id, px, py)
            else:
                xa, ya = px, py
            curve.x_actual.append(xa)
            curve.y_actual.append(ya)

        # 清除预览
        self._auto_preview_points = []
        self._image_viewer.clear_preview_points()
        self._set_tool_status(f"已写入 {len(curve.x_data)} 个点")

        self._display_current_curve_on_image()
        self._update_curve_table()
        self._refresh_project_tree()
        self.project_modified.emit()

    def _poll_auto_detect(self, job_id: int, extension_name: str) -> None:
        future = self._auto_detect_future
        if future is None or job_id != self._auto_detect_job_id:
            return
        if not future.done():
            QTimer.singleShot(50, partial(self._poll_auto_detect, job_id, extension_name))
            return

        try:
            points = list(future.result())
        except Exception as exc:
            if job_id == self._auto_detect_job_id:
                self._set_tool_status(f"{extension_name}失败: {exc}")
            self._auto_detect_future = None
            return

        if job_id != self._auto_detect_job_id:
            return

        self._auto_detect_future = None
        self._auto_preview_points = points
        self._image_viewer.set_preview_points(points)
        self._set_tool_status(f"{extension_name}识别到 {len(points)} 个点，点击「应用」写入曲线")

    # ==================== 数据导出槽函数 ====================

    @staticmethod
    def _ensure_curve_export_suffix(path_text: str, file_format: str) -> str:
        path = Path(path_text)
        suffix = f".{str(file_format or 'csv').strip().lower()}"
        if path.suffix.lower() == suffix:
            return str(path)
        if path.suffix:
            return str(path.with_suffix(suffix))
        return str(path.with_name(f"{path.name}{suffix}"))

    def _on_export_curves(self):
        """通过共享对话框导出曲线到文件或剪贴板"""
        import datetime

        curves = self._get_export_curves()
        if not curves:
            InfoBar.warning(title="警告", content="请先选择有效曲线", parent=self, duration=3000)
            return

        base_name = self._sanitize_export_name(self._export_name_edit.text().strip() or self._suggest_export_name())
        series_list = []
        if len(curves) == 1:
            series_list.append(self._curve_to_data_series(curves[0], export_name=base_name))
        else:
            for curve in curves:
                series_list.append(self._curve_to_data_series(curve))

        merge_supported = False
        if len(series_list) > 1:
            try:
                merge_supported = Exporter.can_merge_data_series(series_list)
            except ValueError:
                merge_supported = False

        export_plan = choose_curve_file_export_plan(
            self,
            title="导出曲线",
            source_labels=[series.name or f"curve_{index + 1}" for index, series in enumerate(series_list)],
            merge_supported=merge_supported,
        )
        if export_plan is None:
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") if export_plan.include_timestamp else None
        try:
            if export_plan.action == "clipboard":
                Exporter.export_series_to_clipboard(series_list, timestamp=timestamp, merged=export_plan.merged)
                self._status_label.setText("已复制到剪贴板")
                return
            default_name = self._ensure_curve_export_suffix(base_name, export_plan.file_format)
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存文件",
                default_name,
                curve_export_file_filter(export_plan.file_format),
            )
            if not file_path:
                return
            file_path = self._ensure_curve_export_suffix(file_path, export_plan.file_format)
            Exporter.export_series_file(series_list, file_path, fmt=export_plan.file_format, timestamp=timestamp, merged=export_plan.merged)
            self._status_label.setText(f"已导出: {file_path}")
        except Exception as exc:
            InfoBar.error(title="导出失败", content=str(exc), parent=self, duration=5000)

    def _get_export_curves(self):
        if self._export_scope_combo.currentIndex() == 1:
            project = project_manager.current_project
            if project is None:
                return []
            curves = []
            for img in project.images:
                curves.extend(img.curves)
            curves.extend(project.imported_curves)
            return [curve for curve in curves if curve.x_actual]
        if self._current_curve_id is None:
            return []
        curve = project_manager.get_curve(self._current_curve_id)
        if curve and curve.x_actual:
            return [curve]
        return []

    def _is_data_folder_target(self, node_id: str) -> bool:
        node = project_manager.get_node_by_id(node_id)
        while node is not None:
            if node.kind == "folder" and getattr(node, "group_type", None) in ("datasets", "dataset_set"):
                return True
            parent_id = getattr(node, "parent_id", None)
            node = project_manager.get_node_by_id(parent_id) if parent_id else None
        return False

    def _curve_to_data_series(self, curve, export_name: str | None = None) -> DataSeries:
        """将 Curve 转换为 DataSeries，导出时重新从像素坐标计算实际坐标以确保一致性。"""
        if curve.calibration and curve.x_data:
            x_vals: list = []
            y_vals: list = []
            for px, py in zip(curve.x_data, curve.y_data):
                xa, ya = project_manager.pixel_to_actual_coords(curve.id, px, py)
                x_vals.append(xa)
                y_vals.append(ya)
        elif curve.x_data:
            x_vals = list(curve.x_data)
            y_vals = list(curve.y_data)
        else:
            x_vals = list(curve.x_actual or [])
            y_vals = list(curve.y_actual or [])
        return DataSeries(
            name=export_name or curve.name or "提取曲线",
            x=x_vals,
            y=y_vals,
            color=curve.color,
            source="pyline_curve_copy",
            source_curve_id=curve.id,
        )

    def _sanitize_export_name(self, name: str) -> str:
        value = (name or "").strip()
        if not value:
            return "digitized_result"
        value = value.replace(".digitize", "").replace(".derived", "")
        value = value.replace("/", "_").replace("\\", "_")
        value = "_".join(part for part in value.split() if part)
        return value or "digitized_result"

    def _find_curve_image_name(self, curve_id: str) -> str:
        project = project_manager.current_project
        if project is None:
            return ""
        for image in project.images:
            if any(curve.id == curve_id for curve in image.curves):
                return image.name or ""
        return ""

    def _suggest_export_name(self) -> str:
        curves = self._get_export_curves()
        if not curves:
            return "digitized_result"
        if len(curves) == 1:
            curve = curves[0]
            image_name = self._find_curve_image_name(curve.id)
            parts = [part for part in [image_name, curve.name or "提取曲线"] if part]
            return self._sanitize_export_name("_".join(parts))
        base_name = self._find_curve_image_name(curves[0].id)
        if not base_name and project_manager.current_project is not None:
            base_name = project_manager.current_project.name
        return self._sanitize_export_name(f"{base_name or 'digitized'}_{len(curves)}条曲线")

    def _refresh_export_name_suggestion(self, force: bool = False) -> None:
        if not hasattr(self, "_export_name_edit") or self._export_name_edit is None:
            return
        suggestion = self._suggest_export_name()
        current = self._export_name_edit.text().strip()
        if force or not current or current == self._last_export_suggestion:
            self._export_name_edit.setText(suggestion)
        self._last_export_suggestion = suggestion

    def _ensure_digitize_result_folder(self) -> str | None:
        return self._save_export_coordinator.find_or_create_folder(
            "数字化结果",
            parent_group_type="datasets",
            folder_group_type="datasets",
            fallback=self._save_export_coordinator.find_folder("datasets"),
        )

    def _on_export_to_data_file(self):
        curves = self._get_export_curves()
        if not curves:
            InfoBar.warning(title="警告", content="请先选择有效曲线", parent=self, duration=3000)
            return

        default_name = self._sanitize_export_name(self._export_name_edit.text().strip() or self._suggest_export_name())
        preferred_target_node_id = self._export_target_id or getattr(project_manager.find_folder_by_group_type("datasets"), "id", None)
        export_plan = choose_data_export_plan(
            self,
            title="导出为数据列",
            default_export_name=default_name,
            default_file_name=f"{default_name}.digitize",
            preferred_target_node_id=preferred_target_node_id,
            file_suffix=".digitize",
            create_target_options=[
                DataCreateTargetOption(
                    label="新建数据文件 / 数据集 / 数字化结果（若不存在则创建）",
                    ensure_parent_id=self._ensure_digitize_result_folder,
                )
            ],
        )
        if export_plan is None:
            return

        base_name = self._sanitize_export_name(export_plan.export_name)
        self._export_name_edit.setText(base_name)
        total = len(curves)
        export_series = []
        for index, curve in enumerate(curves, start=1):
            if total == 1:
                series_name = base_name
            else:
                curve_suffix = self._sanitize_export_name(curve.name or f"curve_{index}")
                series_name = self._sanitize_export_name(f"{base_name}_{curve_suffix}")
            export_series.append(self._curve_to_data_series(curve, export_name=series_name))

        if export_plan.target_data_file_id:
            project = project_manager.current_project
            target_node = next(
                (
                    node for node in project.tree.nodes
                    if node.kind == "data_file" and node.data_file_id == export_plan.target_data_file_id
                ),
                None,
            ) if project is not None and project.tree is not None else None
            appended = 0
            for series in export_series:
                if project_manager.add_series_to_data_file(export_plan.target_data_file_id, series):
                    appended += 1
            if appended == 0:
                InfoBar.error(title="导出失败", content="未能追加到目标数据文件", parent=self, duration=3000)
                return
            if target_node is not None:
                self._export_target_kind = "data_file"
                self._export_target_id = target_node.id
            self._update_export_target_label()
            target_name = target_node.name if target_node is not None else "目标数据文件"
            self._status_label.setText(f"已追加 {appended} 条数据列到数据文件: {target_name}")
        else:
            df = DataFile(
                name=export_plan.new_data_file_name or f"{base_name}.digitize",
                series=export_series,
            )
            node = project_manager.add_data_file(df, parent_id=export_plan.new_parent_id)
            if node is None:
                InfoBar.error(title="导出失败", content="未能创建目标数据文件", parent=self, duration=3000)
                return
            self._export_target_kind = "data_file"
            self._export_target_id = node.id
            self._update_export_target_label()
            self._status_label.setText(f"已导出为数据文件: {df.name}")

        self.project_modified.emit()

    def export_current_curve_to_data_file(self) -> None:
        self._on_export_to_data_file()

    def _update_export_target_label(self):
        if self._export_target_kind == "data_file" and self._export_target_id:
            node = project_manager.get_node_by_id(self._export_target_id)
            name = node.name if node else "目标数据文件"
            self._export_target_label.setText(f"导出目标: 数据文件 / {name}")
        elif self._export_target_kind == "folder" and self._export_target_id:
            node = project_manager.get_node_by_id(self._export_target_id)
            name = node.name if node else "数据目录"
            self._export_target_label.setText(f"导出目标: 数据目录 / {name}")
        else:
            self._export_target_label.setText("导出目标: 共享树中选择数据文件或数据目录")

    # ==================== 曲线平滑槽函数 ====================

    def _on_smooth_curve(self):
        """对当前曲线进行平滑处理"""
        if self._current_curve_id is None:
            InfoBar.warning(title="警告", content="请先选择一条曲线", parent=self, duration=3000)
            return
        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None or len(curve.x_data) < 3:
            InfoBar.info(title="提示", content="曲线点数太少（至少需要 3 个点）", parent=self, duration=3000)
            return

        from processing.smoother import smooth_moving_average, smooth_savgol
        method = self._smooth_method_combo.currentText()

        # 按 X 排序
        pairs = sorted(zip(curve.x_data, curve.y_data))
        x_sorted = [p[0] for p in pairs]
        y_sorted = [p[1] for p in pairs]

        try:
            if method == "移动平均":
                window = max(3, min(7, len(x_sorted) // 3 | 1))
                x_new, y_new = smooth_moving_average(x_sorted, y_sorted, window=window)
            else:
                window = max(5, min(9, len(x_sorted) // 3 | 1))
                x_new, y_new = smooth_savgol(x_sorted, y_sorted, window=window, poly=2)
        except Exception as e:
            InfoBar.error(title="平滑失败", content=str(e), parent=self, duration=5000)
            return

        # 记录到撤销栈
        self._record_state("clear_curve", self._current_curve_id, {
            "points": list(zip(curve.x_data, curve.y_data)),
            "x_actual": list(curve.x_actual) if curve.x_actual else [],
            "y_actual": list(curve.y_actual) if curve.y_actual else [],
        })

        # 更新曲线（重新计算实际坐标）
        curve.x_data = x_new
        curve.y_data = y_new
        curve.x_actual = []
        curve.y_actual = []
        for px, py in zip(x_new, y_new):
            if curve.calibration:
                xa, ya = project_manager.pixel_to_actual_coords(self._current_curve_id, px, py)
            else:
                xa, ya = px, py
            curve.x_actual.append(xa)
            curve.y_actual.append(ya)

        self._display_current_curve_on_image()
        self._update_curve_table()
        self.project_modified.emit()
        self._status_label.setText(f"平滑完成（{method}，窗口={window}）")

    def _on_point_size_changed(self, value):
        self._image_viewer.set_point_size(float(value))
        self._point_size_value_label.setText(f"{value} px")

    def _on_select_area_changed(self, value):
        self._image_viewer.set_select_threshold(float(value))
        self._select_area_value_label.setText(str(value))

    def _on_crosshair_size_changed(self, value):
        self._image_viewer.set_crosshair_size(float(value))
        self._crosshair_size_value_label.setText(str(value))

    def _on_crosshair_color_changed(self, color):
        if isinstance(color, QColor):
            self._image_viewer.set_crosshair_color(color)

    def _on_eraser_size_changed(self, value):
        self._image_viewer.set_eraser_size(float(value))
        self._eraser_size_value_label.setText(f"{value} px")

    def _on_mask_brush_size_changed(self, value):
        self._image_viewer.set_mask_brush_size(float(value))
        self._mask_brush_size_value_label.setText(f"{value} px")

    def _on_color_changed(self, color):
        """颜色改变"""
        if isinstance(color, QColor):
            color_str = color.name(QColor.NameFormat.HexRgb)
        else:
            color_str = str(color)
        if self._current_curve_id:
            curve = project_manager.get_curve(self._current_curve_id)
            if curve:
                curve.color = color_str
                # 如果在提取模式中，同步更新临时曲线颜色
                if self._active_tool == "extract":
                    current = self._image_viewer.get_current_curve()
                    if current is not None:
                        current.color = color_str
                # 重新显示曲线，保留所有点
                self._image_viewer.clear_curves()
                self._display_curve_on_image(curve)
                # 更新校准显示
                if curve.calibration:
                    self._apply_calibration_to_viewer(curve.calibration)
                else:
                    calib = self._image_viewer.get_calibration()
                    calib.reset()
                self._image_viewer.update()
                self.project_modified.emit()

    def _on_shape_changed(self, index):
        """形状改变"""
        shape_map = {"●": "circle", "■": "square", "▲": "triangle", "◆": "diamond", "▼": "inv_triangle", "✕": "cross", "★": "star"}
        shape = shape_map.get(self._shape_combo.currentText(), "circle")
        if self._current_curve_id:
            curve = project_manager.get_curve(self._current_curve_id)
            if curve:
                curve.point_shape = shape
                self._display_current_curve_on_image()
                self.project_modified.emit()

    def _on_tree_item_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return

        item_type = data[0]

        # 清除图片上的曲线显示（会在子节点处理中重新添加）
        self._image_viewer.clear_curves()

        if item_type == "project":
            project_id = data[1]
            project_manager.set_current_project(project_id)
            self._current_project_item = item
            self._current_image_id = None
            self._current_curve_id = None
            self._refresh_project_tree(show_indicator=True)
        elif item_type == "image":
            project_id = data[2]
            project_manager.set_current_project(project_id)
            project = project_manager.get_project(project_id)
            if project:
                img_id = data[1]
                for img in project.images:
                    if img.id == img_id:
                        self._image_viewer.load_image(project_manager.get_image_path(img.id))
                        self._current_image_item = item
                        # 只有当点击不同图片时才改变曲线
                        if self._current_image_id != img_id:
                            self._current_image_id = img_id
                            # 自动选择该图片的第一条曲线
                            if img.curves:
                                self._current_curve_id = img.curves[0].id
                                self._display_current_curve_on_image()
                            else:
                                self._current_curve_id = None
                                self._image_viewer.clear_curves()
                            self._update_curve_table()
                        else:
                            # 同一图片，只刷新校准显示
                            if self._current_curve_id:
                                self._display_current_curve_on_image()
                        self._refresh_project_tree(show_indicator=True)
                        self.current_image_changed.emit(img)
                        break
        elif item_type == "curve":
            curve_id = data[1]
            curve = project_manager.get_curve(curve_id)
            if curve is None:
                return

            self._current_curve_id = curve_id
            # 如果有image_id，说明是图片的子节点
            if len(data) >= 4:
                self._current_image_id = data[3]
                # 加载对应的图片
                project_id = data[2]
                project = project_manager.get_project(project_id)
                if project:
                    for img in project.images:
                        if img.id == self._current_image_id:
                            self._image_viewer.load_image(project_manager.get_image_path(img.id))
                            break
            else:
                self._current_image_id = None

            # 清除图片上的曲线，显示当前选中的曲线和校准
            self._display_current_curve_on_image()
            self._update_curve_table()
            self._refresh_project_tree(show_indicator=True)

    def _on_tree_item_double_clicked(self, item, column):
        pass

    def _on_tree_drop_event(self, event):
        """处理图片节点跨项目拖放"""
        target_item = self._project_tree.itemAt(event.position().toPoint())
        dragged_item = self._project_tree.currentItem()
        if dragged_item is None or target_item is None:
            return

        dragged_data = dragged_item.data(0, Qt.ItemDataRole.UserRole)
        if dragged_data is None or dragged_data[0] != "image":
            return

        # 找到投放目标的所属项目
        target_data = target_item.data(0, Qt.ItemDataRole.UserRole)
        if target_data is None:
            return

        if target_data[0] == "project":
            dest_project_id = target_data[1]
        elif target_data[0] == "image":
            dest_project_id = target_data[2]
        else:
            return

        img_id = dragged_data[1]
        src_project_id = dragged_data[2]

        if src_project_id == dest_project_id:
            return

        src_project = project_manager.get_project(src_project_id)
        dest_project = project_manager.get_project(dest_project_id)
        if src_project is None or dest_project is None:
            return

        if not project_manager.move_image(img_id, dest_project_id):
            return
        self._refresh_project_tree()
        self.project_modified.emit()
        event.accept()

    def _on_tree_context_menu(self, pos):
        """显示项目树右键菜单"""
        item = self._project_tree.itemAt(pos)
        if item is None:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None:
            return

        # 右键时先选中该项（同左键逻辑），然后带指示标志刷新
        self._on_tree_item_clicked(item, 0)
        self._refresh_project_tree(show_indicator=True)

        menu = RoundMenu(parent=self)
        item_type = data[0]

        if item_type == "project":
            project_id = data[1]
            rename_action = Action("重命名项目")
            rename_action.triggered.connect(lambda: self._rename_item("project", project_id))
            menu.addAction(rename_action)
            menu.addSeparator()
            delete_action = Action("删除项目")
            delete_action.triggered.connect(lambda: self._delete_project(project_id))
            menu.addAction(delete_action)

        elif item_type == "image":
            img_id = data[1]
            rename_action = Action("重命名图片")
            rename_action.triggered.connect(lambda: self._rename_item("image", img_id))
            menu.addAction(rename_action)
            menu.addSeparator()
            delete_action = Action("删除图片")
            delete_action.triggered.connect(lambda: self._delete_image(img_id))
            menu.addAction(delete_action)

        elif item_type == "curve":
            curve_id = data[1]
            is_hidden = curve_id in self._hidden_curves

            # 显示/隐藏曲线
            if is_hidden:
                show_action = Action("显示曲线")
                show_action.triggered.connect(lambda checked, cid=curve_id: self._toggle_curve_visibility(cid, False))
                menu.addAction(show_action)
            else:
                hide_action = Action("隐藏曲线")
                hide_action.triggered.connect(lambda checked, cid=curve_id: self._toggle_curve_visibility(cid, True))
                menu.addAction(hide_action)

            rename_action = Action("重命名曲线")
            rename_action.triggered.connect(lambda: self._rename_item("curve", curve_id))
            menu.addAction(rename_action)
            menu.addSeparator()
            delete_action = Action("删除曲线")
            delete_action.triggered.connect(lambda checked, cid=curve_id: self._delete_curve(cid))
            menu.addAction(delete_action)

        menu.exec(self._project_tree.mapToGlobal(pos))

    def _rename_item(self, item_type: str, item_id: str):
        """重命名项目/图片/曲线"""
        if item_type == "project":
            project = project_manager.get_project(item_id)
            if project is None:
                return
            dlg = _InputDialog("重命名项目", "新名称:", text=project.name, parent=self)
            if dlg.exec() and dlg.value().strip():
                project.name = dlg.value().strip()
                self._refresh_project_tree()
                self.project_modified.emit()
        elif item_type == "image":
            img = project_manager.get_image(item_id)
            if img is None:
                return
            dlg = _InputDialog("重命名图片", "新名称:", text=img.name, parent=self)
            if dlg.exec() and dlg.value().strip():
                if project_manager.rename_image(item_id, dlg.value().strip()):
                    self._refresh_project_tree()
                    self.project_modified.emit()
                else:
                    InfoBar.error(title="错误", content="重命名图片失败", parent=self, duration=3000)
        elif item_type == "curve":
            curve = project_manager.get_curve(item_id)
            if curve is None:
                return
            dlg = _InputDialog("重命名曲线", "新名称:", text=curve.name, parent=self)
            if dlg.exec() and dlg.value().strip():
                curve.name = dlg.value().strip()
                self._refresh_project_tree()
                self.project_modified.emit()

    def _delete_project(self, project_id: str):
        """删除项目"""
        project = project_manager.get_project(project_id)
        if project is None:
            return
        if not MessageBox("确认删除", f"确定要删除项目「{project.name}」及其所有图片和曲线吗？", self).exec():
            return
        project_manager.projects.remove(project)
        if project_manager.current_project_id == project_id:
            new_id = project_manager.projects[-1].id if project_manager.projects else None
            if new_id:
                project_manager.set_current_project(new_id)
            else:
                project_manager.clear_current_project()
        if self._current_image_id is not None:
            for img in project.images:
                if img.id == self._current_image_id:
                    self._current_image_id = None
                    self._current_curve_id = None
                    self._image_viewer.clear_image()
                    break
        self._refresh_project_tree()
        self.project_modified.emit()

    def _delete_image(self, img_id: str):
        """删除图片"""
        img = project_manager.get_image(img_id)
        if img is None:
            return
        if not MessageBox("确认删除", f"确定要删除图片「{img.name}」及其所有曲线吗？", self).exec():
            return
        project_manager.remove_image(img_id)
        if self._current_image_id == img_id:
            self._current_image_id = None
            self._current_curve_id = None
            self._image_viewer.clear_image()
        self._refresh_project_tree()
        self.project_modified.emit()

    def _toggle_curve_visibility(self, curve_id: str, hidden: bool):
        """切换曲线可见性"""
        if not hasattr(self, '_hidden_curves'):
            self._hidden_curves = set()

        if hidden:
            self._hidden_curves.add(curve_id)
        else:
            self._hidden_curves.discard(curve_id)

        # 如果当前显示的是这条曲线，更新显示
        if self._current_curve_id == curve_id:
            if hidden:
                self._image_viewer.clear_curves()
                # 隐藏时也清除校准
                calib = self._image_viewer.get_calibration()
                calib.reset()
                self._image_viewer.update()
            else:
                self._display_current_curve_on_image()

        self._refresh_project_tree()

    def _delete_curve(self, curve_id: str):
        """删除曲线"""
        if not MessageBox("确认删除", "确定要删除这条曲线吗？", self).exec():
            return

        curve = project_manager.get_curve(curve_id)
        if curve is None:
            return

        # 从对应的图片中移除
        if curve.source_image_id:
            img = project_manager.get_image(curve.source_image_id)
            if img:
                img.curves = [c for c in img.curves if c.id != curve_id]
        else:
            project = project_manager.current_project
            if project:
                project.imported_curves = [c for c in project.imported_curves if c.id != curve_id]

        # 从隐藏集合中移除
        self._hidden_curves.discard(curve_id)

        if self._current_curve_id == curve_id:
            self._current_curve_id = None
            self._image_viewer.clear_curves()
            # 重置校准
            calib = self._image_viewer.get_calibration()
            calib.reset()

        self._refresh_project_tree()
        self._update_curve_table()
        self.project_modified.emit()

    def _display_curve_on_image(self, curve):
        """在图片查看器上显示曲线的点（使用像素坐标）"""
        from ui.widgets.image_viewer import CurveOverlayItem

        if curve and curve.x_data and curve.y_data:
            curve_item = CurveOverlayItem(color=curve.color, point_shape=getattr(curve, 'point_shape', 'circle'))
            curve_item.name = curve.name

            # 直接使用存储的像素坐标
            for i in range(len(curve.x_data)):
                curve_item.add_point(curve.x_data[i], curve.y_data[i])

            self._image_viewer.add_curve_item(curve_item)

    def _display_current_curve_on_image(self):
        """显示当前选中曲线到图片"""
        self._image_viewer.clear_curves()
        if self._current_curve_id:
            curve = project_manager.get_curve(self._current_curve_id)
            if curve:
                # 显示曲线点
                self._display_curve_on_image(curve)
                # 更新颜色和形状选择器
                if hasattr(self, '_color_btn'):
                    self._color_btn.blockSignals(True)
                    self._color_btn.setColor(QColor(curve.color))
                    self._color_btn.blockSignals(False)
                if hasattr(self, '_shape_combo'):
                    shape_map = {"circle": "●", "square": "■", "triangle": "▲", "diamond": "◆", "inv_triangle": "▼", "cross": "✕", "star": "★", "pentagram": "★"}
                    shape_text = shape_map.get(getattr(curve, 'point_shape', 'circle'), "●")
                    idx = self._shape_combo.findText(shape_text)
                    if idx >= 0:
                        self._shape_combo.blockSignals(True)
                        self._shape_combo.setCurrentIndex(idx)
                        self._shape_combo.blockSignals(False)
                # 设置校准覆盖层（无论曲线是否有数据都要显示校准）
                if curve.calibration:
                    self._apply_calibration_to_viewer(curve.calibration)
                else:
                    calib = self._image_viewer.get_calibration()
                    calib.reset()
                self._image_viewer.update()

    def _apply_calibration_to_viewer(self, calib_data):
        """将校准数据应用到图片查看器"""
        from PySide6.QtCore import QPointF
        calib = self._image_viewer.get_calibration()
        calib.reset()
        if calib_data.x_start:
            calib.x_start = QPointF(calib_data.x_start[0], calib_data.x_start[1])
        if calib_data.x_end:
            calib.x_end = QPointF(calib_data.x_end[0], calib_data.x_end[1])
        if calib_data.y_start:
            calib.y_start = QPointF(calib_data.y_start[0], calib_data.y_start[1])
        if calib_data.y_end:
            calib.y_end = QPointF(calib_data.y_end[0], calib_data.y_end[1])
        calib.x_range = calib_data.x_range
        calib.y_range = calib_data.y_range
        calib.coord_type = calib_data.coord_type

    def _create_calibration_overlay(self, calib_data):
        """从 CalibrationData 创建 CalibrationOverlay"""
        from PySide6.QtCore import QPointF
        overlay = self._image_viewer.get_calibration()
        overlay.reset()
        if calib_data.x_start:
            overlay.x_start = QPointF(calib_data.x_start[0], calib_data.x_start[1])
        if calib_data.x_end:
            overlay.x_end = QPointF(calib_data.x_end[0], calib_data.x_end[1])
        if calib_data.y_start:
            overlay.y_start = QPointF(calib_data.y_start[0], calib_data.y_start[1])
        if calib_data.y_end:
            overlay.y_end = QPointF(calib_data.y_end[0], calib_data.y_end[1])
        overlay.x_range = calib_data.x_range
        overlay.y_range = calib_data.y_range
        overlay.coord_type = calib_data.coord_type
        return overlay

    def _on_new_project(self):
        dlg = _InputDialog("新建项目", "请输入项目名称:", parent=self)
        if not dlg.exec():
            return
        name = dlg.value().strip()
        if name:
            base_dir = QFileDialog.getExistingDirectory(self, "选择项目保存目录", "")
            if not base_dir:
                return
            try:
                project_manager.create_new(name, parent_dir=base_dir, create_structure=True)
                self._refresh_project_tree()
                self.project_saved.emit()
                InfoBar.success(title="成功", content="项目已创建并初始化目录结构", parent=self, duration=3000)
            except Exception as e:
                InfoBar.error(title="错误", content=f"创建项目失败:\n{str(e)}", parent=self, duration=5000)

    def _on_open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开项目", "", "ALine 项目 (*.aline);;所有文件 (*)"
        )
        if file_path:
            try:
                project_manager.open(file_path)
                self._refresh_project_tree()
                self.project_modified.emit()
            except Exception as e:
                InfoBar.error(title="错误", content=f"无法打开项目:\n{str(e)}", parent=self, duration=5000)

    def _on_save_project(self):
        if project_manager.current_project is None:
            InfoBar.warning(title="警告", content="请先选择一个项目", parent=self, duration=3000)
            return

        file_path = project_manager.current_project.file_path
        if file_path is None:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存项目", f"{project_manager.current_project.name}.aline", "ALine 项目 (*.aline)"
            )

        if file_path:
            try:
                project_manager.save(file_path)
                project_manager.current_project.is_modified = False
                self._refresh_project_tree()
                self.project_saved.emit()
                InfoBar.success(title="成功", content=f"项目已保存到:\n{file_path}", parent=self, duration=4000)
            except Exception as e:
                InfoBar.error(title="错误", content=f"保存失败:\n{str(e)}", parent=self, duration=5000)

    def _on_close_project(self):
        if project_manager.current_project is None:
            InfoBar.warning(title="警告", content="请先选择一个项目", parent=self, duration=3000)
            return

        if project_manager.current_project.is_modified:
            decision = confirm_unsaved_project_close(project_manager.current_project.name, self)
            if decision == ProjectCloseDecision.CANCEL:
                return
            if decision == ProjectCloseDecision.SAVE:
                self._on_save_project()

        project_manager.close_current_project()
        self._image_viewer.clear_image()
        self._refresh_project_tree()
        self.project_modified.emit()

    def _on_add_image(self):
        if project_manager.current_project is None:
            InfoBar.warning(title="警告", content="请先选择一个项目", parent=self, duration=3000)
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tiff);;所有文件 (*)"
        )
        if file_path:
            self.import_source_image(file_path)

    def import_source_image(self, file_path: str, *, name: Optional[str] = None) -> bool:
        if project_manager.current_project is None:
            InfoBar.warning(title="警告", content="请先选择一个项目", parent=self, duration=3000)
            return False

        if Path(file_path).suffix.lower() not in _SUPPORTED_SOURCE_IMAGE_SUFFIXES:
            InfoBar.warning(title="提示", content="当前源文件不是可导入到数字化的图片格式", parent=self, duration=3000)
            return False

        try:
            image_work = project_manager.add_image(file_path, name=name)
        except ValueError as exc:
            InfoBar.warning(title="导入失败", content=str(exc), parent=self, duration=3000)
            return False
        self._current_image_id = image_work.id
        self._current_curve_id = None
        self._image_viewer.load_image(project_manager.get_image_path(image_work.id))
        self._refresh_project_tree()
        self.project_modified.emit()
        return True

    def _on_add_curve(self):
        """为当前选中图片添加新曲线"""
        if self._current_image_id is None:
            InfoBar.warning(title="警告", content="请先选择一张图片", parent=self, duration=3000)
            return

        img = project_manager.get_image(self._current_image_id)
        if img is None:
            return

        # 继承同一图片中上一条曲线的校准数据、颜色和形状
        calib = None
        color = "#0078D4"
        point_shape = "circle"
        if img.curves:
            prev_curve = img.curves[-1]
            calib = prev_curve.calibration
            color = prev_curve.color
            point_shape = getattr(prev_curve, 'point_shape', 'circle')

        # 创建新曲线
        curve = project_manager.add_curve_to_image(
            self._current_image_id,
            x_data=[],
            y_data=[],
            name=f"曲线 {len(img.curves) + 1}",
            color=color,
            point_shape=point_shape,
            calibration=calib
        )

        if curve:
            self._current_curve_id = curve.id
            self._display_current_curve_on_image()
            self._update_curve_table()
            self._refresh_project_tree()
            self.project_modified.emit()

    def add_curve_from_shell(self) -> None:
        self._on_add_curve()

    def clear_current_image(self) -> None:
        self._image_viewer.clear_image()

    def _on_image_loaded(self, file_path: str):
        # 更新底部状态栏路径
        if hasattr(self, '_status_path_label'):
            import os as _os
            short = _os.path.basename(file_path)
            self._status_path_label.setText(short)
            self._status_path_label.setToolTip(file_path)
        # 清除图片上的曲线
        self._image_viewer.clear_curves()

        # 只显示当前选中的曲线
        if self._current_curve_id:
            curve = project_manager.get_curve(self._current_curve_id)
            if curve:
                self._display_curve_on_image(curve)

        self._update_curve_table()
        self._refresh_project_tree()

    def load_image(self, file_path: str) -> bool:
        if self._image_viewer:
            return self._image_viewer.load_image(file_path)
        return False

    def on_tree_node_selected(self, kind: str, node_id: str) -> None:
        """共享树节点选中时，若为图片节点则加载到查看器。"""
        if kind == "image_work":
            self.load_image_by_id(node_id)
            return
        if kind == "curve":
            self.load_curve_by_id(node_id)
            return
        if kind == "data_file":
            self._export_target_kind = kind
            self._export_target_id = node_id
            self._update_export_target_label()
            return
        if kind == "folder" and self._is_data_folder_target(node_id):
            self._export_target_kind = kind
            self._export_target_id = node_id
            self._update_export_target_label()

    def on_tree_node_activated(self, kind: str, node_id: str) -> None:
        """共享树节点激活时，同步到当前图片 / 曲线或导出目标。"""
        self.on_tree_node_selected(kind, node_id)

    def _find_image_id_for_curve(self, curve_id: str) -> Optional[str]:
        curve = project_manager.get_curve(curve_id)
        if curve is not None and getattr(curve, "source_image_id", None):
            return curve.source_image_id
        project = project_manager.current_project
        if project is None:
            return None
        for image in project.images:
            if any(existing_curve.id == curve_id for existing_curve in image.curves):
                return image.id
        return None

    def _resolve_image_work_id(self, image_ref: str) -> Optional[str]:
        if not image_ref:
            return None
        image = project_manager.get_image(image_ref)
        if image is not None:
            return image.id
        node = project_manager.get_node_by_id(image_ref)
        if node is not None and getattr(node, "kind", None) == "image_work":
            return getattr(node, "image_work_id", None)
        return None

    def load_curve_by_id(self, curve_id: str) -> None:
        """通过 Curve.id 加载所属图片并切换当前曲线。"""
        curve = project_manager.get_curve(curve_id)
        if curve is None:
            return
        image_id = self._find_image_id_for_curve(curve_id)
        if image_id is not None:
            self.load_image_by_id(image_id)
        self._current_curve_id = curve_id
        if image_id is not None:
            self._current_image_id = image_id
        self._refresh_export_name_suggestion(force=True)
        self._display_current_curve_on_image()
        self._update_curve_table()
        self._refresh_project_tree(show_indicator=True)

    def load_image_by_id(self, image_work_id: str) -> None:
        """通过 ImageWork.id 加载图像到查看器（供共享树双击激活调用）。"""
        resolved_image_id = self._resolve_image_work_id(image_work_id)
        if resolved_image_id is None:
            return
        img = project_manager.get_image(resolved_image_id)
        if img is None:
            return
        path = project_manager.get_image_path(resolved_image_id)
        if path:
            self._image_viewer.load_image(path)
        self._current_image_id = resolved_image_id
        if img.curves:
            self._current_curve_id = img.curves[0].id
            self._refresh_export_name_suggestion()
            self._display_current_curve_on_image()
        else:
            self._current_curve_id = None
            self._refresh_export_name_suggestion()
            self._image_viewer.clear_curves()
        self._update_curve_table()
        self._refresh_project_tree(show_indicator=True)

    def update_theme_colors(self):
        """主题切换后重新应用颜色到所有使用 text_color/placeholder_color/border_color 的组件"""
        from ui.theme import text_color, placeholder_color
        from PySide6.QtWidgets import QFrame
        from qfluentwidgets import BodyLabel

        tc = text_color()
        pc = placeholder_color()
        bc = self._border_color()

        # 重新设置已知的 self._ 成员
        known_placeholder = [
            getattr(self, "_status_label", None),
            getattr(self, "_point_size_value_label", None),
            getattr(self, "_select_area_value_label", None),
            getattr(self, "_eraser_size_value_label", None),
            getattr(self, "_assist_status_label", None),
        ]
        for lbl in known_placeholder:
            if lbl and lbl.styleSheet():
                ss = lbl.styleSheet()
                # 替换颜色值（统一使用当前 placeholder 颜色）
                import re as _re
                ss = _re.sub(r'color:\s*#[0-9a-fA-F]{3,8}', f'color: {pc}', ss)
                lbl.setStyleSheet(ss)

        # 扫描所有子 BodyLabel（section title 类型，font-weight:bold 样式）
        for lbl in self.findChildren(BodyLabel):
            ss = lbl.styleSheet()
            if 'font-weight: bold' in ss and 'color:' in ss:
                import re as _re
                ss = _re.sub(r'color:\s*#[0-9a-fA-F]{3,8}', f'color: {tc}', ss)
                lbl.setStyleSheet(ss)

        # 扫描分隔线
        for frame in self.findChildren(QFrame):
            ss = frame.styleSheet()
            if 'background-color:' in ss and 'border' not in ss:
                frame.setStyleSheet(f"background-color: {bc};")
            elif 'color:' in ss and frame.frameShape() in (QFrame.Shape.HLine, QFrame.Shape.VLine):
                frame.setStyleSheet(f"color: {bc};")

        # 更新工具栏中无 bold 的普通 BodyLabel（大小/步长/橡皮 等说明文字）
        for lbl in self._viewer_toolbar.findChildren(BodyLabel):
            ss = lbl.styleSheet()
            if 'font-size: 10px' not in ss and 'font-weight' not in ss:
                lbl.setStyleSheet(f"color: {tc};")

    # ==================== 校准和曲线提取 ====================

    def _on_calibration_complete(self, calibration_overlay):
        if self._current_curve_id is None:
            return

        curve_before = project_manager.get_curve(self._current_curve_id)
        old_calibration = curve_before.calibration.model_dump() if (curve_before and curve_before.calibration) else None
        old_x_actual = list(curve_before.x_actual) if curve_before else []
        old_y_actual = list(curve_before.y_actual) if curve_before else []

        # 根据坐标类型选择对应的对话框
        coord_type = calibration_overlay.coord_type
        if coord_type == "polar":
            dialog = PolarCalibrationDialog(calibration_overlay, self)
        else:
            dialog = CalibrationDialog(calibration_overlay, coord_type, self)

        if dialog.exec():
            data = dialog.get_calibration_data()

            if coord_type == "polar":
                calib_data = CalibrationData(
                    x_start=(calibration_overlay.x_start.x(), calibration_overlay.x_start.y()),
                    x_end=(calibration_overlay.x_end.x(), calibration_overlay.x_end.y()),
                    coord_type="polar",
                    angle_A=data["angle_A"],
                    radius_A=data["radius_A"]
                )
            else:
                calib_data = CalibrationData(
                    x_start=(calibration_overlay.x_start.x(), calibration_overlay.x_start.y()),
                    x_end=(calibration_overlay.x_end.x(), calibration_overlay.x_end.y()),
                    y_start=(calibration_overlay.y_start.x(), calibration_overlay.y_start.y()),
                    y_end=(calibration_overlay.y_end.x(), calibration_overlay.y_end.y()),
                    x_range=data["x_range"],
                    y_range=data["y_range"],
                    coord_type=data["coord_type"]
                )

            # 更新校准
            project_manager.update_curve_calibration(self._current_curve_id, calib_data)

            # 重新计算实际坐标
            curve = project_manager.get_curve(self._current_curve_id)
            if curve and curve.x_data:
                x_actual = []
                y_actual = []
                for px, py in zip(curve.x_data, curve.y_data):
                    x, y = project_manager.pixel_to_actual_coords(self._current_curve_id, px, py)
                    x_actual.append(x)
                    y_actual.append(y)
                curve.x_actual = x_actual
                curve.y_actual = y_actual

            # 记录校准变更到撤销栈
            curve_after = project_manager.get_curve(self._current_curve_id)
            self._record_state("update_calibration", self._current_curve_id, {
                "old_calibration": old_calibration,
                "new_calibration": curve_after.calibration.model_dump() if (curve_after and curve_after.calibration) else None,
                "old_x_actual": old_x_actual,
                "old_y_actual": old_y_actual,
                "new_x_actual": list(curve_after.x_actual) if curve_after else [],
                "new_y_actual": list(curve_after.y_actual) if curve_after else [],
            })

            self._deactivate_all_tools()
            self._active_tool = None
            self._image_viewer.set_select_mode()
            self._status_label.setText("校准完成！")
            self._display_current_curve_on_image()
            self._update_curve_table()
            self._refresh_project_tree()
            self.project_modified.emit()

    def _on_calibration_step(self, step_type: str):
        step_hints = {
            "x_start":            "请点击设置 X 轴起点 (第1/4)",
            "x_end":              "请点击设置 X 轴终点 (第2/4)",
            "y_start":            "请点击设置 Y 轴起点 (第3/4)",
            "y_end":              "请点击设置 Y 轴终点 (第4/4)",
            "origin":             "请点击设置原点 O (第1/2)",
            "angle_radius_point": "请点击设置角度+极径参考点 A (第2/2)",
            "x_axis":             "请点击正X轴方向点",
            "y_axis":             "请点击正Y轴方向点",
            "angle_ref":          "请点击角度参考点",
            "complete":           "校准点已设置完成，请再次点击校准按钮完成校准"
        }
        self._status_label.setText(step_hints.get(step_type, ""))

    def _on_calibration_nudge(self, dx: float, dy: float):
        pass

    def _on_viewer_mouse_moved(self, px: float, py: float):
        """鼠标在图片上移动 - 更新底部状态栏坐标"""
        if not hasattr(self, '_status_coord_label'):
            return
        # 计算校准坐标（如果可用）
        if self._current_curve_id is not None:
            curve = project_manager.get_curve(self._current_curve_id)
            if curve and curve.calibration:
                try:
                    cx, cy = project_manager.pixel_to_actual_coords(self._current_curve_id, px, py)
                    self._status_coord_label.setText(f"像素: ({px:.1f}, {py:.1f})  坐标: ({cx:.4g}, {cy:.4g})")
                    return
                except Exception:
                    pass
        self._status_coord_label.setText(f"像素: ({px:.1f}, {py:.1f})")

    def _on_curve_point_moved(self, index: int, new_px: float, new_py: float):
        """曲线点被键盘微调后更新数据"""
        if self._current_curve_id is None:
            return
        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None or index >= len(curve.x_data):
            return
        # 更新像素坐标
        curve.x_data[index] = new_px
        curve.y_data[index] = new_py
        # 重新计算实际坐标
        if curve.calibration:
            x_actual, y_actual = project_manager.pixel_to_actual_coords(self._current_curve_id, new_px, new_py)
        else:
            x_actual, y_actual = new_px, new_py
        if curve.x_actual and index < len(curve.x_actual):
            curve.x_actual[index] = x_actual
            curve.y_actual[index] = y_actual
        # 直接更新 curve_items 中对应点坐标，避免刷新整个 overlay
        for item in self._image_viewer.get_curves():
            if index < len(item.points):
                item.points[index] = (new_px, new_py)
                break
        self._image_viewer.update()
        # 更新表格（仅该行）
        self._update_curve_table()
        self.project_modified.emit()

    def _on_curve_point_added(self, px: float, py: float):
        """处理曲线点添加 - 直接写入 curve.x_data"""
        if self._current_image_id is None or self._current_curve_id is None:
            return

        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None:
            return

        # 直接写入曲线数据
        curve.x_data.append(px)
        curve.y_data.append(py)

        # 计算实际坐标
        if curve.calibration:
            x_actual, y_actual = project_manager.pixel_to_actual_coords(self._current_curve_id, px, py)
        else:
            x_actual, y_actual = px, py
        curve.x_actual.append(x_actual)
        curve.y_actual.append(y_actual)

        # 记录到撤销栈（使用在 curve.x_data 中的正确索引）
        self._record_state("add_point", self._current_curve_id, {
            "index": len(curve.x_data) - 1,
            "x": px,
            "y": py,
            "x_actual": x_actual,
            "y_actual": y_actual,
        })

        # 刷新显示（同步清除 image_viewer 中的临时 _current_curve）
        self._display_current_curve_on_image()
        self._update_curve_table()
        self._status_label.setText(f"已添加 {len(curve.x_data)} 个点")
        self.project_modified.emit()

    def _on_eraser_point(self, px: float, py: float):
        """处理橡皮擦擦除点"""
        eraser_radius = self._image_viewer.get_eraser_size()
        mask = self._image_viewer.get_mask()

        # 擦除曲线点 - 批量收集后单条记录，防止多点删除时索引错位
        if self._current_curve_id is not None:
            curve = project_manager.get_curve(self._current_curve_id)
            if curve is not None and curve.x_data:
                points_to_remove = []
                for i in range(len(curve.x_data)):
                    dx = curve.x_data[i] - px
                    dy = curve.y_data[i] - py
                    if (dx * dx + dy * dy) ** 0.5 <= eraser_radius:
                        points_to_remove.append(i)

                if points_to_remove:
                    # 保存所有被删点的原始数据（保留原始索引用于恢复）
                    deleted = []
                    for i in points_to_remove:
                        deleted.append({
                            "index": i,
                            "x": curve.x_data[i],
                            "y": curve.y_data[i],
                            "x_actual": curve.x_actual[i] if curve.x_actual and i < len(curve.x_actual) else None,
                            "y_actual": curve.y_actual[i] if curve.y_actual and i < len(curve.y_actual) else None,
                        })
                    self._record_state("remove_points_batch", self._current_curve_id, {"points": deleted})

                    # 倒序删除（保持索引有效）
                    for i in sorted(points_to_remove, reverse=True):
                        del curve.x_data[i]
                        del curve.y_data[i]
                        if curve.x_actual and i < len(curve.x_actual):
                            del curve.x_actual[i]
                            del curve.y_actual[i]

                    self._display_current_curve_on_image()
                    self._update_curve_table()
                    self.project_modified.emit()

        # 擦除蒙版多边形 - 记录用于撤销
        if mask and mask.enabled and mask.polygons:
            polygon_to_remove = mask.get_polygon_at_point(px, py)
            if polygon_to_remove >= 0:
                self._record_state("remove_mask", None, {
                    "polygon": list(mask.polygons[polygon_to_remove])
                })
                del mask.polygons[polygon_to_remove]
                if not mask.polygons:
                    mask.enabled = False
                self._image_viewer.update()
                self._status_label.setText(f"蒙版区域: {len(mask.polygons)} 个")
                self.project_modified.emit()

    def _on_toggle_eraser_mode(self):
        """切换橡皮擦模式"""
        if self._active_tool == "extract":
            self._on_tool_clicked("eraser")
        elif self._active_tool == "eraser":
            self._on_tool_clicked("extract")

    def _on_mask_changed(self):
        """蒙版改变时的处理"""
        mask = self._image_viewer.get_mask()
        if mask and mask.enabled:
            self._status_label.setText(f"蒙版区域: {len(mask.polygons)} 个")
        self.project_modified.emit()

    def _on_mask_about_to_add(self, polygon):
        """蒙版即将添加时记录撤销信息"""
        self._record_state("add_mask", None, {"polygon": list(polygon)})

    def _save_extracted_curve(self):
        """保存提取的曲线点（点已在 _on_curve_point_added 中直接写入，此方法仅做状态清理）"""
        self._current_curve_points = []
        if self._current_curve_id:
            self._display_current_curve_on_image()
            self._update_curve_table()
            self._refresh_project_tree()
            self.project_modified.emit()

    def _on_sort_by_x(self):
        """按X坐标排序当前曲线"""
        if self._current_curve_id is None:
            return
        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None:
            return

        # 先保存当前提取的曲线点（如果有）
        # （点已实时写入，无需保存）
        # 如果曲线没有数据，直接返回
        if not curve.x_data:
            return

        # 保存校准数据
        saved_calibration = curve.calibration

        # 获取排序后的索引
        indices = sorted(range(len(curve.x_data)), key=lambda i: curve.x_data[i])

        curve.x_data = [curve.x_data[i] for i in indices]
        curve.y_data = [curve.y_data[i] for i in indices]
        if curve.x_actual and curve.y_actual:
            curve.x_actual = [curve.x_actual[i] for i in indices]
            curve.y_actual = [curve.y_actual[i] for i in indices]

        # 先应用校准，再显示曲线
        if saved_calibration:
            self._apply_calibration_to_viewer(saved_calibration)
        self._display_current_curve_on_image()
        self._update_curve_table()
        self.project_modified.emit()

    def _on_sort_by_y(self):
        """按Y坐标排序当前曲线"""
        if self._current_curve_id is None:
            return
        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None:
            return

        # 保存校准数据
        saved_calibration = curve.calibration

        # 获取排序后的索引
        indices = sorted(range(len(curve.y_data)), key=lambda i: curve.y_data[i])

        curve.x_data = [curve.x_data[i] for i in indices]
        curve.y_data = [curve.y_data[i] for i in indices]
        if curve.x_actual and curve.y_actual:
            curve.x_actual = [curve.x_actual[i] for i in indices]
            curve.y_actual = [curve.y_actual[i] for i in indices]

        # 先应用校准，再显示曲线
        if saved_calibration:
            self._apply_calibration_to_viewer(saved_calibration)
        self._display_current_curve_on_image()
        self._update_curve_table()
        self.project_modified.emit()

    def _on_clear_all_points(self):
        """清除当前曲线的所有点"""
        if self._current_curve_id is None:
            return
        curve = project_manager.get_curve(self._current_curve_id)
        if curve is None or not curve.x_data:
            return

        # 记录状态用于撤销（包含完整点数据）
        self._record_state("clear_curve", self._current_curve_id, {
            "points": list(zip(curve.x_data, curve.y_data)),
            "x_actual": list(curve.x_actual) if curve.x_actual else [],
            "y_actual": list(curve.y_actual) if curve.y_actual else [],
        })

        # 清除所有点
        curve.x_data = []
        curve.y_data = []
        curve.x_actual = []
        curve.y_actual = []

        # 重新显示
        self._display_current_curve_on_image()
        self._update_curve_table()
        self.project_modified.emit()
        self._status_label.setText("已清除所有点")

    def _record_state(self, action_type: str, curve_id: Optional[str] = None, data: Optional[dict[str, Any]] = None):
        """记录操作到撤销栈

        精细化操作记录：
        - add_point: 添加点 - 记录点数据
        - remove_point: 删除点 - 记录点和索引
        - clear_curve: 清除曲线 - 记录所有点
        - add_mask: 添加蒙版 - 记录蒙版多边形
        - remove_mask: 删除蒙版 - 记录蒙版多边形
        """
        if self._is_undo_redo:
            return

        if curve_id is None:
            curve_id = self._current_curve_id

        # 构建操作记录
        state = {
            "type": action_type,
            "curve_id": curve_id,
            "data": data
        }

        self._undo_stack.append(state)
        # 清空重做栈
        self._redo_stack.clear()

        # 限制历史记录数量
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)

    def _undo(self):
        """撤销上一个操作"""
        if not self._undo_stack:
            self._status_label.setText("没有可撤销的操作")
            return

        self._is_undo_redo = True
        state = self._undo_stack.pop()

        action_type = state["type"]
        curve_id = state.get("curve_id")
        data = state.get("data") or {}
        curve = project_manager.get_curve(curve_id) if curve_id else None

        if action_type == "add_point":
            # 撤销添加点 = 从 curve.x_data 指定索引处删除
            if curve and curve.x_data:
                idx = data.get("index", len(curve.x_data) - 1)
                idx = min(idx, len(curve.x_data) - 1)
                self._redo_stack.append({
                    "type": "add_point",
                    "curve_id": curve_id,
                    "data": {
                        "index": idx,
                        "x": curve.x_data[idx],
                        "y": curve.y_data[idx],
                        "x_actual": curve.x_actual[idx] if curve.x_actual and idx < len(curve.x_actual) else None,
                        "y_actual": curve.y_actual[idx] if curve.y_actual and idx < len(curve.y_actual) else None,
                    }
                })
                del curve.x_data[idx]
                del curve.y_data[idx]
                if curve.x_actual and idx < len(curve.x_actual):
                    del curve.x_actual[idx]
                    del curve.y_actual[idx]

        elif action_type == "remove_points_batch":
            # 撤销批量删除 = 按原始索引升序恢复（逐个 insert 方式正确还原位置）
            if curve and data.get("points"):
                self._redo_stack.append({
                    "type": "remove_points_batch",
                    "curve_id": curve_id,
                    "data": {"points": data["points"]},
                })
                for pt in sorted(data["points"], key=lambda p: p["index"]):
                    idx = pt["index"]
                    curve.x_data.insert(idx, pt["x"])
                    curve.y_data.insert(idx, pt["y"])
                    if pt.get("x_actual") is not None:
                        if not curve.x_actual:
                            curve.x_actual = []
                            curve.y_actual = []
                        curve.x_actual.insert(idx, pt["x_actual"])
                        curve.y_actual.insert(idx, pt["y_actual"])

        elif action_type == "remove_point":
            # 向后兼容旧记录的单点删除
            if curve:
                self._redo_stack.append({
                    "type": "remove_point",
                    "curve_id": curve_id,
                    "data": data,
                })
                idx = data["index"]
                curve.x_data.insert(idx, data["x"])
                curve.y_data.insert(idx, data["y"])
                if data.get("x_actual") is not None:
                    if not curve.x_actual:
                        curve.x_actual = []
                        curve.y_actual = []
                    curve.x_actual.insert(idx, data["x_actual"])
                    curve.y_actual.insert(idx, data["y_actual"])

        elif action_type == "clear_curve":
            # 撤销清除 = 恢复所有点
            if curve and data.get("points"):
                self._redo_stack.append({
                    "type": "clear_curve",
                    "curve_id": curve_id,
                    "data": {
                        "points": data["points"],  # 保存原始点供 redo 再次清除后仍可 undo
                        "x_actual": data.get("x_actual", []),
                        "y_actual": data.get("y_actual", []),
                    },
                })
                curve.x_data = [p[0] for p in data["points"]]
                curve.y_data = [p[1] for p in data["points"]]
                curve.x_actual = list(data.get("x_actual", []))
                curve.y_actual = list(data.get("y_actual", []))

        elif action_type == "remove_mask":
            mask = self._image_viewer.get_mask()
            if mask and data.get("polygon") is not None:
                self._redo_stack.append({"type": "remove_mask", "curve_id": None, "data": {"polygon": data["polygon"]}})
                mask.polygons.append(data["polygon"])
                mask.enabled = True

        elif action_type == "add_mask":
            mask = self._image_viewer.get_mask()
            if mask and mask.polygons:
                self._redo_stack.append({"type": "add_mask", "curve_id": None, "data": {"polygon": mask.polygons[-1]}})
                del mask.polygons[-1]
                if not mask.polygons:
                    mask.enabled = False

        elif action_type == "update_calibration":
            if curve:
                self._redo_stack.append({
                    "type": "update_calibration",
                    "curve_id": curve_id,
                    "data": data,
                })
                old_cal = data.get("old_calibration")
                curve.calibration = CalibrationData(**old_cal) if old_cal else None
                curve.x_actual = list(data.get("old_x_actual", []))
                curve.y_actual = list(data.get("old_y_actual", []))

        # 更新显示
        if curve:
            self._display_current_curve_on_image()
            self._update_curve_table()
        self._image_viewer.update()
        self.project_modified.emit()
        self._is_undo_redo = False
        self._status_label.setText("已撤销")

    def _redo(self):
        """重做上一个撤销的操作"""
        if not self._redo_stack:
            self._status_label.setText("没有可重做的操作")
            return

        self._is_undo_redo = True
        state = self._redo_stack.pop()

        action_type = state["type"]
        curve_id = state.get("curve_id")
        data = state.get("data") or {}
        curve = project_manager.get_curve(curve_id) if curve_id else None

        if action_type == "add_point":
            # 重做添加点 = 在指定索引位置重新插入
            if curve:
                idx = data.get("index", len(curve.x_data))
                self._undo_stack.append({
                    "type": "add_point",
                    "curve_id": curve_id,
                    "data": data,
                })
                curve.x_data.insert(idx, data["x"])
                curve.y_data.insert(idx, data["y"])
                if data.get("x_actual") is not None:
                    if not curve.x_actual:
                        curve.x_actual = []
                        curve.y_actual = []
                    curve.x_actual.insert(idx, data["x_actual"])
                    curve.y_actual.insert(idx, data["y_actual"])

        elif action_type == "remove_points_batch":
            # 重做批量删除 = 按原始索引倒序删除
            if curve and data.get("points"):
                self._undo_stack.append({
                    "type": "remove_points_batch",
                    "curve_id": curve_id,
                    "data": {"points": data["points"]},
                })
                for pt in sorted(data["points"], key=lambda p: p["index"], reverse=True):
                    idx = pt["index"]
                    if idx < len(curve.x_data):
                        del curve.x_data[idx]
                        del curve.y_data[idx]
                        if curve.x_actual and idx < len(curve.x_actual):
                            del curve.x_actual[idx]
                            del curve.y_actual[idx]

        elif action_type == "remove_point":
            # 向后兼容旧记录的单点删除
            if curve:
                self._undo_stack.append({
                    "type": "remove_point",
                    "curve_id": curve_id,
                    "data": data,
                })
                idx = data["index"]
                if idx < len(curve.x_data):
                    del curve.x_data[idx]
                    del curve.y_data[idx]
                    if curve.x_actual and idx < len(curve.x_actual):
                        del curve.x_actual[idx]
                        del curve.y_actual[idx]

        elif action_type == "clear_curve":
            # 重做清除 = 保存当前（恢复后的）状态到撤销栈，然后再次清除
            if curve:
                self._undo_stack.append({
                    "type": "clear_curve",
                    "curve_id": curve_id,
                    "data": {
                        "points": list(zip(curve.x_data, curve.y_data)) if curve.x_data else [],
                        "x_actual": list(curve.x_actual) if curve.x_actual else [],
                        "y_actual": list(curve.y_actual) if curve.y_actual else [],
                    },
                })
                curve.x_data = []
                curve.y_data = []
                curve.x_actual = []
                curve.y_actual = []

        elif action_type == "remove_mask":
            mask = self._image_viewer.get_mask()
            if mask and data.get("polygon") is not None:
                self._undo_stack.append({"type": "remove_mask", "curve_id": None, "data": {"polygon": data["polygon"]}})
                for i, poly in enumerate(mask.polygons):
                    if poly == data["polygon"]:
                        del mask.polygons[i]
                        break
                if not mask.polygons:
                    mask.enabled = False

        elif action_type == "add_mask":
            mask = self._image_viewer.get_mask()
            if mask and data.get("polygon") is not None:
                self._undo_stack.append({"type": "add_mask", "curve_id": None, "data": {"polygon": data["polygon"]}})
                mask.polygons.append(data["polygon"])
                mask.enabled = True

        elif action_type == "update_calibration":
            if curve:
                self._undo_stack.append({
                    "type": "update_calibration",
                    "curve_id": curve_id,
                    "data": data,
                })
                new_cal = data.get("new_calibration")
                curve.calibration = CalibrationData(**new_cal) if new_cal else None
                curve.x_actual = list(data.get("new_x_actual", []))
                curve.y_actual = list(data.get("new_y_actual", []))

        # 更新显示
        if curve:
            self._display_current_curve_on_image()
            self._update_curve_table()
        self._image_viewer.update()
        self.project_modified.emit()
        self._is_undo_redo = False
        self._status_label.setText("已重做")

    @property
    def _current_image_id(self):
        return self._workspace_state.current_image_id

    @_current_image_id.setter
    def _current_image_id(self, value):
        self._workspace_state.current_image_id = value

    @property
    def _current_curve_id(self):
        return self._workspace_state.current_curve_id

    @_current_curve_id.setter
    def _current_curve_id(self, value):
        self._workspace_state.current_curve_id = value

    @property
    def _export_target_kind(self):
        return self._workspace_state.export_target_kind

    @_export_target_kind.setter
    def _export_target_kind(self, value):
        self._workspace_state.export_target_kind = value

    @property
    def _export_target_id(self):
        return self._workspace_state.export_target_id

    @_export_target_id.setter
    def _export_target_id(self, value):
        self._workspace_state.export_target_id = value

    @property
    def _last_export_suggestion(self):
        return self._workspace_state.last_export_suggestion

    @_last_export_suggestion.setter
    def _last_export_suggestion(self, value):
        self._workspace_state.last_export_suggestion = value

    @property
    def _current_curve_points(self):
        return self._workspace_state.current_curve_points

    @_current_curve_points.setter
    def _current_curve_points(self, value):
        self._workspace_state.current_curve_points = value

    @property
    def _active_tool(self):
        return self._workspace_state.active_tool

    @_active_tool.setter
    def _active_tool(self, value):
        self._workspace_state.active_tool = value

    @property
    def _hidden_curves(self):
        return self._workspace_state.hidden_curves

    @_hidden_curves.setter
    def _hidden_curves(self, value):
        self._workspace_state.hidden_curves = value

    @property
    def _undo_stack(self):
        return self._workspace_state.undo_stack

    @_undo_stack.setter
    def _undo_stack(self, value):
        self._workspace_state.undo_stack = value

    @property
    def _redo_stack(self):
        return self._workspace_state.redo_stack

    @_redo_stack.setter
    def _redo_stack(self, value):
        self._workspace_state.redo_stack = value

    @property
    def _max_history(self):
        return self._workspace_state.max_history

    @_max_history.setter
    def _max_history(self, value):
        self._workspace_state.max_history = value

    @property
    def _is_undo_redo(self):
        return self._workspace_state.is_undo_redo

    @_is_undo_redo.setter
    def _is_undo_redo(self, value):
        self._workspace_state.is_undo_redo = value

    @property
    def _sampled_color(self):
        return self._workspace_state.sampled_color

    @_sampled_color.setter
    def _sampled_color(self, value):
        self._workspace_state.sampled_color = value

    @property
    def _auto_preview_points(self):
        return self._workspace_state.auto_preview_points

    @_auto_preview_points.setter
    def _auto_preview_points(self, value):
        self._workspace_state.auto_preview_points = value

    @property
    def _shape_template(self):
        return self._workspace_state.shape_template

    @_shape_template.setter
    def _shape_template(self, value):
        self._workspace_state.shape_template = value

    @property
    def _auto_mode_type_ids(self):
        return self._workspace_state.auto_mode_type_ids

    @_auto_mode_type_ids.setter
    def _auto_mode_type_ids(self, value):
        self._workspace_state.auto_mode_type_ids = value

    @property
    def _pending_digitize_field_key(self):
        return self._workspace_state.pending_digitize_field_key

    @_pending_digitize_field_key.setter
    def _pending_digitize_field_key(self, value):
        self._workspace_state.pending_digitize_field_key = value

    @property
    def _pending_digitize_field_type(self):
        return self._workspace_state.pending_digitize_field_type

    @_pending_digitize_field_type.setter
    def _pending_digitize_field_type(self, value):
        self._workspace_state.pending_digitize_field_type = value
