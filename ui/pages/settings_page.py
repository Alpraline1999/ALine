from typing import Literal, cast

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QFrame, QFormLayout, QKeySequenceEdit)
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from qfluentwidgets import (ComboBox, setTheme, Theme, CardWidget, PushButton,
    BodyLabel, SubtitleLabel, TitleLabel, SmoothScrollArea,
    LineEdit, PrimaryPushButton, InfoBar, InfoBarPosition, PlainTextEdit,
    CheckBox, FolderListSettingCard, SettingCard, SettingCardGroup, ExpandGroupSettingCard,
    Slider, SwitchSettingCard,
    FluentIcon as FIF)
from qfluentwidgets.common.config import ConfigItem, qconfig

from ui.theme import (
    accent_color,
    body_text_style_sheet,
    border_color,
    card_background_color,
    card_title_style_sheet,
    error_text_style_sheet,
    flat_status_button_style,
    install_fluent_tooltip,
    notification_parent,
    placeholder_color,
    placeholder_text_style_sheet,
    secondary_text_style_sheet,
    text_color,
    warning_color,
)
from ui.widgets.extension_panel import show_extension_load_report_dialog
from core.extension_loader import get_extension_load_status
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.widgets.focus_commit import install_click_away_focus_commit
from ui.widgets.navigation_stack import PivotStackWidget, SegmentedStackWidget
from ui.page_view_state import SettingsPageViewState
from core.shortcut_manager import shortcut_manager
from core.ui_preferences import (
    TreeNameDisplayMode,
    get_tree_name_display_mode,
    is_page_tree_focus_mode_enabled,
    set_page_tree_focus_mode_enabled,
    set_tree_name_display_mode,
)
from core.ai.providers import (
    get_provider_preset,
    list_builtin_models,
    list_provider_keys,
)


_EXTENSION_CATEGORY_TABS_MAX_HEIGHT = 60750
_EXTENSION_CATEGORY_TABS_HEIGHT_MULTIPLIER = 3


class _MutableFolderListSettingCard(FolderListSettingCard):

    def __init__(self, title: str, content: str | None, folders: list[str], *, directory: str, parent: QWidget | None = None):
        self._config_item = ConfigItem("SettingsPage", "externalExtensionDirs", list(folders or []))
        super().__init__(self._config_item, title, content or "", directory=directory, parent=parent)

    def setFolders(self, folders: list[str]) -> None:
        normalized = [str(folder).strip() for folder in folders if str(folder).strip()]
        self.folders = normalized
        qconfig.set(self.configItem, list(self.folders))
        while self.viewLayout.count():
            item = self.viewLayout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        add_folder_item = getattr(self, "_FolderListSettingCard__addFolderItem")
        for folder in self.folders:
            add_folder_item(folder)
        self._adjustViewSize()


