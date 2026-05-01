from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget
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
    SwitchSettingCard,
)

from core.shortcut_manager import shortcut_manager
from core.ui_preferences import get_tree_name_display_mode, is_page_tree_focus_mode_enabled
from ui.widgets.navigation_stack import SegmentedStackWidget
from ui.theme import (
    body_text_style_sheet,
    card_title_style_sheet,
    placeholder_text_style_sheet,
    secondary_text_style_sheet,
)

_EXTENSION_CATEGORY_TABS_MAX_HEIGHT = 60750
_EXTENSION_CATEGORY_TABS_HEIGHT_MULTIPLIER = 3


class MutableFolderListSettingCard(FolderListSettingCard):

    def __init__(self, title: str, content: str | None, folders: list[str], *, directory: str, parent: QWidget | None = None):
        from qfluentwidgets.common.config import ConfigItem

        self._config_item = ConfigItem("SettingsPage", "externalExtensionDirs", list(folders or []))
        super().__init__(self._config_item, title, content or "", directory=directory, parent=parent)

    def setFolders(self, folders: list[str]) -> None:
        from qfluentwidgets.common.config import qconfig

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


def build_extension_category_tabs(page, parent: QWidget, *, empty_hints: dict[str, BodyLabel], option_layouts: dict[str, QVBoxLayout]) -> QWidget:
    tabs = SegmentedStackWidget(parent)
    tabs.setMaximumHeight(_EXTENSION_CATEGORY_TABS_MAX_HEIGHT)
    for category, label in (("plot", "绘图扩展"), ("processing", "处理扩展"), ("analysis", "分析扩展"), ("digitize", "数字化扩展")):
        tab_page = QWidget(parent)
        page_layout = QVBoxLayout(tab_page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(6)
        empty_hint = BodyLabel(f"当前未发现{label}。", tab_page)
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

    extension_group = SettingCardGroup("扩展", content)
    page._extension_card = extension_group
    page._extension_title = page._bind_theme_label_style(
        extension_group.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )
    page._extension_status_card = SettingCard(FIF.INFO, "扩展状态", "查看当前扩展加载情况与失败详情。", extension_group)
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

    page._extension_actions_card = SettingCard(FIF.SYNC, "应用扩展设置", "保存当前启用状态与目录配置，并重新加载扩展。", extension_group)
    page._bind_setting_card_styles(
        page._extension_actions_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._save_extension_settings_btn = PrimaryPushButton("保存并重载扩展", page._extension_actions_card)
    page._save_extension_settings_btn.clicked.connect(page._save_extension_settings)
    page._attach_setting_card_control(page._extension_actions_card, page._save_extension_settings_btn)
    extension_group.addSettingCard(page._extension_actions_card)
    layout.addWidget(extension_group)

    page._builtin_extension_card = SettingCardGroup("内置扩展", content)
    page._bind_theme_label_style(
        page._builtin_extension_card.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )
    page._builtin_extensions_enabled_checkbox = SwitchSettingCard(
        FIF.DOWNLOAD,
        "启用内置扩展",
        "关闭后保留内置扩展配置，但不参与加载。",
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
        "扩展管理",
        "按类别管理内置扩展的启用状态。",
        page._builtin_extension_card,
    )
    page._builtin_extension_management_card.setExpand(False)
    page._bind_theme_text_in_widget(
        page._builtin_extension_management_card,
        "扩展管理",
        lambda: card_title_style_sheet(font_size=18),
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

    page._external_extension_card = SettingCardGroup("外部扩展", content)
    page._bind_theme_label_style(
        page._external_extension_card.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )
    page._external_extensions_enabled_checkbox = SwitchSettingCard(
        FIF.FOLDER,
        "启用外部扩展",
        "关闭后保留目录配置，但不加载外部扩展。",
        parent=page._external_extension_card,
    )
    page._bind_setting_card_styles(
        page._external_extensions_enabled_checkbox,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._external_extensions_enabled_checkbox.checkedChanged.connect(page._on_external_extensions_enabled_changed)
    page._external_extension_card.addSettingCard(page._external_extensions_enabled_checkbox)
    page._external_extensions_dirs_card = MutableFolderListSettingCard(
        "外部扩展目录",
        "可添加多个文件夹；保存后会统一扫描并重载。",
        [],
        directory="~/.config/aline/extensions",
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
        "刷新外部扩展扫描",
        "按当前目录配置重新探测外部扩展，不会修改保存设置。",
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
        "扩展管理",
        "按类别管理外部扩展的启用状态。",
        page._external_extension_card,
    )
    page._external_extension_management_card.setExpand(False)
    page._bind_theme_text_in_widget(
        page._external_extension_management_card,
        "扩展管理",
        lambda: card_title_style_sheet(font_size=18),
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

    page._extension_other_settings_card = SettingCardGroup("其他设置", content)
    page._bind_theme_label_style(
        page._extension_other_settings_card.titleLabel,
        lambda: card_title_style_sheet(font_size=18),
    )
    page._external_extension_number_decimals_card = SettingCard(
        FIF.INFO,
        "浮点参数显示小数位",
        "控制扩展 number 参数使用 DoubleSpinBox 时默认显示的小数位数。",
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
