from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QListWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action, BodyLabel, CaptionLabel, CardWidget, CheckBox, ComboBox,
    ExpandGroupSettingCard, FluentIcon as FIF, FolderListSettingCard,
    IndeterminateProgressRing, InfoBar, InfoBarPosition,
    LineEdit, ListWidget, MessageBoxBase, PlainTextEdit,
    PrimaryPushButton, PushButton,
    RadioButton, RoundMenu, SegmentedWidget, SettingCard, SettingCardGroup, Slider,
    SmoothScrollArea, SpinBox, StrongBodyLabel, SubtitleLabel,
    SwitchButton, SwitchSettingCard, TableWidget, TextWrap, ToolButton,
)

from core.ai.providers import get_provider_preset
from core.extension_api import build_extension_entry
from core.extension_settings import (
    default_external_extensions_directory,
    get_builtin_extension_settings,
    get_external_extension_settings,
    set_builtin_extension_settings,
    set_external_extension_sandbox_enabled,
    set_external_extension_settings,
)
from core.shortcut_manager import shortcut_manager
from core.ui_preferences import (
    get_auto_save_enabled,
    get_auto_save_interval_seconds,
    get_interface_scale,
    get_tree_name_display_mode,
    get_ui_font_family,
    get_ui_language,
    is_page_tree_focus_mode_enabled,
)
from ui.theme import effective_ui_font_family, install_fluent_tooltip, list_installed_ui_font_families
from ui.widgets.navigation_stack import SegmentedStackWidget
from ui.theme import (
    body_text_style_sheet,
    card_title_style_sheet,
    error_text_style_sheet,
    placeholder_text_style_sheet,
    secondary_text_style_sheet,
)
from core.i18n import _

_EXTENSION_CATEGORIES = (("plot", _("绘图扩展")), ("processing", _("处理扩展")), ("analysis", _("分析扩展")), ("digitize", _("数字化扩展")))


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