class SettingsPage(QWidget):
    """设置页面 - 主题切换、快捷键自定义等配置"""

    shortcuts_changed = Signal()  # 快捷键保存后发出
    tree_display_mode_changed = Signal(str)
    page_tree_focus_mode_changed = Signal(bool)
    extensions_reloaded = Signal()
    project_modified = Signal()
    assets_modified = Signal()
    replay_onboarding_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._extension_height_watch_targets: list[QWidget] = []
        self._view_state = SettingsPageViewState()
        self._title_label = None
        self._theme_label = None
        self._tree_display_mode_label = None
        self._tree_display_mode_combo = None
        self._tree_display_mode_keys = ["wrap", "elide"]
        self._page_tree_focus_mode_label = None
        self._page_tree_focus_mode_card = None
        self._page_tree_focus_mode_checkbox = None
        self._page_tree_focus_mode_hint = None
        self._appearance_title = None
        self._extension_card = None
        self._builtin_extension_card = None
        self._external_extension_card = None
        self._extension_other_settings_card = None
        self._builtin_extension_management_card = None
        self._external_extension_management_card = None
        self._extension_status_card = None
        self._extension_actions_card = None
        self._extension_title = None
        self._extension_hint = None
        self._builtin_section_hint = None
        self._external_section_hint = None
        self._external_extensions_dirs_card = None
        self._external_extensions_dir_label = None
        self._external_extensions_dir_edit = None
        self._browse_external_extensions_dir_btn = None
        self._external_extensions_enabled_checkbox = None
        self._external_extension_number_decimals_card = None
        self._external_extension_number_decimals_slider = None
        self._external_extension_number_decimals_value_label = None
        self._refresh_external_extensions_btn = None
        self._builtin_extensions_enabled_checkbox = None
        self._extension_tabs = None
        self._external_extension_tabs = None
        self._extension_empty_hints: dict[str, BodyLabel] = {}
        self._extension_option_layouts: dict[str, QVBoxLayout] = {}
        self._external_extension_empty_hints: dict[str, BodyLabel] = {}
        self._external_extension_option_layouts: dict[str, QVBoxLayout] = {}
        self._builtin_extension_checkboxes: dict[str, CheckBox] = {}
        self._builtin_extension_checkbox_groups: dict[str, list[CheckBox]] = {}
        self._external_extension_checkboxes: dict[str, CheckBox] = {}
        self._external_extension_checkbox_groups: dict[str, list[CheckBox]] = {}
        self._extension_specs_by_source: dict[str, list[dict]] = {"builtin": [], "external": []}
        self._save_extension_settings_btn = None
        self._onboarding_label = None
        self._onboarding_hint = None
        self._replay_onboarding_btn = None
        self._lang_title = None
        self._lang_placeholder = None
        self._shortcuts_title = None
        self._appearance_card = None
        self._lang_card = None
        self._shortcuts_card = None
        self._shortcuts_editor_card = None
        self._tmpl_card = None
        self._tmpl_list = None
        self.theme_combo = None
        self._shortcut_filter_edit = None
        self._shortcut_edits: dict[str, QKeySequenceEdit] = {}
        self._shortcut_rows: dict[str, QWidget] = {}
        self._shortcut_labels: list[BodyLabel] = []
        self._conflict_labels: dict[str, BodyLabel] = {}  # action -> red warning label
        self._provider_keys = list_provider_keys()
        self._active_provider_key = (
            "openai_compatible"
            if "openai_compatible" in self._provider_keys
            else (self._provider_keys[0] if self._provider_keys else "openai_compatible")
        )
        self.setup_ui()

    @staticmethod
    def _tab_content_margins() -> tuple[int, int, int, int]:
        return (14, 12, 14, 12)

    def _notification_parent(self) -> QWidget:
        parent = notification_parent(self)
        return parent if isinstance(parent, QWidget) else self

    def setup_ui(self):
        tabs = PivotStackWidget(self)
        self._tabs = tabs

        tabs.addTab(self._build_general_tab(), "常规")
        tabs.addTab(self._build_extensions_tab(), "扩展")
        tabs.addTab(self._build_shortcuts_tab(), "快捷键")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(tabs)

        self._load_ai_config()
        self._load_extension_settings()
        self._schedule_extension_category_tab_heights_refresh()
        self._refresh_ai_tools_panel()
        self._install_tooltip_filters()
        self._click_away_focus_commit = install_click_away_focus_commit(self)

    def _install_tooltip_filters(self) -> None:
        for widget in self.findChildren(QWidget):
            install_fluent_tooltip(widget, delay=400)

    def _shortcut_edit_style(self, *, focused: bool) -> str:
        border = accent_color() if focused else border_color()
        border_width = 2 if focused else 1
        background = card_background_color()
        return (
            f"background: {background}; color: {text_color()};"
            f" border: {border_width}px solid {border}; border-radius: 6px; padding: 3px;"
        )

    def _apply_shortcut_edit_style(self, edit: QKeySequenceEdit, *, focused: bool) -> None:
        edit.setStyleSheet(self._shortcut_edit_style(focused=focused))

    def eventFilter(self, watched, event):
        if isinstance(watched, QKeySequenceEdit) and watched in self._shortcut_edits.values():
            if event.type() == QEvent.Type.FocusIn:
                self._apply_shortcut_edit_style(watched, focused=True)
            elif event.type() == QEvent.Type.FocusOut:
                self._apply_shortcut_edit_style(watched, focused=False)
        if any(watched is target for target in self._extension_height_watch_targets):
            if event.type() in {QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.LayoutRequest}:
                self._schedule_extension_category_tab_heights_refresh()
        return super().eventFilter(watched, event)

    def _register_extension_height_watch_target(self, widget: QWidget | None) -> None:
        if widget is None or any(widget is target for target in self._extension_height_watch_targets):
            return
        self._extension_height_watch_targets.append(widget)
        widget.installEventFilter(self)

    def _schedule_extension_category_tab_heights_refresh(self) -> None:
        if self._view_state.extension_height_refresh_pending:
            return
        self._view_state.extension_height_refresh_pending = True
        QTimer.singleShot(0, self._refresh_extension_category_tab_heights)

    @staticmethod
    def _apply_card_layout_metrics(layout) -> None:
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

    def _apply_shortcut_filter_style(self) -> None:
        if self._shortcut_filter_edit is None:
            return
        self._shortcut_filter_edit.setFixedHeight(36)
        self._shortcut_filter_edit.setStyleSheet(
            f"background: {card_background_color()}; color: {text_color()};"
            f" border: 1px solid {accent_color()}; border-radius: 8px; padding: 4px 8px;"
        )

    def _ai_config_controls_ready(self) -> bool:
        return all(
            hasattr(self, name) and getattr(self, name) is not None
            for name in (
                "_ai_provider_combo",
                "_ai_url_edit",
                "_ai_key_edit",
                "_ai_model_edit",
                "_ai_timeout_edit",
                "_ai_temperature_edit",
                "_ai_top_p_edit",
                "_ai_max_tokens_edit",
                "_ai_system_prompt_edit",
                "_ai_ollama_keep_alive_edit",
                "_ai_ollama_num_ctx_edit",
                "_ai_provider_hint",
                "_ai_refresh_models_btn",
                "_ai_model_preset_combo",
            )
        )

    def _ai_tools_controls_ready(self) -> bool:
        return all(
            hasattr(self, name) and getattr(self, name) is not None
            for name in (
                "_ai_tools_project_label",
                "_ai_tools_summary_label",
                "_ai_tool_selector",
                "_ai_tool_detail_name",
                "_ai_tool_detail_type",
                "_ai_tool_detail_desc",
                "_ai_tool_edit_btn",
                "_ai_tool_delete_btn",
            )
        )

    @staticmethod
    def _attach_setting_card_control(card: SettingCard, widget: QWidget, *, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight) -> None:
        card.hBoxLayout.addWidget(widget, 0, alignment | Qt.AlignmentFlag.AlignVCenter)

    @staticmethod
    def _build_setting_card_row(parent: QWidget, *widgets: QWidget) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for widget in widgets:
            layout.addWidget(widget)
        return row

    def _build_extension_category_tabs(
        self,
        parent: QWidget,
        *,
        empty_hints: dict[str, BodyLabel],
        option_layouts: dict[str, QVBoxLayout],
    ) -> SegmentedStackWidget:
        tabs = SegmentedStackWidget(parent)
        tabs.setMaximumHeight(_EXTENSION_CATEGORY_TABS_MAX_HEIGHT)
        for category, label in (("plot", "绘图扩展"), ("processing", "处理扩展"), ("analysis", "分析扩展"), ("digitize", "数字化扩展")):
            page = QWidget(parent)
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(0, 0, 0, 0)
            page_layout.setSpacing(6)
            empty_hint = BodyLabel(f"当前未发现{label}。", page)
            empty_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
            page_layout.addWidget(empty_hint)
            empty_hints[category] = empty_hint

            options_scroll = SmoothScrollArea(page)
            options_scroll.setWidgetResizable(True)
            options_scroll.setFrameShape(QFrame.Shape.NoFrame)
            options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            options_scroll.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

            options_widget = QWidget(options_scroll)
            options_layout = QVBoxLayout(options_widget)
            options_layout.setContentsMargins(0, 0, 0, 0)
            options_layout.setSpacing(6)
            options_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            options_scroll.setWidget(options_widget)
            page_layout.addWidget(options_scroll, 1)
            option_layouts[category] = options_layout

            tabs.addTab(page, label, route_key=category)
        tabs.setMinimumHeight(max(tabs.sizeHint().height() * _EXTENSION_CATEGORY_TABS_HEIGHT_MULTIPLIER, tabs.navigationWidget.sizeHint().height()))
        return tabs

    def _build_general_tab(self) -> QWidget:
        outer = SmoothScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(*self._tab_content_margins())
        outer.setWidget(content)

        appearance_group = SettingCardGroup("外观", content)
        self._appearance_card = appearance_group
        self._appearance_title = appearance_group.titleLabel
        self._appearance_title.setStyleSheet(card_title_style_sheet(font_size=18))

        theme_card = SettingCard(FIF.BRUSH, "主题", "切换浅色、深色或跟随系统。", appearance_group)
        self._theme_label = theme_card.titleLabel
        self._theme_label.setStyleSheet(body_text_style_sheet())
        self.theme_combo = ComboBox(theme_card)
        self.theme_combo.setMinimumWidth(148)
        self.theme_combo.addItems(["浅色", "深色", "跟随系统"])
        self.theme_combo.setCurrentIndex(2)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        self._attach_setting_card_control(theme_card, self.theme_combo)
        appearance_group.addSettingCard(theme_card)

        tree_mode_card = SettingCard(FIF.INFO, "项目树长名称显示", "控制项目树长名称使用自动换行还是省略显示。", appearance_group)
        self._tree_display_mode_label = tree_mode_card.titleLabel
        self._tree_display_mode_label.setStyleSheet(body_text_style_sheet())
        self._tree_display_mode_combo = ComboBox(tree_mode_card)
        self._tree_display_mode_combo.setMinimumWidth(148)
        self._tree_display_mode_combo.addItems(["自动换行", "部分隐藏"])
        current_mode = get_tree_name_display_mode()
        current_index = 1 if current_mode == "elide" else 0
        self._tree_display_mode_combo.setCurrentIndex(current_index)
        self._tree_display_mode_combo.currentIndexChanged.connect(self._on_tree_display_mode_changed)
        self._attach_setting_card_control(tree_mode_card, self._tree_display_mode_combo)
        appearance_group.addSettingCard(tree_mode_card)

        focus_mode_card = SwitchSettingCard(
            FIF.INFO,
            "项目树页面专注模式",
            "开启后，功能页中的共享项目树只显示当前页面直接相关的节点。",
            parent=appearance_group,
        )
        self._page_tree_focus_mode_card = focus_mode_card
        self._page_tree_focus_mode_checkbox = focus_mode_card
        self._page_tree_focus_mode_label = focus_mode_card.titleLabel
        self._page_tree_focus_mode_label.setStyleSheet(body_text_style_sheet())
        self._page_tree_focus_mode_hint = focus_mode_card.contentLabel
        self._page_tree_focus_mode_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        focus_mode_card.setChecked(is_page_tree_focus_mode_enabled())
        focus_mode_card.checkedChanged.connect(self._on_page_tree_focus_mode_changed)
        appearance_group.addSettingCard(focus_mode_card)

        onboarding_card = SettingCard(
            FIF.HELP,
            "新手引导",
            "点击后会重新播放主页引导，并重置数据管理、处理、可视化、分析和图片数字化页面的 TeachingTip 状态。",
            appearance_group,
        )
        self._onboarding_label = onboarding_card.titleLabel
        self._onboarding_label.setStyleSheet(body_text_style_sheet())
        self._onboarding_hint = onboarding_card.contentLabel
        self._onboarding_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        self._replay_onboarding_btn = PushButton("重新显示引导", onboarding_card)
        self._replay_onboarding_btn.clicked.connect(self.replay_onboarding_requested.emit)
        self._attach_setting_card_control(onboarding_card, self._replay_onboarding_btn)
        appearance_group.addSettingCard(onboarding_card)
        layout.addWidget(appearance_group)

        layout.addStretch()
        return outer

    def _build_extensions_tab(self) -> QWidget:
        outer = SmoothScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(*self._tab_content_margins())
        outer.setWidget(content)

        extension_group = SettingCardGroup("扩展", content)
        self._extension_card = extension_group
        self._extension_title = extension_group.titleLabel
        self._extension_title.setStyleSheet(card_title_style_sheet(font_size=18))
        self._extension_status_card = SettingCard(FIF.INFO, "扩展状态", "查看当前扩展加载情况与失败详情。", extension_group)
        self._extension_status_summary_btn = PushButton("", self._extension_status_card)
        self._extension_status_summary_btn.setFlat(True)
        self._extension_status_summary_btn.clicked.connect(self._show_extension_status_details)
        self._attach_setting_card_control(self._extension_status_card, self._extension_status_summary_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        extension_group.addSettingCard(self._extension_status_card)

        self._extension_actions_card = SettingCard(FIF.SYNC, "应用扩展设置", "保存当前启用状态与目录配置，并重新加载扩展。", extension_group)
        self._save_extension_settings_btn = PrimaryPushButton("保存并重载扩展", self._extension_actions_card)
        self._save_extension_settings_btn.clicked.connect(self._save_extension_settings)
        self._attach_setting_card_control(self._extension_actions_card, self._save_extension_settings_btn)
        extension_group.addSettingCard(self._extension_actions_card)
        layout.addWidget(extension_group)

        self._builtin_extension_card = SettingCardGroup("内置扩展", content)
        self._builtin_extension_card.titleLabel.setStyleSheet(card_title_style_sheet(font_size=18))
        self._builtin_extensions_enabled_checkbox = SwitchSettingCard(
            FIF.DOWNLOAD,
            "启用内置扩展",
            "关闭后保留内置扩展配置，但不参与加载。",
            parent=self._builtin_extension_card,
        )
        self._builtin_extensions_enabled_checkbox.titleLabel.setStyleSheet(body_text_style_sheet())
        self._builtin_extensions_enabled_checkbox.contentLabel.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        self._builtin_extensions_enabled_checkbox.checkedChanged.connect(self._on_builtin_extensions_enabled_changed)
        self._extension_hint = self._builtin_extensions_enabled_checkbox.contentLabel
        self._builtin_extension_card.addSettingCard(self._builtin_extensions_enabled_checkbox)
        self._builtin_extension_management_card = ExpandGroupSettingCard(
            FIF.DOWNLOAD,
            "扩展管理",
            "按类别管理内置扩展的启用状态。",
            self._builtin_extension_card,
        )
        self._builtin_extension_management_card.setExpand(False)
        self._extension_tabs = self._build_extension_category_tabs(
            self._builtin_extension_management_card,
            empty_hints=self._extension_empty_hints,
            option_layouts=self._extension_option_layouts,
        )
        self._builtin_extension_management_card.addGroupWidget(self._extension_tabs)
        self._builtin_extension_card.addSettingCard(self._builtin_extension_management_card)
        self._register_extension_height_watch_target(self._builtin_extension_management_card)
        self._register_extension_height_watch_target(self._extension_tabs)
        layout.addWidget(self._builtin_extension_card)

        self._external_extension_card = SettingCardGroup("外部扩展", content)
        self._external_extension_card.titleLabel.setStyleSheet(card_title_style_sheet(font_size=18))
        self._external_extensions_enabled_checkbox = SwitchSettingCard(
            FIF.FOLDER,
            "启用外部扩展",
            "关闭后保留目录配置，但不加载外部扩展。",
            parent=self._external_extension_card,
        )
        self._external_extensions_enabled_checkbox.titleLabel.setStyleSheet(body_text_style_sheet())
        self._external_extensions_enabled_checkbox.contentLabel.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        self._external_extensions_enabled_checkbox.checkedChanged.connect(self._on_external_extensions_enabled_changed)
        self._external_extension_card.addSettingCard(self._external_extensions_enabled_checkbox)
        self._external_extensions_dirs_card = _MutableFolderListSettingCard(
            "外部扩展目录",
            "可添加多个文件夹；保存后会统一扫描并重载。",
            [],
            directory="~/.config/aline/extensions",
            parent=self._external_extension_card,
        )
        self._external_extension_card.addSettingCard(self._external_extensions_dirs_card)

        external_refresh_card = SettingCard(
            FIF.SYNC,
            "刷新外部扩展扫描",
            "按当前目录配置重新探测外部扩展，不会修改保存设置。",
            self._external_extension_card,
        )
        self._refresh_external_extensions_btn = PushButton("立即刷新", external_refresh_card)
        self._refresh_external_extensions_btn.clicked.connect(self._refresh_external_extension_specs)
        self._attach_setting_card_control(external_refresh_card, self._refresh_external_extensions_btn)
        self._external_extension_card.addSettingCard(external_refresh_card)
        self._external_extension_management_card = ExpandGroupSettingCard(
            FIF.FOLDER,
            "扩展管理",
            "按类别管理外部扩展的启用状态。",
            self._external_extension_card,
        )
        self._external_extension_management_card.setExpand(False)
        self._external_extension_tabs = self._build_extension_category_tabs(
            self._external_extension_management_card,
            empty_hints=self._external_extension_empty_hints,
            option_layouts=self._external_extension_option_layouts,
        )
        self._external_extension_management_card.addGroupWidget(self._external_extension_tabs)
        self._external_extension_card.addSettingCard(self._external_extension_management_card)
        self._register_extension_height_watch_target(self._external_extension_management_card)
        self._register_extension_height_watch_target(self._external_extension_tabs)
        layout.addWidget(self._external_extension_card)

        self._extension_other_settings_card = SettingCardGroup("其他设置", content)
        self._extension_other_settings_card.titleLabel.setStyleSheet(card_title_style_sheet(font_size=18))
        self._external_extension_number_decimals_card = SettingCard(
            FIF.INFO,
            "浮点参数显示小数位",
            "控制扩展 number 参数使用 DoubleSpinBox 时默认显示的小数位数。",
            self._extension_other_settings_card,
        )
        decimals_slider = Slider(Qt.Orientation.Horizontal, self._external_extension_number_decimals_card)
        decimals_slider.setRange(0, 12)
        decimals_slider.setSingleStep(1)
        decimals_slider.setPageStep(1)
        decimals_slider.setMinimumWidth(132)
        decimals_slider.valueChanged.connect(self._on_external_extension_number_decimals_changed)
        self._external_extension_number_decimals_slider = decimals_slider
        decimals_value = BodyLabel("6", self._external_extension_number_decimals_card)
        decimals_value.setStyleSheet(secondary_text_style_sheet(font_size=12))
        decimals_value.setMinimumWidth(24)
        self._external_extension_number_decimals_value_label = decimals_value
        decimals_row = self._build_setting_card_row(self._external_extension_number_decimals_card, decimals_slider, decimals_value)
        decimals_row_layout = cast(QHBoxLayout, decimals_row.layout())
        if decimals_row_layout is not None:
            decimals_row_layout.setStretch(0, 1)
        self._attach_setting_card_control(self._external_extension_number_decimals_card, decimals_row)
        self._extension_other_settings_card.addSettingCard(self._external_extension_number_decimals_card)
        layout.addWidget(self._extension_other_settings_card)

        layout.addStretch()
        return outer

    def _build_shortcuts_tab(self) -> QWidget:
        outer = SmoothScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(*self._tab_content_margins())
        outer.setWidget(content)

        self._shortcuts_card = SettingCardGroup("快捷键", content)
        self._shortcuts_title = self._shortcuts_card.titleLabel
        self._shortcuts_title.setStyleSheet(card_title_style_sheet(font_size=18))

        sc_content = QWidget(self._shortcuts_card)
        sc_form = QFormLayout(sc_content)
        sc_form.setSpacing(6)
        sc_form.setContentsMargins(0, 4, 0, 4)

        from ui.theme import card_background_color, border_color
        from PySide6.QtGui import QKeySequence

        for definition in shortcut_manager.list_definitions():
            action = definition.action
            label = f"[{definition.category}] {definition.label}"
            edit = QKeySequenceEdit(sc_content)
            edit.setKeySequence(QKeySequence(shortcut_manager.get(action)))
            self._apply_shortcut_edit_style(edit, focused=False)
            edit.installEventFilter(self)
            row_lbl = BodyLabel(label + ":", sc_content)
            row_lbl.setStyleSheet(body_text_style_sheet())

            conflict_lbl = BodyLabel("", sc_content)
            conflict_lbl.setStyleSheet(error_text_style_sheet(font_size=10))
            conflict_lbl.setVisible(False)

            edit_col = QWidget(sc_content)
            ecol_layout = QVBoxLayout(edit_col)
            ecol_layout.setContentsMargins(0, 0, 0, 0)
            ecol_layout.setSpacing(1)
            ecol_layout.addWidget(edit)
            ecol_layout.addWidget(conflict_lbl)

            sc_form.addRow(row_lbl, edit_col)
            self._shortcut_edits[action] = edit
            self._shortcut_rows[action] = edit_col
            self._shortcut_labels.append(row_lbl)
            self._conflict_labels[action] = conflict_lbl
            edit.keySequenceChanged.connect(lambda ks, a=action: self._check_shortcut_conflict(a, ks))

        btn_container = QWidget(self._shortcuts_card)
        btn_row = QHBoxLayout(btn_container)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        apply_btn = PushButton("应用快捷键", btn_container)
        apply_btn.clicked.connect(self._on_apply_shortcuts)
        reset_btn = PushButton("恢复默认", btn_container)
        reset_btn.clicked.connect(self._on_reset_shortcuts)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()

        shortcuts_editor_card = ExpandGroupSettingCard(
            FIF.INFO,
            "快捷键映射",
            "所有已注册的界面动作都会显示在这里。点击输入框后按下新快捷键，再点击“应用快捷键”保存。",
            self._shortcuts_card,
        )
        self._shortcuts_editor_card = shortcuts_editor_card
        shortcuts_editor_card.setExpand(True)
        filter_container = QWidget(shortcuts_editor_card)
        filter_layout = QVBoxLayout(filter_container)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(6)
        self._shortcut_filter_edit = LineEdit(filter_container)
        self._shortcut_filter_edit.setPlaceholderText("筛选快捷键动作，例如“分析”或“导出”")
        self._shortcut_filter_edit.setClearButtonEnabled(True)
        self._shortcut_filter_edit.setToolTip("按动作名称、分类或关键词筛选快捷键")
        self._shortcut_filter_edit.textChanged.connect(self._filter_shortcut_rows)
        self._apply_shortcut_filter_style()
        self._shortcut_filter_edit.setMinimumWidth(280)
        filter_layout.addWidget(self._shortcut_filter_edit)
        shortcuts_editor_card.addGroupWidget(filter_container)
        shortcuts_editor_card.addGroupWidget(sc_content)
        shortcuts_editor_card.addGroupWidget(btn_container)
        self._shortcuts_card.addSettingCard(shortcuts_editor_card)

        layout.addWidget(self._shortcuts_card)
        layout.addStretch()
        return outer

    def _build_ai_tab(self) -> QWidget:
        outer = SmoothScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(*self._tab_content_margins())
        outer.setWidget(content)

        # ── AI 接口配置 ──
        self._ai_card = CardWidget(content)
        ai_layout = QVBoxLayout(self._ai_card)
        self._apply_card_layout_metrics(ai_layout)

        ai_title = BodyLabel("AI 接口", self._ai_card)
        ai_title.setStyleSheet(card_title_style_sheet(font_size=18))
        ai_layout.addWidget(ai_title)

        self._ai_provider_hint = BodyLabel("", self._ai_card)
        self._ai_provider_hint.setWordWrap(True)
        self._ai_provider_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        ai_layout.addWidget(self._ai_provider_hint)

        form = QFormLayout()
        form.setSpacing(8)

        self._ai_provider_combo = ComboBox(self._ai_card)
        for provider_key in self._provider_keys:
            self._ai_provider_combo.addItem(get_provider_preset(provider_key)["label"])
        self._ai_provider_combo.currentIndexChanged.connect(self._on_ai_provider_changed)
        form.addRow("接口类型:", self._ai_provider_combo)

        self._ai_url_edit = LineEdit(self._ai_card)
        self._ai_url_edit.setPlaceholderText("例: https://api.openai.com/v1  或  http://localhost:11434")
        self._ai_url_edit.setToolTip("AI 接口的 Base URL，OpenAI 填官方地址，Ollama 填本地地址")
        form.addRow("API 地址:", self._ai_url_edit)

        self._ai_key_edit = LineEdit(self._ai_card)
        self._ai_key_edit.setPlaceholderText("sk-...（OpenAI 必填，Ollama 可选）")
        self._ai_key_edit.setToolTip("API 认证密钥，OpenAI/商用接口通常必填；Ollama 本地部署可留空，服务端代理可填写")
        form.addRow("API Key:", self._ai_key_edit)

        self._ai_model_preset_combo = ComboBox(self._ai_card)
        self._ai_model_preset_combo.currentIndexChanged.connect(self._on_model_preset_changed)
        form.addRow("推荐模型:", self._ai_model_preset_combo)

        self._ai_model_edit = LineEdit(self._ai_card)
        form.addRow("模型名称:", self._ai_model_edit)

        self._ai_timeout_edit = LineEdit(self._ai_card)
        self._ai_timeout_edit.setPlaceholderText("60")
        self._ai_timeout_edit.setToolTip("等待 AI 响应的超时秒数，网络较慢或模型较大时可适当增大")
        form.addRow("超时(秒):", self._ai_timeout_edit)

        self._ai_temperature_edit = LineEdit(self._ai_card)
        self._ai_temperature_edit.setPlaceholderText("0.7")
        self._ai_temperature_edit.setToolTip("控制回复随机性：0 = 完全确定性，1-2 = 创造性更高。\n一般推荐 0.5~0.8，精确计算任务建议 0")
        form.addRow("Temperature:", self._ai_temperature_edit)

        self._ai_top_p_edit = LineEdit(self._ai_card)
        self._ai_top_p_edit.setPlaceholderText("1.0")
        self._ai_top_p_edit.setToolTip("核采样概率阈值，与 Temperature 配合使用。\n1.0 表示不限制，通常保持默认 1.0 即可")
        form.addRow("Top P:", self._ai_top_p_edit)

        self._ai_max_tokens_edit = LineEdit(self._ai_card)
        self._ai_max_tokens_edit.setPlaceholderText("2048")
        self._ai_max_tokens_edit.setToolTip("单次回复的最大 token 数量，超出后截断\n日常对话 2048 足够，长文档分析可调高至 4096")
        form.addRow("Max Tokens:", self._ai_max_tokens_edit)

        self._ai_ollama_keep_alive_edit = LineEdit(self._ai_card)
        self._ai_ollama_keep_alive_edit.setPlaceholderText("5m")
        self._ai_ollama_keep_alive_edit.setToolTip("Ollama 模型在内存中保持加载的时长\n格式：数字+单位，如 5m / 1h / 0（永久）。仅 Ollama 接口生效")
        form.addRow("Ollama Keep-Alive:", self._ai_ollama_keep_alive_edit)

        self._ai_ollama_num_ctx_edit = LineEdit(self._ai_card)
        self._ai_ollama_num_ctx_edit.setPlaceholderText("4096")
        self._ai_ollama_num_ctx_edit.setToolTip("Ollama 模型上下文窗口大小（token 数量）\n越大可处理更长的历史记录，但内存占用也更高。仅 Ollama 接口生效")
        form.addRow("Ollama Num Ctx:", self._ai_ollama_num_ctx_edit)

        self._ai_system_prompt_edit = PlainTextEdit(self._ai_card)
        self._ai_system_prompt_edit.setPlaceholderText("全局系统提示，例如：优先用中文回答，并保持术语统一。")
        self._ai_system_prompt_edit.setFixedHeight(96)
        form.addRow("系统提示:", self._ai_system_prompt_edit)

        ai_layout.addLayout(form)

        ai_btn_row = QHBoxLayout()
        save_ai_btn = PrimaryPushButton("保存配置")
        save_ai_btn.clicked.connect(self._save_ai_config)
        test_ai_btn = PushButton("测试连接")
        test_ai_btn.clicked.connect(self._test_ai_connection)
        self._ai_refresh_models_btn = PushButton("探测模型")
        self._ai_refresh_models_btn.clicked.connect(self._refresh_available_models)
        ai_btn_row.addWidget(save_ai_btn)
        ai_btn_row.addWidget(test_ai_btn)
        ai_btn_row.addWidget(self._ai_refresh_models_btn)
        ai_btn_row.addStretch()
        ai_layout.addLayout(ai_btn_row)

        layout.addWidget(self._ai_card)

        self._ai_tool_items: list[dict] = []  # {source, type, name, desc, item}

        self._ai_tools_card = CardWidget(content)
        ai_tools_layout = QVBoxLayout(self._ai_tools_card)
        self._apply_card_layout_metrics(ai_tools_layout)

        ai_tools_title = BodyLabel("AI 工具管理", self._ai_tools_card)
        ai_tools_title.setStyleSheet(card_title_style_sheet(font_size=18))
        ai_tools_layout.addWidget(ai_tools_title)

        self._ai_tools_project_label = BodyLabel("当前项目: 未打开", self._ai_tools_card)
        self._ai_tools_project_label.setStyleSheet(body_text_style_sheet())
        ai_tools_layout.addWidget(self._ai_tools_project_label)

        self._ai_tools_summary_label = BodyLabel("内置 0 · Prompt 0 · Skill 0 · Agent 0", self._ai_tools_card)
        self._ai_tools_summary_label.setStyleSheet(secondary_text_style_sheet())
        ai_tools_layout.addWidget(self._ai_tools_summary_label)

        # 工具选择下拉框
        selector_row = QHBoxLayout()
        selector_row.addWidget(BodyLabel("选择工具:", self._ai_tools_card))
        self._ai_tool_selector = ComboBox(self._ai_tools_card)
        self._ai_tool_selector.setMinimumWidth(300)
        self._ai_tool_selector.currentIndexChanged.connect(self._on_ai_tool_selected)
        selector_row.addWidget(self._ai_tool_selector, 1)
        ai_tools_layout.addLayout(selector_row)

        # 工具详情卡片
        self._ai_tool_detail_card = CardWidget(self._ai_tools_card)
        detail_layout = QVBoxLayout(self._ai_tool_detail_card)
        detail_layout.setSpacing(6)
        detail_layout.setContentsMargins(12, 10, 12, 10)

        detail_name_row = QHBoxLayout()
        detail_name_row.addWidget(BodyLabel("名称:", self._ai_tool_detail_card))
        self._ai_tool_detail_name = BodyLabel("—", self._ai_tool_detail_card)
        self._ai_tool_detail_name.setStyleSheet(f"{body_text_style_sheet()} font-weight: bold;")
        detail_name_row.addWidget(self._ai_tool_detail_name, 1)
        detail_layout.addLayout(detail_name_row)

        detail_type_row = QHBoxLayout()
        detail_type_row.addWidget(BodyLabel("类型:", self._ai_tool_detail_card))
        self._ai_tool_detail_type = BodyLabel("—", self._ai_tool_detail_card)
        self._ai_tool_detail_type.setStyleSheet(secondary_text_style_sheet())
        detail_type_row.addWidget(self._ai_tool_detail_type, 1)
        detail_layout.addLayout(detail_type_row)

        detail_desc_row = QHBoxLayout()
        detail_desc_row.addWidget(BodyLabel("描述:", self._ai_tool_detail_card))
        self._ai_tool_detail_desc = BodyLabel("—", self._ai_tool_detail_card)
        self._ai_tool_detail_desc.setWordWrap(True)
        detail_desc_row.addWidget(self._ai_tool_detail_desc, 1)
        detail_layout.addLayout(detail_desc_row)

        detail_action_row = QHBoxLayout()
        self._ai_tool_edit_btn = PushButton("编辑", self._ai_tool_detail_card)
        self._ai_tool_edit_btn.setEnabled(False)
        self._ai_tool_edit_btn.clicked.connect(self._on_edit_selected_ai_tool)
        self._ai_tool_delete_btn = PushButton("删除", self._ai_tool_detail_card)
        self._ai_tool_delete_btn.setEnabled(False)
        self._ai_tool_delete_btn.clicked.connect(self._on_delete_selected_ai_tool)
        detail_action_row.addWidget(self._ai_tool_edit_btn)
        detail_action_row.addWidget(self._ai_tool_delete_btn)
        detail_action_row.addStretch()
        detail_layout.addLayout(detail_action_row)

        ai_tools_layout.addWidget(self._ai_tool_detail_card)

        # 创建按钮行
        ai_tools_btn_row = QHBoxLayout()
        new_prompt_btn = PushButton("新建 Prompt", self._ai_tools_card)
        new_prompt_btn.clicked.connect(lambda: self._open_ai_tool_dialog("prompt"))
        new_skill_btn = PushButton("新建 Skill", self._ai_tools_card)
        new_skill_btn.clicked.connect(lambda: self._open_ai_tool_dialog("skill"))
        new_agent_btn = PushButton("新建 Agent", self._ai_tools_card)
        new_agent_btn.clicked.connect(lambda: self._open_ai_tool_dialog("agent"))
        refresh_ai_tools_btn = PushButton("刷新", self._ai_tools_card)
        refresh_ai_tools_btn.clicked.connect(self._refresh_ai_tools_panel)
        ai_tools_btn_row.addWidget(new_prompt_btn)
        ai_tools_btn_row.addWidget(new_skill_btn)
        ai_tools_btn_row.addWidget(new_agent_btn)
        ai_tools_btn_row.addWidget(refresh_ai_tools_btn)
        ai_tools_btn_row.addStretch()
        ai_tools_layout.addLayout(ai_tools_btn_row)

        layout.addWidget(self._ai_tools_card)

        # 兼容字段（隐藏）
        from qfluentwidgets import ListWidget as _ListWidget
        self._tmpl_card = CardWidget(content)
        self._tmpl_card.hide()
        self._tmpl_list = _ListWidget(self._tmpl_card)

        layout.addStretch()
        return outer

    def _on_apply_shortcuts(self):
        """保存用户修改的快捷键"""
        mapping = {}
        for action, edit in self._shortcut_edits.items():
            mapping[action] = edit.keySequence().toString()
        shortcut_manager.apply_all(mapping)
        self.shortcuts_changed.emit()

    def _filter_shortcut_rows(self, text: str) -> None:
        query = text.strip().lower()
        for definition in shortcut_manager.list_definitions():
            action = definition.action
            label = definition.label
            tags = " ".join(shortcut_manager.search_tags(action))
            visible = not query or query in action.lower() or query in label.lower() or query in tags.lower()
            row_prefix = f"[{definition.category}] {label}"
            row_label = next((item for item in self._shortcut_labels if item.text().startswith(row_prefix)), None)
            edit_col = self._shortcut_rows.get(action)
            if row_label is not None:
                row_label.setVisible(visible)
            if edit_col is not None:
                edit_col.setVisible(visible)

    def _check_shortcut_conflict(self, changed_action: str, ks):
        """实时检测快捷键冲突"""
        ks_str = ks.toString() if not isinstance(ks, str) else ks
        # 清空所有冲突提示
        for a, lbl in self._conflict_labels.items():
            lbl.setVisible(False)
        if not ks_str:
            return
        # 找所有与此序列重复的 action
        conflicts = []
        for a, edit in self._shortcut_edits.items():
            if a != changed_action and edit.keySequence().toString() == ks_str:
                conflicts.append(a)
        if conflicts:
            from core.shortcut_manager import shortcut_manager as sm
            conflict_names = " / ".join(str(sm.LABELS.get(a, a) or a) for a in conflicts)
            self._conflict_labels[changed_action].setText(f"与「{conflict_names}」冲突")
            self._conflict_labels[changed_action].setVisible(True)
            for a in conflicts:
                if a in self._conflict_labels:
                    cur_ks = self._shortcut_edits[changed_action].keySequence().toString()
                    changed_name = sm.LABELS.get(changed_action, changed_action)
                    self._conflict_labels[a].setText(f"与「{changed_name}」冲突")
                    self._conflict_labels[a].setVisible(True)

    def _on_reset_shortcuts(self):
        """恢复所有快捷键为默认值"""
        shortcut_manager.reset_to_defaults()
        from PySide6.QtGui import QKeySequence
        for action, edit in self._shortcut_edits.items():
            edit.setKeySequence(QKeySequence(shortcut_manager.get(action)))
        self.shortcuts_changed.emit()

    def on_theme_changed(self, index):
        themes = [Theme.LIGHT, Theme.DARK, Theme.AUTO]
        setTheme(themes[index])
        QTimer.singleShot(50, self._update_colors)

    def _update_colors(self):
        """更新界面颜色以适应新主题"""
        if self._appearance_title is not None:
            self._appearance_title.setStyleSheet(card_title_style_sheet(font_size=18))
        if self._theme_label is not None:
            self._theme_label.setStyleSheet(body_text_style_sheet())
        if self._tree_display_mode_label is not None:
            self._tree_display_mode_label.setStyleSheet(body_text_style_sheet())
        if self._onboarding_label is not None:
            self._onboarding_label.setStyleSheet(body_text_style_sheet())
        if self._onboarding_hint is not None:
            self._onboarding_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if self._extension_title is not None:
            self._extension_title.setStyleSheet(card_title_style_sheet(font_size=18))
        if self._extension_hint is not None:
            self._extension_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if self._external_extensions_dir_label is not None:
            self._external_extensions_dir_label.setStyleSheet(body_text_style_sheet())
        for hint in self._extension_empty_hints.values():
            hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if self._lang_title is not None:
            self._lang_title.setStyleSheet(card_title_style_sheet(font_size=18))
        if self._lang_placeholder is not None:
            self._lang_placeholder.setStyleSheet(placeholder_text_style_sheet(font_size=12, italic=True))
        if self._shortcuts_title:
            self._shortcuts_title.setStyleSheet(card_title_style_sheet(font_size=18))
        self._apply_shortcut_filter_style()
        # 快捷键行标签
        for lbl in self._shortcut_labels:
            lbl.setStyleSheet(body_text_style_sheet())
        for lbl in self._conflict_labels.values():
            lbl.setStyleSheet(error_text_style_sheet(font_size=10))
        # QKeySequenceEdit 样式
        for edit in self._shortcut_edits.values():
            self._apply_shortcut_edit_style(edit, focused=edit.hasFocus())
        # hint label（找到快捷键卡片下方的说明标签）
        if self._shortcuts_card is not None:
            for lbl in self._shortcuts_card.findChildren(BodyLabel):
                ss = lbl.styleSheet()
                if 'font-size: 11px' in ss:
                    lbl.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if hasattr(self, "_ai_provider_hint") and self._ai_provider_hint is not None:
            self._ai_provider_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if hasattr(self, "_ai_tools_project_label") and self._ai_tools_project_label is not None:
            self._ai_tools_project_label.setStyleSheet(body_text_style_sheet())
        if hasattr(self, "_ai_tools_summary_label") and self._ai_tools_summary_label is not None:
            self._ai_tools_summary_label.setStyleSheet(secondary_text_style_sheet())
        if hasattr(self, "_ai_tool_detail_name") and self._ai_tool_detail_name is not None:
            self._ai_tool_detail_name.setStyleSheet(f"{body_text_style_sheet()} font-weight: bold;")
        if hasattr(self, "_ai_tool_detail_type") and self._ai_tool_detail_type is not None:
            self._ai_tool_detail_type.setStyleSheet(secondary_text_style_sheet())

    def update_theme_colors(self) -> None:
        self._update_colors()

    def _current_tree_display_mode(self) -> TreeNameDisplayMode:
        if self._tree_display_mode_combo is None:
            return "wrap"
        idx = self._tree_display_mode_combo.currentIndex()
        if 0 <= idx < len(self._tree_display_mode_keys):
            return "elide" if self._tree_display_mode_keys[idx] == "elide" else "wrap"
        return "wrap"

    def _on_tree_display_mode_changed(self, _index: int) -> None:
        mode = set_tree_name_display_mode(self._current_tree_display_mode())
        self.tree_display_mode_changed.emit(mode)

    def _on_page_tree_focus_mode_changed(self, _state: int) -> None:
        enabled = bool(self._page_tree_focus_mode_checkbox.isChecked()) if self._page_tree_focus_mode_checkbox is not None else False
        enabled = set_page_tree_focus_mode_enabled(enabled)
        self.page_tree_focus_mode_changed.emit(enabled)

    def _clear_builtin_extension_options(self) -> None:
        self._builtin_extension_checkboxes.clear()
        self._builtin_extension_checkbox_groups.clear()
        self._external_extension_checkboxes.clear()
        self._external_extension_checkbox_groups.clear()
        for layout in [*self._extension_option_layouts.values(), *self._external_extension_option_layouts.values()]:
            while layout.count() > 0:
                item = layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

    def _register_extension_checkbox(self, source: str, spec_id: str, checkbox: CheckBox) -> None:
        checkbox_map = self._builtin_extension_checkboxes if source == "builtin" else self._external_extension_checkboxes
        group_map = self._builtin_extension_checkbox_groups if source == "builtin" else self._external_extension_checkbox_groups
        if spec_id not in checkbox_map:
            checkbox_map[spec_id] = checkbox
        group_map.setdefault(spec_id, []).append(checkbox)
        checkbox.stateChanged.connect(lambda state, s=source, extension_id=spec_id: self._sync_extension_checkbox_group(s, extension_id, state))

    def _sync_extension_checkbox_group(self, source: str, spec_id: str, state: int) -> None:
        group_map = self._builtin_extension_checkbox_groups if source == "builtin" else self._external_extension_checkbox_groups
        for checkbox in group_map.get(spec_id, []):
            if checkbox.checkState() == state:
                continue
            checkbox.blockSignals(True)
            checkbox.setCheckState(Qt.CheckState(state))
            checkbox.blockSignals(False)

    @staticmethod
    def _extension_spec_display_name(spec: dict, category: str) -> str:
        category_names = [str(item).strip() for item in spec.get("names_by_category", {}).get(category, []) if str(item).strip()]
        if category_names:
            return " / ".join(category_names)
        return str(spec.get("name") or spec.get("id") or "扩展").strip()

    @staticmethod
    def _extension_spec_tooltip(spec: dict, category: str) -> str:
        tooltip_lines = [str(spec.get("file_name") or "")]
        type_ids = [str(item).strip() for item in spec.get("type_ids_by_category", {}).get(category, []) if str(item).strip()]
        if type_ids:
            tooltip_lines.append(f"类型: {', '.join(type_ids)}")
        load_error = str(spec.get("load_error") or "").strip()
        if load_error:
            tooltip_lines.append(f"探测失败: {load_error}")
        return "\n".join(line for line in tooltip_lines if line)

    def _rebuild_builtin_extension_options(
        self,
        builtin_specs: list[dict],
        external_specs: list[dict],
        disabled_builtin_ids: list[str],
        disabled_external_ids: list[str],
    ) -> None:
        self._clear_builtin_extension_options()
        self._extension_specs_by_source = {"builtin": list(builtin_specs), "external": list(external_specs)}

        disabled_markers = {
            "builtin": {str(item).strip() for item in disabled_builtin_ids},
            "external": {str(item).strip() for item in disabled_external_ids},
        }
        source_enabled = {
            "builtin": bool(self._builtin_extensions_enabled_checkbox is not None and self._builtin_extensions_enabled_checkbox.isChecked()),
            "external": bool(self._external_extensions_enabled_checkbox is not None and self._external_extensions_enabled_checkbox.isChecked()),
        }
        for category, layout in self._extension_option_layouts.items():
            category_specs = [spec for spec in builtin_specs if category in list(spec.get("categories") or [])]
            hint = self._extension_empty_hints.get(category)
            if hint is not None:
                hint.setVisible(not category_specs)
            for spec in category_specs:
                spec_id = str(spec.get("id") or "").strip()
                if not spec_id:
                    continue
                checkbox = CheckBox(self._extension_spec_display_name(spec, category), self._builtin_extension_card)
                checkbox.setChecked(spec_id not in disabled_markers["builtin"])
                checkbox.setEnabled(source_enabled["builtin"])
                checkbox.setToolTip(self._extension_spec_tooltip(spec, category))
                install_fluent_tooltip(checkbox, delay=400)
                self._register_extension_checkbox("builtin", spec_id, checkbox)
                layout.addWidget(checkbox)

        for category, layout in self._external_extension_option_layouts.items():
            category_specs = [spec for spec in external_specs if category in list(spec.get("categories") or [])]
            hint = self._external_extension_empty_hints.get(category)
            if hint is not None:
                hint.setVisible(not category_specs)
            for spec in category_specs:
                spec_id = str(spec.get("id") or "").strip()
                if not spec_id:
                    continue
                checkbox = CheckBox(self._extension_spec_display_name(spec, category), self._external_extension_card)
                checkbox.setChecked(spec_id not in disabled_markers["external"])
                checkbox.setEnabled(source_enabled["external"])
                checkbox.setToolTip(self._extension_spec_tooltip(spec, category))
                install_fluent_tooltip(checkbox, delay=400)
                self._register_extension_checkbox("external", spec_id, checkbox)
                layout.addWidget(checkbox)
        self._schedule_extension_category_tab_heights_refresh()

    def _refresh_extension_category_tab_heights(self) -> None:
        self._view_state.extension_height_refresh_pending = False
        for tabs in (self._extension_tabs, self._external_extension_tabs):
            if tabs is None:
                continue
            tabs.adjustSize()
            tabs.updateGeometry()
            tabs.setMinimumHeight(
                max(
                    tabs.sizeHint().height() * _EXTENSION_CATEGORY_TABS_HEIGHT_MULTIPLIER,
                    tabs.navigationWidget.sizeHint().height(),
                )
            )

    def _on_builtin_extensions_enabled_changed(self, *_args) -> None:
        enabled = bool(
            self._builtin_extensions_enabled_checkbox is not None
            and self._builtin_extensions_enabled_checkbox.isChecked()
        )
        for checkboxes in self._builtin_extension_checkbox_groups.values():
            for checkbox in checkboxes:
                checkbox.setEnabled(enabled)

    def _on_external_extensions_enabled_changed(self, *_args) -> None:
        enabled = bool(
            self._external_extensions_enabled_checkbox is not None
            and self._external_extensions_enabled_checkbox.isChecked()
        )
        for checkboxes in self._external_extension_checkbox_groups.values():
            for checkbox in checkboxes:
                checkbox.setEnabled(enabled)

    def _load_extension_settings(self) -> None:
        from core.extension_api import list_builtin_extension_specs, list_external_extension_specs
        from core.extension_settings import (
            get_builtin_extension_settings,
            get_extension_number_decimals,
            get_external_extension_settings,
            get_external_extensions_directories,
        )

        load_builtin, disabled_extension_ids = get_builtin_extension_settings()
        load_external, disabled_external_ids = get_external_extension_settings()
        if self._builtin_extensions_enabled_checkbox is not None:
            self._builtin_extensions_enabled_checkbox.blockSignals(True)
            self._builtin_extensions_enabled_checkbox.setChecked(load_builtin)
            self._builtin_extensions_enabled_checkbox.blockSignals(False)
        if self._external_extensions_enabled_checkbox is not None:
            self._external_extensions_enabled_checkbox.blockSignals(True)
            self._external_extensions_enabled_checkbox.setChecked(load_external)
            self._external_extensions_enabled_checkbox.blockSignals(False)
        if self._external_extensions_dirs_card is not None:
            self._external_extensions_dirs_card.setFolders([str(path) for path in get_external_extensions_directories()])
        self._set_external_extension_number_decimals(get_extension_number_decimals())
        self._rebuild_builtin_extension_options(
            list_builtin_extension_specs(),
            list_external_extension_specs(),
            disabled_extension_ids,
            disabled_external_ids,
        )
        self._on_builtin_extensions_enabled_changed()
        self._on_external_extensions_enabled_changed()
        self._refresh_extension_status_summary()

    def _refresh_extension_status_summary(self) -> None:
        status = get_extension_load_status()
        registered_count = status["registered_count"]
        error_count = status["error_count"]
        source_summary = status.get("source_summary") or {}
        loaded_counts = dict(source_summary.get("loaded_extension_counts") or {})
        builtin_count = int(loaded_counts.get("builtin", 0) or 0)
        external_count = int(loaded_counts.get("external", 0) or 0)
        source_suffix = (
            f"（内置 {builtin_count} / 外部 {external_count}）"
            if builtin_count + external_count > 0
            else ""
        )
        if error_count:
            self._extension_status_summary_btn.setText(f"当前扩展状态：{registered_count} 项可用{source_suffix}，{error_count} 项失败")
            self._extension_status_summary_btn.setStyleSheet(flat_status_button_style(warning_color()))
        elif registered_count:
            self._extension_status_summary_btn.setText(f"当前扩展状态：{registered_count} 项可用{source_suffix}")
            self._extension_status_summary_btn.setStyleSheet(flat_status_button_style(accent_color()))
        else:
            self._extension_status_summary_btn.setText("当前扩展状态：未发现可用项")
            self._extension_status_summary_btn.setStyleSheet(flat_status_button_style(placeholder_color()))
        self._extension_status_summary_btn.setEnabled(bool(status["details"].get("loaded") or status["details"].get("errors")))

    def _show_extension_status_details(self) -> None:
        show_extension_load_report_dialog(self, "扩展加载详情")

    def _refresh_external_extension_specs(self) -> None:
        from core.extension_api import list_external_extension_specs

        disabled_builtin_ids = [spec_id for spec_id, checkbox in self._builtin_extension_checkboxes.items() if not checkbox.isChecked()]
        disabled_external_ids = [spec_id for spec_id, checkbox in self._external_extension_checkboxes.items() if not checkbox.isChecked()]
        external_dirs = self._current_external_extensions_directories()
        external_specs = list_external_extension_specs(external_dirs or None)
        self._rebuild_builtin_extension_options(
            self._extension_specs_by_source.get("builtin", []),
            external_specs,
            disabled_builtin_ids,
            disabled_external_ids,
        )
        self._on_builtin_extensions_enabled_changed()
        self._on_external_extensions_enabled_changed()
        InfoBar.success(
            "已刷新",
            f"检测到 {len(external_specs)} 个扩展文件",
            parent=self._notification_parent(),
            position=InfoBarPosition.TOP,
        )

    def _current_external_extensions_directories(self) -> list[str]:
        if self._external_extensions_dirs_card is None:
            return []
        return [str(folder).strip() for folder in list(self._external_extensions_dirs_card.folders) if str(folder).strip()]

    def _set_external_extension_number_decimals(self, value: int) -> None:
        normalized = max(0, min(12, int(value)))
        if self._external_extension_number_decimals_slider is not None:
            self._external_extension_number_decimals_slider.blockSignals(True)
            self._external_extension_number_decimals_slider.setValue(normalized)
            self._external_extension_number_decimals_slider.blockSignals(False)
        if self._external_extension_number_decimals_value_label is not None:
            self._external_extension_number_decimals_value_label.setText(str(normalized))

    def _on_external_extension_number_decimals_changed(self, value: int) -> None:
        if self._external_extension_number_decimals_value_label is not None:
            self._external_extension_number_decimals_value_label.setText(str(int(value)))

    def _save_extension_settings(self) -> None:
        from core.extension_loader import reload_configured_extensions
        from core.extension_settings import (
            set_builtin_extension_settings,
            set_extension_number_decimals,
            set_external_extension_settings,
            set_external_extensions_directories,
        )

        load_builtin = bool(
            self._builtin_extensions_enabled_checkbox is not None
            and self._builtin_extensions_enabled_checkbox.isChecked()
        )
        load_external = bool(
            self._external_extensions_enabled_checkbox is not None
            and self._external_extensions_enabled_checkbox.isChecked()
        )
        disabled_extension_ids = [
            spec_id for spec_id, checkbox in self._builtin_extension_checkboxes.items()
            if not checkbox.isChecked()
        ]
        disabled_external_ids = [
            spec_id for spec_id, checkbox in self._external_extension_checkboxes.items()
            if not checkbox.isChecked()
        ]

        external_dirs = self._current_external_extensions_directories()
        try:
            set_external_extensions_directories(external_dirs)
        except ValueError as exc:
            InfoBar.error("扩展设置保存失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        set_builtin_extension_settings(load_builtin, disabled_extension_ids)
        set_external_extension_settings(load_external, disabled_external_ids)
        if self._external_extension_number_decimals_slider is not None:
            set_extension_number_decimals(self._external_extension_number_decimals_slider.value())
        report = reload_configured_extensions()
        self._load_extension_settings()
        self.extensions_reloaded.emit()
        if report.get("errors"):
            InfoBar.warning(
                "扩展设置已保存",
                f"已加载 {len(report.get('loaded', []))} 个扩展，{len(report.get('errors', []))} 个失败",
                parent=self._notification_parent(),
                position=InfoBarPosition.TOP,
            )
            return
        InfoBar.success(
            "扩展设置已保存",
            f"已重新加载 {len(report.get('loaded', []))} 个扩展",
            parent=self._notification_parent(),
            position=InfoBarPosition.TOP,
        )

    # ── AI 配置方法 ──────────────────────────────────────────

    def _current_provider_key(self) -> str:
        if not self._ai_config_controls_ready():
            return self._active_provider_key
        idx = self._ai_provider_combo.currentIndex()
        if 0 <= idx < len(self._provider_keys):
            return self._provider_keys[idx]
        return self._active_provider_key

    def _populate_model_presets(self, models: list[str], preferred: str = "") -> None:
        if not self._ai_config_controls_ready():
            return
        current = preferred or self._ai_model_edit.text().strip()
        self._ai_model_preset_combo.blockSignals(True)
        self._ai_model_preset_combo.clear()
        for model in models:
            self._ai_model_preset_combo.addItem(model)
        if models:
            if current and current in models:
                self._ai_model_preset_combo.setCurrentText(current)
            else:
                self._ai_model_preset_combo.setCurrentIndex(0)
        self._ai_model_preset_combo.blockSignals(False)

    def _on_model_preset_changed(self, idx: int) -> None:
        if not self._ai_config_controls_ready():
            return
        if idx < 0:
            return
        model_name = self._ai_model_preset_combo.currentText().strip()
        if model_name:
            self._ai_model_edit.setText(model_name)

    def _parse_int(self, text: str, fallback: int, minimum: int | None = None) -> int:
        try:
            value = int(text or str(fallback))
        except ValueError:
            value = fallback
        if minimum is not None:
            value = max(minimum, value)
        return value

    def _parse_float(self, text: str, fallback: float, minimum: float, maximum: float) -> float:
        try:
            value = float(text or str(fallback))
        except ValueError:
            value = fallback
        return max(minimum, min(maximum, value))

    def _collect_ai_config(self):
        from core.ai_client import AIConfig

        if not self._ai_config_controls_ready():
            return AIConfig()

        provider = self._current_provider_key()
        if provider not in {"openai_compatible", "ollama"}:
            provider = "openai_compatible"
        provider = cast(Literal["openai_compatible", "ollama"], provider)
        preset = get_provider_preset(provider)
        return AIConfig(
            provider=provider,
            base_url=self._ai_url_edit.text().strip() or preset["default_url"],
            api_key=self._ai_key_edit.text().strip(),
            model=self._ai_model_edit.text().strip() or preset["default_model"],
            timeout=self._parse_int(self._ai_timeout_edit.text(), 60, minimum=1),
            temperature=self._parse_float(self._ai_temperature_edit.text(), 0.7, 0.0, 2.0),
            top_p=self._parse_float(self._ai_top_p_edit.text(), 1.0, 0.0, 1.0),
            max_tokens=self._parse_int(self._ai_max_tokens_edit.text(), 2048, minimum=1),
            system_prompt=self._ai_system_prompt_edit.toPlainText().strip(),
            ollama_keep_alive=self._ai_ollama_keep_alive_edit.text().strip() or "5m",
            ollama_num_ctx=self._parse_int(self._ai_ollama_num_ctx_edit.text(), 4096, minimum=1),
        )

    def _load_ai_config(self) -> None:
        if not self._ai_config_controls_ready():
            return
        from core.ai_client import AIConfig
        cfg = AIConfig.load()
        idx = self._provider_keys.index(cfg.provider) if cfg.provider in self._provider_keys else 0
        self._ai_provider_combo.setCurrentIndex(idx)
        self._ai_url_edit.setText(cfg.base_url)
        self._ai_key_edit.setText(cfg.api_key)
        self._ai_model_edit.setText(cfg.model)
        self._ai_timeout_edit.setText(str(cfg.timeout))
        self._ai_temperature_edit.setText(str(cfg.temperature))
        self._ai_top_p_edit.setText(str(cfg.top_p))
        self._ai_max_tokens_edit.setText(str(cfg.max_tokens))
        self._ai_system_prompt_edit.setPlainText(cfg.system_prompt)
        self._ai_ollama_keep_alive_edit.setText(cfg.ollama_keep_alive)
        self._ai_ollama_num_ctx_edit.setText(str(cfg.ollama_num_ctx))
        self._on_ai_provider_changed(idx)

    def _on_ai_provider_changed(self, idx: int) -> None:
        if not self._ai_config_controls_ready():
            return
        provider = self._provider_keys[idx] if 0 <= idx < len(self._provider_keys) else "openai_compatible"
        previous_preset = get_provider_preset(self._active_provider_key)
        preset = get_provider_preset(provider)

        current_url = self._ai_url_edit.text().strip()
        if not current_url or current_url == previous_preset["default_url"]:
            self._ai_url_edit.setText(preset["default_url"])
        self._ai_url_edit.setPlaceholderText(preset["default_url"])

        current_model = self._ai_model_edit.text().strip()
        if not current_model or current_model == previous_preset["default_model"]:
            self._ai_model_edit.setText(preset["default_model"])
        self._ai_model_edit.setPlaceholderText(preset["model_placeholder"])
        self._populate_model_presets(list_builtin_models(provider), preferred=self._ai_model_edit.text().strip())

        requires_key = bool(preset.get("api_key_required", True))
        self._ai_key_edit.setEnabled(True)
        if not requires_key:
            self._ai_key_edit.setPlaceholderText("可选：服务端 Ollama 可填写 API Key，本地可留空")
        else:
            self._ai_key_edit.setPlaceholderText("sk-...（必填）")

        is_ollama = provider == "ollama"
        self._ai_refresh_models_btn.setVisible(bool(preset.get("supports_model_discovery")))
        self._ai_ollama_keep_alive_edit.setEnabled(is_ollama)
        self._ai_ollama_num_ctx_edit.setEnabled(is_ollama)
        self._ai_provider_hint.setText(preset.get("help_text", ""))
        self._active_provider_key = provider

    def _save_ai_config(self) -> None:
        if not self._ai_config_controls_ready():
            return
        cfg = self._collect_ai_config()
        cfg.save()
        InfoBar.success("已保存", "AI 配置已保存", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _refresh_available_models(self) -> None:
        if not self._ai_config_controls_ready():
            return
        from core.ai_client import AIClient

        provider = self._current_provider_key()
        if provider != "ollama":
            self._populate_model_presets(list_builtin_models(provider))
            return

        try:
            models = AIClient(self._collect_ai_config()).list_available_models_sync()
        except Exception as exc:
            InfoBar.error("探测失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return

        self._populate_model_presets(models, preferred=self._ai_model_edit.text().strip())
        if models and not self._ai_model_edit.text().strip():
            self._ai_model_edit.setText(models[0])
        InfoBar.success("模型已刷新", f"发现 {len(models)} 个可用模型", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _test_ai_connection(self) -> None:
        if not self._ai_config_controls_ready():
            return
        self._save_ai_config()
        InfoBar.info("测试中", "正在测试 AI 连接…", parent=self._notification_parent(), position=InfoBarPosition.TOP)
        import asyncio
        from core.ai_client import AIClient
        client = AIClient()

        async def _test():
            return await client.test_connection()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在 Qt 事件循环中异步执行（需要 qasync 或类似库）
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _test())
                    ok, msg = future.result(timeout=30)
            else:
                ok, msg = loop.run_until_complete(_test())
        except Exception as e:
            ok, msg = False, str(e)

        if ok:
            InfoBar.success("连接成功", msg, parent=self._notification_parent(), position=InfoBarPosition.TOP)
        else:
            InfoBar.error("连接失败", msg, parent=self._notification_parent(), position=InfoBarPosition.TOP)

    # ── 报告模板方法 ──────────────────────────────────────────

    def refresh_templates(self) -> None:
        """报告模板已迁入分析页；保留兼容入口以承接旧刷新调用。"""
        tmpl_list = getattr(self, "_tmpl_list", None)
        if tmpl_list is not None:
            tmpl_list.clear()
        self._refresh_ai_tools_panel()

    def _refresh_ai_tools_panel(self) -> None:
        if not self._ai_tools_controls_ready():
            return
        from ai.command_layer import COMMANDS
        from core.global_assets import global_assets

        self._ai_tool_items = []
        for name, cmd in COMMANDS.items():
            self._ai_tool_items.append({
                "source": "builtin",
                "type": "内置命令",
                "name": name,
                "desc": cmd.desc,
                "item": None,
            })

        prompts = global_assets.list_ai_prompts()
        skills = global_assets.list_ai_skills()
        agents = global_assets.list_ai_agents()
        self._ai_tools_project_label.setText(f"全局资源: {global_assets.asset_path}")
        self._ai_tools_summary_label.setText(
            f"内置 {len(COMMANDS)} · Prompt {len(prompts)} · Skill {len(skills)} · Agent {len(agents)}"
        )
        for item in prompts:
            self._ai_tool_items.append({
                "source": "global", "type": "Prompt",
                "name": item.name, "desc": getattr(item, "description", ""), "item": item,
            })
        for item in skills:
            self._ai_tool_items.append({
                "source": "global", "type": "Skill",
                "name": item.name, "desc": getattr(item, "description", ""), "item": item,
            })
        for item in agents:
            self._ai_tool_items.append({
                "source": "global", "type": "Agent",
                "name": item.name, "desc": getattr(item, "description", ""), "item": item,
            })

        self._ai_tool_selector.blockSignals(True)
        self._ai_tool_selector.clear()
        for t in self._ai_tool_items:
            prefix = "【内置】" if t["source"] == "builtin" else f"【{t['type']}】"
            self._ai_tool_selector.addItem(f"{prefix} {t['name']}")
        self._ai_tool_selector.blockSignals(False)

        if self._ai_tool_items:
            self._ai_tool_selector.setCurrentIndex(0)
            self._on_ai_tool_selected(0)
        else:
            self._clear_ai_tool_detail()

    def _clear_ai_tool_detail(self) -> None:
        if not self._ai_tools_controls_ready():
            return
        self._ai_tool_detail_name.setText("—")
        self._ai_tool_detail_type.setText("—")
        self._ai_tool_detail_desc.setText("—")
        self._ai_tool_edit_btn.setEnabled(False)
        self._ai_tool_delete_btn.setEnabled(False)

    def _on_ai_tool_selected(self, idx: int) -> None:
        if not self._ai_tools_controls_ready():
            return
        if idx < 0 or idx >= len(self._ai_tool_items):
            self._clear_ai_tool_detail()
            return
        t = self._ai_tool_items[idx]
        self._ai_tool_detail_name.setText(t["name"])
        self._ai_tool_detail_type.setText(t["type"])
        self._ai_tool_detail_desc.setText(t["desc"] or "（无描述）")
        is_global = t["source"] == "global"
        self._ai_tool_edit_btn.setEnabled(is_global)
        self._ai_tool_delete_btn.setEnabled(is_global)

    def _on_edit_selected_ai_tool(self) -> None:
        idx = self._ai_tool_selector.currentIndex()
        if idx < 0 or idx >= len(self._ai_tool_items):
            return
        t = self._ai_tool_items[idx]
        if t["source"] != "global" or t["item"] is None:
            return
        from ui.dialogs.ai_tool_dialog import AIToolDialog
        dlg = AIToolDialog(self, tool_type=t["type"].lower(), tool_id=t["item"].id)
        if dlg.exec():
            self._refresh_ai_tools_panel()
            self.assets_modified.emit()
            InfoBar.success("已更新", "AI 工具已修改", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _on_delete_selected_ai_tool(self) -> None:
        idx = self._ai_tool_selector.currentIndex()
        if idx < 0 or idx >= len(self._ai_tool_items):
            return
        t = self._ai_tool_items[idx]
        if t["source"] != "global" or t["item"] is None:
            return
        from core.global_assets import global_assets
        tool_type = t["type"].lower()
        if tool_type == "prompt":
            ok = global_assets.delete_ai_prompt(t["item"].id)
        elif tool_type == "skill":
            ok = global_assets.delete_ai_skill(t["item"].id)
        elif tool_type == "agent":
            ok = global_assets.delete_ai_agent(t["item"].id)
        else:
            ok = False
        if not ok:
            return
        self._refresh_ai_tools_panel()
        self.assets_modified.emit()
        tool_label = f'{t["type"]} "{t["name"]}"'
        InfoBar.success("已删除", f"已删除 {tool_label}", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _open_ai_tool_dialog(self, tool_type: Literal["prompt", "skill", "agent"]) -> None:
        from ui.dialogs.ai_tool_dialog import AIToolDialog

        dlg = AIToolDialog(self, tool_type=tool_type)
        if dlg.exec():
            self._refresh_ai_tools_panel()
            self.assets_modified.emit()
            InfoBar.success("已保存", "AI 工具已保存到全局资源", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _on_new_template(self):
        from core.global_assets import global_assets
        from models.schemas import ReportTemplate

        name, ok = TextInputDialog.get_text(self, "新建报告模板", "模板名称:", placeholder="输入模板名称")
        if not ok or not name.strip():
            return
        global_assets.add_report_template(ReportTemplate(name=name.strip(), content="# 报告\n\n**日期：** {{date}}\n"))
        self.refresh_templates()
        self.assets_modified.emit()

    def _on_edit_template(self):
        from core.global_assets import global_assets
        from core.project_manager import project_manager

        tmpl_list = getattr(self, "_tmpl_list", None)
        if tmpl_list is None:
            return
        idx = tmpl_list.currentRow()
        templates = global_assets.list_report_templates()
        if idx < 0 or idx >= len(templates):
            return
        tmpl = templates[idx]
        if tmpl.is_builtin:
            InfoBar.warning("提示", "内置模板不可编辑，请先复制", parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        from ui.dialogs.report_template_dialog import ReportTemplateDialog
        dlg = ReportTemplateDialog(self, template_id=tmpl.id)
        if dlg.exec():
            project_manager.update_report_template(tmpl.id, content=dlg._editor.toPlainText())
            self.assets_modified.emit()

    def _on_delete_template(self):
        from core.global_assets import global_assets
        from core.project_manager import project_manager

        tmpl_list = getattr(self, "_tmpl_list", None)
        if tmpl_list is None:
            return
        idx = tmpl_list.currentRow()
        templates = global_assets.list_report_templates()
        if idx < 0 or idx >= len(templates):
            return
        tmpl = templates[idx]
        if tmpl.is_builtin:
            InfoBar.warning("提示", "内置模板不可删除", parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        project_manager.delete_report_template(tmpl.id)
        self.refresh_templates()
        self.assets_modified.emit()
