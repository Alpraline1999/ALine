from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QFormLayout,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QKeySequenceEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ComboBox,
    ExpandGroupSettingCard,
    FolderListSettingCard,
    FluentIcon as FIF,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SettingCard,
    SettingCardGroup,
    Slider,
    SmoothScrollArea,
    SpinBox,
    SwitchSettingCard,
)

from core.ai.providers import get_provider_preset
from core.extension_settings import default_external_extensions_directory
from core.shortcut_manager import shortcut_manager
from core.ui_preferences import (
    get_tree_name_display_mode,
    get_ui_language,
    is_page_tree_focus_mode_enabled,
    get_auto_save_enabled,
    get_auto_save_interval_seconds,
)
from ui.widgets.navigation_stack import SegmentedStackWidget
from ui.theme import (
    body_text_style_sheet,
    card_title_style_sheet,
    error_text_style_sheet,
    placeholder_text_style_sheet,
    secondary_text_style_sheet,
)
from core.i18n import _

_EXTENSION_CATEGORY_TABS_MAX_HEIGHT = 60750
_EXTENSION_CATEGORY_TABS_HEIGHT_MULTIPLIER = 3


class MutableFolderListSettingCard(FolderListSettingCard):

    def __init__(self, title: str, content: str | None, folders: list[str], *, directory: str, parent: QWidget | None = None):
        from qfluentwidgets.common.config import ConfigItem

        self._config_item = ConfigItem("SettingsPage", "externalExtensionDirs", list(folders or []))
        super().__init__(self._config_item, title, content or "", directory=directory, parent=parent)
        self.addFolderButton.setText(_("添加文件夹"))
        try:
            self.addFolderButton.clicked.disconnect()
        except RuntimeError:
            pass
        self.addFolderButton.clicked.connect(self._show_folder_dialog)

    def setFolders(self, folders: list[str]) -> None:
        from qfluentwidgets.common.config import qconfig

        normalized = [str(folder).strip() for folder in folders if str(folder).strip()]
        self.folders = normalized
        self._dialogDirectory = normalized[0] if normalized else str(default_external_extensions_directory())
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

    def _show_folder_dialog(self) -> None:
        from qfluentwidgets.common.config import qconfig

        dialog = QFileDialog(self.window() or self, _("选择文件夹"), self._dialogDirectory)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        if dialog.exec() != int(QFileDialog.DialogCode.Accepted):
            return

        selected = dialog.selectedFiles()
        folder = selected[0] if selected else ""

        if not folder or folder in self.folders:
            return

        add_folder_item = getattr(self, "_FolderListSettingCard__addFolderItem")
        add_folder_item(folder)
        self.folders.append(folder)
        self._dialogDirectory = folder
        qconfig.set(self.configItem, list(self.folders))
        self.folderChanged.emit(self.folders)