class ExtensionManageDialog(MessageBoxBase):
    """Fluent-style dialog for managing extensions with a table of checkbox + name + actions."""

    _CATEGORY_LABELS = _EXTENSION_CATEGORIES

    def __init__(self, page, *, source: str, parent=None):
        super().__init__(parent)
        self._page = page
        self._source = str(source or "").strip().lower()
        self.yesButton.hide()
        self.cancelButton.setText(_("关闭"))

        self._tabs = SegmentedStackWidget(self.widget)

        for category, label in self._CATEGORY_LABELS:
            tab_page = QWidget(self.widget)
            layout = QVBoxLayout(tab_page)
            layout.setContentsMargins(8, 8, 8, 8)

            table = TableWidget(tab_page)
            table.setBorderVisible(True)
            table.setBorderRadius(4)
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels([
                _("启用"), _("扩展名称"), _("打开"), _("删除")
            ])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.setColumnWidth(0, 60)
            table.setColumnWidth(2, 60)
            table.setColumnWidth(3, 60)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            table.verticalHeader().hide()
            layout.addWidget(table, 1)
            self._tabs.addTab(tab_page, label, route_key=category)
            self._populate_table(category, table)

        self.viewLayout.addWidget(self._tabs, 1)

        # Bottom buttons row (external only)
        if self._source == "external":
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            refresh_btn = PushButton(FIF.SYNC, _("刷新扫描"))
            refresh_btn.clicked.connect(self._on_refresh)
            add_btn = PushButton(FIF.ADD, _("添加文件"))
            add_btn.clicked.connect(self._on_add_file)
            btn_row.addWidget(refresh_btn)
            btn_row.addWidget(add_btn)
            btn_row.addStretch()
            self.viewLayout.addLayout(btn_row)

        self.widget.setMinimumWidth(580)
        self.widget.setMinimumHeight(420)

    def _populate_table(self, category: str, table: TableWidget) -> None:
        from core.extension_registry import extension_registry
        table.setRowCount(0)

        category_map = {
            "plot": extension_registry.list_plot,
            "processing": extension_registry.list_processing,
            "analysis": extension_registry.list_analysis,
            "digitize": extension_registry.list_digitize,
        }
        getter = category_map.get(category)
        if getter is None:
            return

        details = extension_registry.get_last_load_details()
        path_by_type: dict[str, str] = {}
        for entry in details.get("loaded", []):
            ext_map = entry.get("extensions", {})
            for tid in ext_map.get(category, []):
                path_by_type[tid] = str(entry.get("path", "") or "")

        disabled_ids = self._current_disabled_ids()

        rows = []
        for ext in getter():
            entry = build_extension_entry(ext)
            type_id = str(entry.get("type") or "").strip()
            if not type_id:
                continue
            source_kind = str(entry.get("source_kind", "builtin") or "builtin").strip().lower()
            if source_kind != self._source:
                continue
            ext_name = str(entry.get("name") or type_id)
            file_path = path_by_type.get(type_id, "")
            rows.append((type_id, ext_name, source_kind, file_path))

        rows.sort(key=lambda r: r[1].lower())

        for row_idx, (type_id, ext_name, source_kind, file_path) in enumerate(rows):
            table.insertRow(row_idx)

            # Column 0: SwitchButton
            switch = SwitchButton(table)
            switch.setOnText("")
            switch.setOffText("")
            switch.setChecked(type_id not in disabled_ids)
            switch.checkedChanged.connect(
                lambda checked, tid=type_id: self._on_toggle(tid, checked)
            )
            switch.setFixedWidth(48)
            cell_widget = QWidget(table)
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(4, 0, 4, 0)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(switch)
            table.setCellWidget(row_idx, 0, cell_widget)

            # Column 1: Extension name
            name_item = QTableWidgetItem(ext_name)
            name_item.setToolTip(file_path or "")
            table.setItem(row_idx, 1, name_item)

            # Column 2: Open button
            open_btn = ToolButton(FIF.VIEW, table)
            open_btn.setFixedSize(28, 28)
            open_btn.setToolTip(_("在编辑器中打开"))
            install_fluent_tooltip(open_btn, delay=400)
            open_btn.clicked.connect(lambda checked=False, fp=file_path: self._open_in_editor(fp))
            open_btn.setEnabled(bool(file_path))
            cell_widget2 = QWidget(table)
            cell_layout2 = QHBoxLayout(cell_widget2)
            cell_layout2.setContentsMargins(4, 0, 4, 0)
            cell_layout2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout2.addWidget(open_btn)
            table.setCellWidget(row_idx, 2, cell_widget2)

            # Column 3: Delete button (external only)
            if source_kind == "external":
                del_btn = ToolButton(FIF.DELETE, table)
                del_btn.setFixedSize(28, 28)
                del_btn.setToolTip(_("删除扩展"))
                install_fluent_tooltip(del_btn, delay=400)
                del_btn.clicked.connect(
                    lambda checked=False, fp=file_path, tid=type_id: self._on_delete(fp, tid)
                )
                cell_widget3 = QWidget(table)
                cell_layout3 = QHBoxLayout(cell_widget3)
                cell_layout3.setContentsMargins(4, 0, 4, 0)
                cell_layout3.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_layout3.addWidget(del_btn)
                table.setCellWidget(row_idx, 3, cell_widget3)

    def _current_disabled_ids(self) -> set[str]:
        if self._source == "builtin":
            _, disabled = get_builtin_extension_settings()
        else:
            _, disabled = get_external_extension_settings()
        return {str(i).strip() for i in disabled}

    def _on_toggle(self, type_id: str, checked: bool) -> None:
        if self._source == "builtin":
            load_enabled, disabled = get_builtin_extension_settings()
            if checked and type_id in disabled:
                disabled = [i for i in disabled if i != type_id]
            elif not checked and type_id not in disabled:
                disabled = list(disabled) + [type_id]
            set_builtin_extension_settings(load_enabled, disabled)
        else:
            load_enabled, disabled = get_external_extension_settings()
            if checked and type_id in disabled:
                disabled = [i for i in disabled if i != type_id]
            elif not checked and type_id not in disabled:
                disabled = list(disabled) + [type_id]
            set_external_extension_settings(load_enabled, disabled)

    def _open_in_editor(self, file_path: str) -> None:
        import subprocess, sys
        if not file_path:
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["notepad", file_path])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", file_path])
            else:
                subprocess.Popen(["xdg-open", file_path])
        except OSError:
            pass

    def _on_delete(self, file_path: str, type_id: str) -> None:
        from core.extension_settings import delete_external_extension_file
        from pathlib import Path
        from qfluentwidgets import MessageBox

        name = Path(file_path).name
        msg = MessageBox(_("确认删除"), _("确定要删除外部扩展文件") + f" {name}?", self)
        if not msg.exec():
            return
        try:
            delete_external_extension_file(file_path)
        except (PermissionError, FileNotFoundError, ValueError) as exc:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(_("删除失败"), str(exc), parent=self, position=InfoBarPosition.TOP)
            return
        # Refresh the dialog
        current_idx = self._tabs.currentIndex()
        self._tabs.widget(current_idx).deleteLater()
        for i in range(self._tabs.count()):
            cat, _cat_label = self._CATEGORY_LABELS[i]
            tab = self._tabs.widget(i)
            if tab is not None:
                old_layout = tab.layout()
                if old_layout:
                    QWidget().setLayout(old_layout)
                new_layout = QVBoxLayout(tab)
                new_layout.setContentsMargins(8, 8, 8, 8)
                table = TableWidget(tab)
                table.setBorderVisible(True)
                table.setBorderRadius(4)
                table.setColumnCount(4)
                table.setHorizontalHeaderLabels([_("启用"), _("扩展名称"), _("打开"), _("删除")])
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                table.setColumnWidth(0, 60)
                table.setColumnWidth(2, 60)
                table.setColumnWidth(3, 60)
                table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                table.verticalHeader().hide()
                new_layout.addWidget(table, 1)
                self._populate_table(cat, table)
        self._tabs.setCurrentIndex(current_idx)
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.success(_("已删除"), name, parent=self, position=InfoBarPosition.TOP)

    def _on_refresh(self) -> None:
        self._page._refresh_external_extension_specs()
        # Rebuild all tabs
        for i in range(self._tabs.count()):
            cat, _cat_label = self._CATEGORY_LABELS[i]
            tab = self._tabs.widget(i)
            if tab is None:
                continue
            old_layout = tab.layout()
            if old_layout:
                QWidget().setLayout(old_layout)
            new_layout = QVBoxLayout(tab)
            new_layout.setContentsMargins(8, 8, 8, 8)
            table = TableWidget(tab)
            table.setBorderVisible(True)
            table.setBorderRadius(4)
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels([_("启用"), _("扩展名称"), _("打开"), _("删除")])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.setColumnWidth(0, 60)
            table.setColumnWidth(2, 60)
            table.setColumnWidth(3, 60)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            table.verticalHeader().hide()
            new_layout.addWidget(table, 1)
            self._populate_table(cat, table)

    def _on_add_file(self) -> None:
        self._page._on_add_external_extension()
        self._on_refresh()


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
    builtin_mgr_card = SettingCard(
        FIF.DEVELOPER_TOOLS, _("管理扩展"), _("查看所有扩展，在编辑器中打开，或在文件夹中定位。"),
        page._builtin_extension_card,
    )
    page._bind_setting_card_styles(
        builtin_mgr_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._builtin_mgr_btn = PushButton(_("打开管理"), builtin_mgr_card)
    page._builtin_mgr_btn.clicked.connect(lambda: page._on_open_extension_manager("builtin"))
    page._attach_setting_card_control(builtin_mgr_card, page._builtin_mgr_btn)
    page._builtin_extension_card.addSettingCard(builtin_mgr_card)
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
    page._external_extensions_sandbox_checkbox.checkedChanged.connect(
        lambda checked: set_external_extension_sandbox_enabled(checked)
    )
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

    external_mgr_card = SettingCard(
        FIF.DEVELOPER_TOOLS, _("管理扩展"), _("查看所有扩展，在编辑器中打开，或在文件夹中定位。"),
        page._external_extension_card,
    )
    page._bind_setting_card_styles(
        external_mgr_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._external_mgr_btn = PushButton(_("打开管理"), external_mgr_card)
    page._external_mgr_btn.clicked.connect(lambda: page._on_open_extension_manager("external"))
    page._attach_setting_card_control(external_mgr_card, page._external_mgr_btn)
    page._external_extension_card.addSettingCard(external_mgr_card)
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

    # ── 界面缩放 ──
    zoom_card = SettingCard(getattr(FIF, "ZOOM", FIF.VIEW), _("界面缩放"), _("调整界面元素和字体的大小，重启后生效。"), appearance_group)
    page._zoom_card = zoom_card
    page._zoom_card_title = zoom_card.titleLabel
    page._bind_setting_card_styles(
        zoom_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._zoom_combo = ComboBox(zoom_card)
    page._zoom_combo.setMinimumWidth(148)
    page._zoom_combo.addItems(["100%", "125%", "150%", "175%", "200%", _("跟随系统设置")])
    page._zoom_keys = [1.0, 1.25, 1.5, 1.75, 2.0, 0.0]
    current_scale = get_interface_scale()
    current_zoom_index = page._zoom_keys.index(current_scale) if current_scale in page._zoom_keys else len(page._zoom_keys) - 1
    page._zoom_combo.setCurrentIndex(current_zoom_index)
    page._zoom_combo.currentIndexChanged.connect(page._on_interface_scale_changed)
    page._attach_setting_card_control(zoom_card, page._zoom_combo)
    appearance_group.addSettingCard(zoom_card)

    font_card = SettingCard(getattr(FIF, "FONT", FIF.INFO), _("界面字体"), _("自动检测系统已安装字体，并立即应用到整个界面。"), appearance_group)
    page._ui_font_title = font_card.titleLabel
    page._bind_setting_card_styles(
        font_card,
        title_style=body_text_style_sheet,
        content_style=lambda: placeholder_text_style_sheet(font_size=11),
    )
    page._ui_font_combo = ComboBox(font_card)
    page._ui_font_combo.setMinimumWidth(220)
    page._ui_font_keys = [""]
    page._ui_font_combo.addItem(_("跟随系统默认"))
    installed_fonts = list_installed_ui_font_families()
    preferred_fonts = []
    for family in (
        effective_ui_font_family(get_ui_font_family()),
        "Segoe UI",
        "Microsoft YaHei",
        "PingFang SC",
        "Noto Sans CJK SC",
    ):
        if family and family in installed_fonts and family not in preferred_fonts:
            preferred_fonts.append(family)
    for family in preferred_fonts + [name for name in installed_fonts if name not in preferred_fonts]:
        page._ui_font_keys.append(family)
        page._ui_font_combo.addItem(family)
    current_font = get_ui_font_family()
    current_index = page._ui_font_keys.index(current_font) if current_font in page._ui_font_keys else 0
    page._ui_font_combo.setCurrentIndex(current_index)
    page._ui_font_combo.currentIndexChanged.connect(page._on_ui_font_changed)
    page._attach_setting_card_control(font_card, page._ui_font_combo)
    appearance_group.addSettingCard(font_card)

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
    page._ai_test_progress = IndeterminateProgressRing(test_ai_btn)
    page._ai_test_progress.setFixedSize(20, 20)
    page._ai_test_progress.hide()
    page._ai_refresh_models_btn = PushButton("探测模型")
    page._ai_refresh_models_btn.clicked.connect(page._refresh_available_models)
    ai_btn_row.addWidget(save_ai_btn)
    ai_btn_row.addWidget(test_ai_btn)
    ai_btn_row.addWidget(page._ai_test_progress)
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

    page._ai_tools_summary_label = BodyLabel("内置 0 · Prompt 0", page._ai_tools_card)
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
    new_prompt_btn.clicked.connect(page._open_ai_tool_dialog)
    refresh_ai_tools_btn = PushButton("刷新", page._ai_tools_card)
    refresh_ai_tools_btn.clicked.connect(page._refresh_ai_tools_panel)
    ai_tools_btn_row.addWidget(new_prompt_btn)
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