def build_extension_category_tabs(page, parent: QWidget, *, empty_hints: dict[str, BodyLabel], option_layouts: dict[str, QVBoxLayout]) -> QWidget:
    tabs = SegmentedStackWidget(parent)
    tabs.setMaximumHeight(_EXTENSION_CATEGORY_TABS_MAX_HEIGHT)
    for category, label in (("plot", _("绘图扩展")), ("processing", _("处理扩展")), ("analysis", _("分析扩展")), ("digitize", _("数字化扩展"))):
        tab_page = QWidget(parent)
        page_layout = QVBoxLayout(tab_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(6)
        empty_hint = BodyLabel(f"{_('当前未发现')}{label}{_('。')}", tab_page)
        page._bind_theme_label_style(empty_hint, lambda: placeholder_text_style_sheet(font_size=11))
        page_layout.addWidget(empty_hint)
        empty_hints[category] = empty_hint

        options_scroll = SmoothScrollArea(tab_page)
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

        tabs.addTab(tab_page, label, route_key=category)
    tabs.setMinimumHeight(max(tabs.sizeHint().height() * _EXTENSION_CATEGORY_TABS_HEIGHT_MULTIPLIER, tabs.navigationWidget.sizeHint().height()))
    return tabs


def build_extensions_tab(page) -> QWidget:
    outer = SmoothScrollArea()
    outer.setWidgetResizable(True)
    outer.setFrameShape(QFrame.Shape.NoFrame)
    outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

    content = QWidget()
    content.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(content)
    layout.setSpacing(12)
    layout.setContentsMargins(*page._tab_content_margins())
    outer.setWidget(content)

    extension_group = SettingCardGroup(_("扩展"), content)
    page._extension_card = extension_group
    page._extension_title = page._bind_theme_label_style(
        extension_group.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )
    page._extension_status_card = SettingCard(FIF.INFO, _("扩展状态"), _("查看当前扩展加载情况与失败详情。"), extension_group)
    page._bind_setting_card_styles(
        page._extension_status_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._extension_status_summary_btn = PushButton("", page._extension_status_card)
    page._extension_status_summary_btn.setFlat(True)
    page._extension_status_summary_btn.clicked.connect(page._show_extension_status_details)
    page._attach_setting_card_control(page._extension_status_card, page._extension_status_summary_btn, alignment=Qt.AlignmentFlag.AlignLeft)
    extension_group.addSettingCard(page._extension_status_card)

    page._extension_actions_card = SettingCard(FIF.SYNC, _("应用扩展设置"), _("保存当前启用状态与目录配置，并重新加载扩展。"), extension_group)
    page._bind_setting_card_styles(
        page._extension_actions_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._save_extension_settings_btn = PrimaryPushButton(_("保存并重载扩展"), page._extension_actions_card)
    page._save_extension_settings_btn.clicked.connect(page._save_extension_settings)
    page._attach_setting_card_control(page._extension_actions_card, page._save_extension_settings_btn)
    extension_group.addSettingCard(page._extension_actions_card)
    layout.addWidget(extension_group)

    page._builtin_extension_card = SettingCardGroup(_("内置扩展"), content)
    page._bind_theme_label_style(
        page._builtin_extension_card.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )
    page._builtin_extensions_enabled_checkbox = SwitchSettingCard(
        FIF.DOWNLOAD,
        _("启用内置扩展"),
        _("关闭后保留内置扩展配置，但不参与加载。"),
        parent=page._builtin_extension_card,
    )
    page._bind_setting_card_styles(
        page._builtin_extensions_enabled_checkbox,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._builtin_extensions_enabled_checkbox.checkedChanged.connect(page._on_builtin_extensions_enabled_changed)
    page._extension_hint = page._builtin_extensions_enabled_checkbox.contentLabel
    page._builtin_extension_card.addSettingCard(page._builtin_extensions_enabled_checkbox)
    page._builtin_extension_management_card = ExpandGroupSettingCard(
        FIF.DOWNLOAD,
        _("扩展管理"),
        _("按类别管理内置扩展的启用状态。"),
        page._builtin_extension_card,
    )
    page._builtin_extension_management_card.setExpand(False)
    page._bind_theme_text_in_widget(
        page._builtin_extension_management_card,
        "扩展管理",
        body_text_style_sheet,
        first_only=True,
    )
    page._bind_theme_text_in_widget(
        page._builtin_extension_management_card,
        "按类别管理内置扩展的启用状态。",
        lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._extension_tabs = build_extension_category_tabs(
        page,
        page._builtin_extension_management_card,
        empty_hints=page._extension_empty_hints,
        option_layouts=page._extension_option_layouts,
    )
    page._builtin_extension_management_card.addGroupWidget(page._extension_tabs)
    page._builtin_extension_card.addSettingCard(page._builtin_extension_management_card)
    page._register_extension_height_watch_target(page._builtin_extension_management_card)
    page._register_extension_height_watch_target(page._extension_tabs)
    layout.addWidget(page._builtin_extension_card)

    page._external_extension_card = SettingCardGroup(_("外部扩展"), content)
    page._bind_theme_label_style(
        page._external_extension_card.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )
    page._external_extensions_enabled_checkbox = SwitchSettingCard(
        FIF.FOLDER,
        _("启用外部扩展"),
        _("关闭后保留目录配置，但不加载外部扩展。"),
        parent=page._external_extension_card,
    )
    page._bind_setting_card_styles(
        page._external_extensions_enabled_checkbox,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._external_extensions_enabled_checkbox.checkedChanged.connect(page._on_external_extensions_enabled_changed)
    page._external_extension_card.addSettingCard(page._external_extensions_enabled_checkbox)
    page._external_extensions_sandbox_checkbox = SwitchSettingCard(
        FIF.FOLDER,
        _("外部扩展沙箱模式"),
        _("在独立进程中执行外部扩展，崩溃不影响主应用。"),
        parent=page._external_extension_card,
    )
    page._bind_setting_card_styles(
        page._external_extensions_sandbox_checkbox,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._external_extension_card.addSettingCard(page._external_extensions_sandbox_checkbox)
    page._external_extensions_dirs_card = MutableFolderListSettingCard(
        _("外部扩展目录"),
        _("可添加多个文件夹；保存后会统一扫描并重载。"),
        [],
        directory=str(default_external_extensions_directory()),
        parent=page._external_extension_card,
    )
    page._bind_theme_text_in_widget(
        page._external_extensions_dirs_card,
        "外部扩展目录",
        body_text_style_sheet,
        first_only=True,
    )
    page._bind_theme_text_in_widget(
        page._external_extensions_dirs_card,
        "可添加多个文件夹；保存后会统一扫描并重载。",
        lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._external_extension_card.addSettingCard(page._external_extensions_dirs_card)

    external_refresh_card = SettingCard(
        FIF.SYNC,
        _("刷新外部扩展扫描"),
        _("按当前目录配置重新探测外部扩展，不会修改保存设置。"),
        page._external_extension_card,
    )
    page._bind_setting_card_styles(
        external_refresh_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._refresh_external_extensions_btn = PushButton("立即刷新", external_refresh_card)
    page._refresh_external_extensions_btn.clicked.connect(page._refresh_external_extension_specs)
    page._attach_setting_card_control(external_refresh_card, page._refresh_external_extensions_btn)
    page._external_extension_card.addSettingCard(external_refresh_card)
    page._external_extension_management_card = ExpandGroupSettingCard(
        FIF.FOLDER,
        _("扩展管理"),
        _("按类别管理外部扩展的启用状态。"),
        page._external_extension_card,
    )
    page._external_extension_management_card.setExpand(False)
    page._bind_theme_text_in_widget(
        page._external_extension_management_card,
        "扩展管理",
        body_text_style_sheet,
        first_only=True,
    )
    page._bind_theme_text_in_widget(
        page._external_extension_management_card,
        "按类别管理外部扩展的启用状态。",
        lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._external_extension_tabs = build_extension_category_tabs(
        page,
        page._external_extension_management_card,
        empty_hints=page._external_extension_empty_hints,
        option_layouts=page._external_extension_option_layouts,
    )
    page._external_extension_management_card.addGroupWidget(page._external_extension_tabs)
    page._external_extension_card.addSettingCard(page._external_extension_management_card)
    page._register_extension_height_watch_target(page._external_extension_management_card)
    page._register_extension_height_watch_target(page._external_extension_tabs)
    layout.addWidget(page._external_extension_card)

    page._extension_other_settings_card = SettingCardGroup(_("其他设置"), content)
    page._bind_theme_label_style(
        page._extension_other_settings_card.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )
    page._external_extension_number_decimals_card = SettingCard(
        FIF.INFO,
        _("浮点参数显示小数位"),
        _("控制扩展 number 参数使用 DoubleSpinBox 时默认显示的小数位数。"),
        page._extension_other_settings_card,
    )
    page._bind_setting_card_styles(
        page._external_extension_number_decimals_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    decimals_slider = Slider(Qt.Orientation.Horizontal, page._external_extension_number_decimals_card)
    decimals_slider.setRange(0, 12)
    decimals_slider.setSingleStep(1)
    decimals_slider.setPageStep(1)
    decimals_slider.setMinimumWidth(132)
    decimals_slider.valueChanged.connect(page._on_external_extension_number_decimals_changed)
    page._external_extension_number_decimals_slider = decimals_slider
    decimals_value = BodyLabel("6", page._external_extension_number_decimals_card)
    page._bind_theme_label_style(decimals_value, lambda: secondary_text_style_sheet(font_size=12))
    decimals_value.setMinimumWidth(24)
    page._external_extension_number_decimals_value_label = decimals_value
    decimals_row = page._build_setting_card_row(page._external_extension_number_decimals_card, decimals_slider, decimals_value)
    decimals_row_layout = decimals_row.layout()
    if isinstance(decimals_row_layout, QHBoxLayout):
        decimals_row_layout.setStretch(0, 1)
    page._attach_setting_card_control(page._external_extension_number_decimals_card, decimals_row)
    page._extension_other_settings_card.addSettingCard(page._external_extension_number_decimals_card)
    layout.addWidget(page._extension_other_settings_card)

    layout.addStretch()
    return outer


def build_general_tab(page) -> QWidget:
    outer = SmoothScrollArea()
    outer.setWidgetResizable(True)
    outer.setFrameShape(QFrame.Shape.NoFrame)
    outer.setStyleSheet(page._transparent_scroll_style())

    content = QWidget()
    content.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(content)
    layout.setSpacing(12)
    layout.setContentsMargins(*page._tab_content_margins())
    outer.setWidget(content)

    appearance_group = SettingCardGroup(_("外观"), content)
    page._appearance_card = appearance_group
    page._appearance_title = page._bind_theme_label_style(
        appearance_group.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )

    theme_card = SettingCard(FIF.BRUSH, _("主题"), _("切换浅色、深色或跟随系统。"), appearance_group)
    page._theme_label = theme_card.titleLabel
    page._bind_setting_card_styles(
        theme_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page.theme_combo = ComboBox(theme_card)
    page.theme_combo.setMinimumWidth(148)
    page.theme_combo.addItems([_("浅色"), _("深色"), _("跟随系统")])
    page.theme_combo.setCurrentIndex(2)
    page.theme_combo.currentIndexChanged.connect(page.on_theme_changed)
    page._attach_setting_card_control(theme_card, page.theme_combo)
    appearance_group.addSettingCard(theme_card)

    tree_mode_card = SettingCard(FIF.INFO, _("项目树长名称显示"), _("控制项目树长名称使用自动换行还是省略显示。"), appearance_group)
    page._tree_display_mode_label = tree_mode_card.titleLabel
    page._bind_setting_card_styles(
        tree_mode_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._tree_display_mode_combo = ComboBox(tree_mode_card)
    page._tree_display_mode_combo.setMinimumWidth(148)
    page._tree_display_mode_combo.addItems([_("自动换行"), _("部分隐藏")])
    current_mode = get_tree_name_display_mode()
    current_index = 1 if current_mode == "elide" else 0
    page._tree_display_mode_combo.setCurrentIndex(current_index)
    page._tree_display_mode_combo.currentIndexChanged.connect(page._on_tree_display_mode_changed)
    page._attach_setting_card_control(tree_mode_card, page._tree_display_mode_combo)
    appearance_group.addSettingCard(tree_mode_card)

    focus_mode_card = SwitchSettingCard(
        FIF.INFO,
        _("项目树页面专注模式"),
        _("开启后，功能页中的共享项目树只显示当前页面直接相关的节点。"),
        parent=appearance_group,
    )
    page._page_tree_focus_mode_card = focus_mode_card
    page._page_tree_focus_mode_checkbox = focus_mode_card
    page._page_tree_focus_mode_label = focus_mode_card.titleLabel
    page._page_tree_focus_mode_hint = focus_mode_card.contentLabel
    page._bind_setting_card_styles(
        focus_mode_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    focus_mode_card.setChecked(is_page_tree_focus_mode_enabled())
    focus_mode_card.checkedChanged.connect(page._on_page_tree_focus_mode_changed)
    appearance_group.addSettingCard(focus_mode_card)

    language_card = SettingCard(getattr(FIF, "LANGUAGE", FIF.INFO), _("语言"), _("切换应用界面语言，重启后生效。"), appearance_group)
    page._lang_card = language_card
    page._language_title = language_card.titleLabel
    page._bind_setting_card_styles(
        language_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._language_combo = ComboBox(language_card)
    page._language_combo.setMinimumWidth(148)
    page._language_keys = ["zh_CN", "en_US"]
    page._language_combo.addItems(["简体中文", "English"])
    current_language = get_ui_language()
    page._language_combo.setCurrentIndex(page._language_keys.index(current_language) if current_language in page._language_keys else 0)
    page._language_combo.currentIndexChanged.connect(page._on_language_changed)
    page._attach_setting_card_control(language_card, page._language_combo)
    appearance_group.addSettingCard(language_card)

    onboarding_card = SettingCard(
        FIF.HELP,
        _("新手引导"),
        _("点击后会重新播放主页引导，并重置数据管理、处理、可视化、分析和图片数字化页面的 TeachingTip 状态。"),
        appearance_group,
    )
    page._onboarding_label = onboarding_card.titleLabel
    page._onboarding_hint = onboarding_card.contentLabel
    page._bind_setting_card_styles(
        onboarding_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._replay_onboarding_btn = PushButton(_("重新显示引导"), onboarding_card)
    page._replay_onboarding_btn.clicked.connect(page.replay_onboarding_requested.emit)
    page._attach_setting_card_control(onboarding_card, page._replay_onboarding_btn)
    appearance_group.addSettingCard(onboarding_card)
    layout.addWidget(appearance_group)

    # ── 自动保存 ──
    auto_save_group = SettingCardGroup(_("自动保存"), content)
    page._auto_save_group = auto_save_group
    page._auto_save_group_title = page._bind_theme_label_style(
        auto_save_group.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )

    auto_save_enable_card = SwitchSettingCard(
        FIF.SAVE,
        _("启用自动保存"),
        _("定时自动保存当前项目，不影响手动保存操作。"),
        parent=auto_save_group,
    )
    page._auto_save_enable_card = auto_save_enable_card
    page._bind_setting_card_styles(
        auto_save_enable_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    auto_save_enable_card.setChecked(get_auto_save_enabled())
    auto_save_enable_card.checkedChanged.connect(page._on_auto_save_enabled_changed)
    auto_save_group.addSettingCard(auto_save_enable_card)

    auto_save_interval_card = SettingCard(
        FIF.UPDATE,
        _("自动保存间隔"),
        _("自动保存之间的等待时间。更改后立即生效。"),
        parent=auto_save_group,
    )
    page._auto_save_interval_card = auto_save_interval_card
    page._bind_setting_card_styles(
        auto_save_interval_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )

    interval_spin = SpinBox(auto_save_interval_card)
    interval_spin.setRange(1, 999)
    total_seconds = get_auto_save_interval_seconds()
    # Determine initial unit: use minutes if ≥ 60, hours if ≥ 3600, else seconds
    if total_seconds >= 3600:
        interval_spin.setValue(max(1, total_seconds // 3600))
        default_unit_idx = 2
    elif total_seconds >= 60:
        interval_spin.setValue(max(1, total_seconds // 60))
        default_unit_idx = 1
    else:
        interval_spin.setValue(max(1, total_seconds))
        default_unit_idx = 0
    page._auto_save_interval_spin = interval_spin
    interval_spin.valueChanged.connect(page._on_auto_save_interval_changed)

    interval_unit = ComboBox(auto_save_interval_card)
    interval_unit.addItems([_("秒"), _("分"), _("时")])
    interval_unit.setCurrentIndex(default_unit_idx)
    page._auto_save_interval_unit = interval_unit
    interval_unit.currentIndexChanged.connect(page._on_auto_save_interval_unit_changed)

    row = page._build_setting_card_row(auto_save_interval_card, interval_spin, interval_unit)
    page._attach_setting_card_control(auto_save_interval_card, row)
    auto_save_group.addSettingCard(auto_save_interval_card)

    layout.addWidget(auto_save_group)
    layout.addStretch()
    return outer


def build_shortcuts_tab(page) -> QWidget:
    outer = SmoothScrollArea()
    outer.setWidgetResizable(True)
    outer.setFrameShape(QFrame.Shape.NoFrame)
    outer.setStyleSheet(page._transparent_scroll_style())

    content = QWidget()
    content.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(content)
    layout.setSpacing(12)
    layout.setContentsMargins(*page._tab_content_margins())
    outer.setWidget(content)

    page._shortcuts_card = SettingCardGroup(_("快捷键"), content)
    page._shortcuts_title = page._shortcuts_card.titleLabel
    page._bind_theme_label_style(page._shortcuts_title, lambda: card_title_style_sheet(font_size=18))

    sc_content = QWidget(page._shortcuts_card)
    sc_form = QFormLayout(sc_content)
    sc_form.setSpacing(6)
    sc_form.setContentsMargins(0, 4, 0, 4)

    for definition in shortcut_manager.list_definitions():
        action = definition.action
        label = f"[{definition.category}] {definition.label}"
        edit = QKeySequenceEdit(sc_content)
        edit.setKeySequence(QKeySequence(shortcut_manager.get(action)))
        page._apply_shortcut_edit_style(edit, focused=False)
        edit.installEventFilter(page)
        row_lbl = BodyLabel(label + ":", sc_content)
        page._bind_theme_label_style(row_lbl, body_text_style_sheet)

        conflict_lbl = BodyLabel("", sc_content)
        page._bind_theme_label_style(conflict_lbl, lambda: error_text_style_sheet(font_size=10))
        conflict_lbl.setVisible(False)

        edit_col = QWidget(sc_content)
        ecol_layout = QVBoxLayout(edit_col)
        ecol_layout.setContentsMargins(0, 0, 0, 0)
        ecol_layout.setSpacing(1)
        ecol_layout.addWidget(edit)
        ecol_layout.addWidget(conflict_lbl)

        sc_form.addRow(row_lbl, edit_col)
        page._shortcut_edits[action] = edit
        page._shortcut_rows[action] = edit_col
        page._shortcut_labels.append(row_lbl)
        page._conflict_labels[action] = conflict_lbl
        edit.keySequenceChanged.connect(lambda ks, a=action: page._check_shortcut_conflict(a, ks))

    btn_container = QWidget(page._shortcuts_card)
    btn_row = QHBoxLayout(btn_container)
    btn_row.setContentsMargins(0, 0, 0, 0)
    btn_row.setSpacing(8)
    apply_btn = PushButton(_("应用快捷键"), btn_container)
    apply_btn.clicked.connect(page._on_apply_shortcuts)
    reset_btn = PushButton(_("恢复默认"), btn_container)
    reset_btn.clicked.connect(page._on_reset_shortcuts)
    btn_row.addWidget(apply_btn)
    btn_row.addWidget(reset_btn)
    btn_row.addStretch()

    shortcuts_editor_card = ExpandGroupSettingCard(
        FIF.INFO,
        _("快捷键映射"),
        _("所有已注册的界面动作都会显示在这里。点击输入框后按下新快捷键，再点击\u201c应用快捷键\u201d保存。"),
        page._shortcuts_card,
    )
    page._shortcuts_editor_card = shortcuts_editor_card
    page._bind_theme_text_in_widget(
        shortcuts_editor_card,
        _("快捷键映射"),
        body_text_style_sheet,
        first_only=True,
    )
    page._bind_theme_text_in_widget(
        shortcuts_editor_card,
        _("所有已注册的界面动作都会显示在这里。点击输入框后按下新快捷键，再点击\u201c应用快捷键\u201d保存。"),
        lambda: placeholder_text_style_sheet(font_size=11),
    )
    shortcuts_editor_card.setExpand(True)
    shortcuts_editor_card.viewLayout.setContentsMargins(16, 0, 16, 0)
    filter_container = QWidget(shortcuts_editor_card)
    filter_layout = QVBoxLayout(filter_container)
    filter_layout.setContentsMargins(0, 0, 0, 0)
    filter_layout.setSpacing(6)
    page._shortcut_filter_edit = LineEdit(filter_container)
    page._shortcut_filter_edit.setPlaceholderText(_("筛选快捷键动作，例如\u201c分析\u201d或\u201c导出\u201d"))
    page._shortcut_filter_edit.setClearButtonEnabled(True)
    page._shortcut_filter_edit.setToolTip(_("按动作名称、分类或关键词筛选快捷键"))
    page._shortcut_filter_edit.textChanged.connect(page._filter_shortcut_rows)
    page._apply_shortcut_filter_style()
    page._shortcut_filter_edit.setMinimumWidth(280)
    filter_layout.addWidget(page._shortcut_filter_edit)
    shortcuts_editor_card.addGroupWidget(filter_container)
    shortcuts_editor_card.addGroupWidget(sc_content)
    shortcuts_editor_card.addGroupWidget(btn_container)
    page._shortcuts_card.addSettingCard(shortcuts_editor_card)

    layout.addWidget(page._shortcuts_card)
    layout.addStretch()
    return outer


def build_ai_tab(page) -> QWidget:
    outer = SmoothScrollArea()
    outer.setWidgetResizable(True)
    outer.setFrameShape(QFrame.Shape.NoFrame)
    outer.setStyleSheet(page._transparent_scroll_style())

    content = QWidget()
    content.setStyleSheet("background: transparent;")
    layout = QVBoxLayout(content)
    layout.setSpacing(12)
    layout.setContentsMargins(*page._tab_content_margins())
    outer.setWidget(content)

    # ── AI 接口配置 ──
    page._ai_card = CardWidget(content)
    ai_layout = QVBoxLayout(page._ai_card)
    page._apply_card_layout_metrics(ai_layout)

    ai_title = BodyLabel("AI 接口", page._ai_card)
    page._bind_theme_label_style(ai_title, lambda: card_title_style_sheet(font_size=18))
    ai_layout.addWidget(ai_title)

    page._ai_provider_hint = BodyLabel("", page._ai_card)
    page._ai_provider_hint.setWordWrap(True)
    page._bind_theme_label_style(page._ai_provider_hint, lambda: placeholder_text_style_sheet(font_size=11))
    ai_layout.addWidget(page._ai_provider_hint)

    form = QFormLayout()
    form.setSpacing(8)

    page._ai_provider_combo = ComboBox(page._ai_card)
    for provider_key in page._provider_keys:
        page._ai_provider_combo.addItem(get_provider_preset(provider_key)["label"])
    page._ai_provider_combo.currentIndexChanged.connect(page._on_ai_provider_changed)
    form.addRow("接口类型:", page._ai_provider_combo)

    page._ai_url_edit = LineEdit(page._ai_card)
    page._ai_url_edit.setPlaceholderText("例: https://api.openai.com/v1  或  http://localhost:11434")
    page._ai_url_edit.setToolTip("AI 接口的 Base URL，OpenAI 填官方地址，Ollama 填本地地址")
    form.addRow("API 地址:", page._ai_url_edit)

    page._ai_key_edit = LineEdit(page._ai_card)
    page._ai_key_edit.setPlaceholderText("sk-...（OpenAI 必填，Ollama 可选）")
    page._ai_key_edit.setToolTip("API 认证密钥，OpenAI/商用接口通常必填；Ollama 本地部署可留空，服务端代理可填写")
    form.addRow("API Key:", page._ai_key_edit)

    page._ai_model_preset_combo = ComboBox(page._ai_card)
    page._ai_model_preset_combo.currentIndexChanged.connect(page._on_model_preset_changed)
    form.addRow("推荐模型:", page._ai_model_preset_combo)

    page._ai_model_edit = LineEdit(page._ai_card)
    form.addRow("模型名称:", page._ai_model_edit)

    page._ai_timeout_edit = LineEdit(page._ai_card)
    page._ai_timeout_edit.setPlaceholderText("60")
    page._ai_timeout_edit.setToolTip("等待 AI 响应的超时秒数，网络较慢或模型较大时可适当增大")
    form.addRow("超时(秒):", page._ai_timeout_edit)

    page._ai_temperature_edit = LineEdit(page._ai_card)
    page._ai_temperature_edit.setPlaceholderText("0.7")
    page._ai_temperature_edit.setToolTip("控制回复随机性：0 = 完全确定性，1-2 = 创造性更高。\n一般推荐 0.5~0.8，精确计算任务建议 0")
    form.addRow("Temperature:", page._ai_temperature_edit)

    page._ai_top_p_edit = LineEdit(page._ai_card)
    page._ai_top_p_edit.setPlaceholderText("1.0")
    page._ai_top_p_edit.setToolTip("核采样概率阈值，与 Temperature 配合使用。\n1.0 表示不限制，通常保持默认 1.0 即可")
    form.addRow("Top P:", page._ai_top_p_edit)

    page._ai_max_tokens_edit = LineEdit(page._ai_card)
    page._ai_max_tokens_edit.setPlaceholderText("2048")
    page._ai_max_tokens_edit.setToolTip("单次回复的最大 token 数量，超出后截断\n日常对话 2048 足够，长文档分析可调高至 4096")
    form.addRow("Max Tokens:", page._ai_max_tokens_edit)

    page._ai_ollama_keep_alive_edit = LineEdit(page._ai_card)
    page._ai_ollama_keep_alive_edit.setPlaceholderText("5m")
    page._ai_ollama_keep_alive_edit.setToolTip("Ollama 模型在内存中保持加载的时长\n格式：数字+单位，如 5m / 1h / 0（永久）。仅 Ollama 接口生效")
    form.addRow("Ollama Keep-Alive:", page._ai_ollama_keep_alive_edit)

    page._ai_ollama_num_ctx_edit = LineEdit(page._ai_card)
    page._ai_ollama_num_ctx_edit.setPlaceholderText("4096")
    page._ai_ollama_num_ctx_edit.setToolTip("Ollama 模型上下文窗口大小（token 数量）\n越大可处理更长的历史记录，但内存占用也更高。仅 Ollama 接口生效")
    form.addRow("Ollama Num Ctx:", page._ai_ollama_num_ctx_edit)

    page._ai_system_prompt_edit = PlainTextEdit(page._ai_card)
    page._ai_system_prompt_edit.setPlaceholderText("全局系统提示，例如：优先用中文回答，并保持术语统一。")
    page._ai_system_prompt_edit.setFixedHeight(96)
    form.addRow("系统提示:", page._ai_system_prompt_edit)

    ai_layout.addLayout(form)

    ai_btn_row = QHBoxLayout()
    save_ai_btn = PrimaryPushButton("保存配置")
    save_ai_btn.clicked.connect(page._save_ai_config)
    test_ai_btn = PushButton("测试连接")
    test_ai_btn.clicked.connect(page._test_ai_connection)
    page._ai_refresh_models_btn = PushButton("探测模型")
    page._ai_refresh_models_btn.clicked.connect(page._refresh_available_models)
    ai_btn_row.addWidget(save_ai_btn)
    ai_btn_row.addWidget(test_ai_btn)
    ai_btn_row.addWidget(page._ai_refresh_models_btn)
    ai_btn_row.addStretch()
    ai_layout.addLayout(ai_btn_row)

    layout.addWidget(page._ai_card)

    page._ai_tool_items: list[dict] = []  # {source, type, name, desc, item}

    page._ai_tools_card = CardWidget(content)
    ai_tools_layout = QVBoxLayout(page._ai_tools_card)
    page._apply_card_layout_metrics(ai_tools_layout)

    ai_tools_title = BodyLabel("AI 工具管理", page._ai_tools_card)
    page._bind_theme_label_style(ai_tools_title, lambda: card_title_style_sheet(font_size=18))
    ai_tools_layout.addWidget(ai_tools_title)

    page._ai_tools_project_label = BodyLabel("当前项目: 未打开", page._ai_tools_card)
    page._bind_theme_label_style(page._ai_tools_project_label, body_text_style_sheet)
    ai_tools_layout.addWidget(page._ai_tools_project_label)

    page._ai_tools_summary_label = BodyLabel("内置 0 · Prompt 0 · Skill 0 · Agent 0", page._ai_tools_card)
    page._bind_theme_label_style(page._ai_tools_summary_label, secondary_text_style_sheet)
    ai_tools_layout.addWidget(page._ai_tools_summary_label)

    # 工具选择下拉框
    selector_row = QHBoxLayout()
    selector_row.addWidget(BodyLabel("选择工具:", page._ai_tools_card))
    page._ai_tool_selector = ComboBox(page._ai_tools_card)
    page._ai_tool_selector.setMinimumWidth(300)
    page._ai_tool_selector.currentIndexChanged.connect(page._on_ai_tool_selected)
    selector_row.addWidget(page._ai_tool_selector, 1)
    ai_tools_layout.addLayout(selector_row)

    # 工具详情卡片
    page._ai_tool_detail_card = CardWidget(page._ai_tools_card)
    detail_layout = QVBoxLayout(page._ai_tool_detail_card)
    detail_layout.setSpacing(6)
    detail_layout.setContentsMargins(12, 10, 12, 10)

    detail_name_row = QHBoxLayout()
    detail_name_row.addWidget(BodyLabel("名称:", page._ai_tool_detail_card))
    page._ai_tool_detail_name = BodyLabel("—", page._ai_tool_detail_card)
    page._bind_theme_label_style(
        page._ai_tool_detail_name,
        lambda: f"{body_text_style_sheet()} font-weight: bold;",
    )
    detail_name_row.addWidget(page._ai_tool_detail_name, 1)
    detail_layout.addLayout(detail_name_row)

    detail_type_row = QHBoxLayout()
    detail_type_row.addWidget(BodyLabel("类型:", page._ai_tool_detail_card))
    page._ai_tool_detail_type = BodyLabel("—", page._ai_tool_detail_card)
    page._bind_theme_label_style(page._ai_tool_detail_type, secondary_text_style_sheet)
    detail_type_row.addWidget(page._ai_tool_detail_type, 1)
    detail_layout.addLayout(detail_type_row)

    detail_desc_row = QHBoxLayout()
    detail_desc_row.addWidget(BodyLabel("描述:", page._ai_tool_detail_card))
    page._ai_tool_detail_desc = BodyLabel("—", page._ai_tool_detail_card)
    page._ai_tool_detail_desc.setWordWrap(True)
    detail_desc_row.addWidget(page._ai_tool_detail_desc, 1)
    detail_layout.addLayout(detail_desc_row)

    detail_action_row = QHBoxLayout()
    page._ai_tool_edit_btn = PushButton("编辑", page._ai_tool_detail_card)
    page._ai_tool_edit_btn.setEnabled(False)
    page._ai_tool_edit_btn.clicked.connect(page._on_edit_selected_ai_tool)
    page._ai_tool_delete_btn = PushButton("删除", page._ai_tool_detail_card)
    page._ai_tool_delete_btn.setEnabled(False)
    page._ai_tool_delete_btn.clicked.connect(page._on_delete_selected_ai_tool)
    detail_action_row.addWidget(page._ai_tool_edit_btn)
    detail_action_row.addWidget(page._ai_tool_delete_btn)
    detail_action_row.addStretch()
    detail_layout.addLayout(detail_action_row)

    ai_tools_layout.addWidget(page._ai_tool_detail_card)

    # 创建按钮行
    ai_tools_btn_row = QHBoxLayout()
    new_prompt_btn = PushButton("新建 Prompt", page._ai_tools_card)
    new_prompt_btn.clicked.connect(lambda: page._open_ai_tool_dialog("prompt"))
    new_skill_btn = PushButton("新建 Skill", page._ai_tools_card)
    new_skill_btn.clicked.connect(lambda: page._open_ai_tool_dialog("skill"))
    new_agent_btn = PushButton("新建 Agent", page._ai_tools_card)
    new_agent_btn.clicked.connect(lambda: page._open_ai_tool_dialog("agent"))
    refresh_ai_tools_btn = PushButton("刷新", page._ai_tools_card)
    refresh_ai_tools_btn.clicked.connect(page._refresh_ai_tools_panel)
    ai_tools_btn_row.addWidget(new_prompt_btn)
    ai_tools_btn_row.addWidget(new_skill_btn)
    ai_tools_btn_row.addWidget(new_agent_btn)
    ai_tools_btn_row.addWidget(refresh_ai_tools_btn)
    ai_tools_btn_row.addStretch()
    ai_tools_layout.addLayout(ai_tools_btn_row)

    layout.addWidget(page._ai_tools_card)

    # 兼容字段（隐藏）
    from qfluentwidgets import ListWidget as _ListWidget
    page._tmpl_card = CardWidget(content)
    page._tmpl_card.hide()
    page._tmpl_list = _ListWidget(page._tmpl_card)

    layout.addStretch()
    return outer
