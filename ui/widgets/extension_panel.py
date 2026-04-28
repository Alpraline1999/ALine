from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    MessageBoxBase,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    SubtitleLabel,
    ToolTipFilter,
    ToolTipPosition,
    ToolButton,
)

from core.global_assets import global_assets
from core.extension_api import (
    compare_extension_versions,
    extension_entry_display_info,
    extension_entry_parameter_help_text,
    format_extension_load_report,
    get_extension_load_status,
    normalize_extension_version,
)
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.widgets.extension_options_form import ExtensionOptionsForm
from ui.widgets.focus_commit import install_click_away_focus_commit
from ui.theme import (
    WORKBENCH_BUTTON_HEIGHT,
    accent_color,
    card_title_style_sheet,
    flat_status_button_style,
    install_fluent_tooltip,
    make_hsep,
    make_section_label,
    notification_parent,
    placeholder_color,
    placeholder_text_style_sheet,
    secondary_text_style_sheet,
    warning_color,
)


class _ExtensionLoadReportDialog(MessageBoxBase):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.viewLayout.addWidget(SubtitleLabel(title, self))
        editor = PlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setMinimumHeight(280)
        editor.setPlainText(content)
        self.viewLayout.addWidget(editor)
        self.yesButton.setText("关闭")
        self.cancelButton.hide()
        self.widget.setMinimumWidth(560)


def show_extension_load_report_dialog(parent, title: str, category: Optional[str] = None) -> None:
    dialog_parent = notification_parent(parent)
    dialog = _ExtensionLoadReportDialog(title, format_extension_load_report(category), dialog_parent)
    dialog.exec()


class ExtensionConfigPanel(QWidget):
    """页面级自定义扩展侧边栏。"""

    apply_requested = Signal(str, dict)
    reload_requested = Signal()
    remove_requested = Signal(str)
    selection_changed = Signal(str)
    configs_changed = Signal()

    def __init__(
        self,
        title: str = "自定义扩展",
        action_text: str = "应用扩展",
        parent=None,
        *,
        mode: str = "full",
        framed: bool = True,
    ):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._entries: List[dict] = []
        self._saved_options: Dict[str, Dict[str, Any]] = {}
        self._config_ids: List[Optional[str]] = []
        self._selected_config_ids: Dict[str, str] = {}
        self._action_text = action_text
        self._status_category: Optional[str] = None
        self._config_category: Optional[str] = None
        self._status_title = title or "扩展"
        self._inline_apply_visible = False
        self._section_dividers: List[QWidget] = []
        self._panel_mode = mode if mode in {"full", "help_only", "compact"} else "full"
        self._framed = bool(framed)
        self._config_entry_visible = False
        self._help_area_expanding_override: Optional[bool] = None
        self._help_area_min_height_override: Optional[int] = None
        self._help_area_max_height_override: Optional[int] = None
        self._setup_ui(title)
        self._click_away_focus_commit = install_click_away_focus_commit(self)

    def _add_section_divider(self, layout: QVBoxLayout, parent: QWidget) -> None:
        divider = make_hsep(parent)
        self._section_dividers.append(divider)
        layout.addWidget(divider)

    @staticmethod
    def _install_fluent_tip(widget: ToolButton, text: str, position=ToolTipPosition.TOP) -> None:
        widget.setToolTip(text)
        install_fluent_tooltip(widget, delay=300, position=position)

    @staticmethod
    def _set_square_tool_button(button: ToolButton) -> None:
        button.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)

    def _notification_parent(self) -> QWidget:
        parent = notification_parent(self)
        return parent if isinstance(parent, QWidget) else self

    def _setup_ui(self, title: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._root_layout = root

        card = CardWidget(self) if self._framed else QWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14) if self._framed else layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._surface = card
        self._surface_layout = layout

        self._title_label = BodyLabel(title, card)
        self._title_label.setStyleSheet(card_title_style_sheet(font_size=17))
        layout.addWidget(self._title_label)

        self._status_row_widget = QWidget(card)
        status_row = QHBoxLayout(self._status_row_widget)
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(6)
        self._status_summary_btn = PushButton("尚未扫描扩展", card)
        self._status_summary_btn.setFlat(True)
        self._status_summary_btn.clicked.connect(self._show_status_details)
        status_row.addWidget(self._status_summary_btn, 1)
        layout.addWidget(self._status_row_widget)

        self._extension_section_label = make_section_label("扩展", card)
        layout.addWidget(self._extension_section_label)

        self._current_entry_label = CaptionLabel("未选择扩展", card)
        self._current_entry_label.setWordWrap(True)
        self._current_entry_label.setStyleSheet(card_title_style_sheet(font_size=14))
        layout.addWidget(self._current_entry_label)

        self._selector_row_widget = QWidget(card)
        selector_row = QHBoxLayout(self._selector_row_widget)
        selector_row.setContentsMargins(0, 0, 0, 0)
        selector_row.setSpacing(6)
        self._selector = ComboBox(card)
        self._selector.currentIndexChanged.connect(self._on_selection_changed)
        selector_row.addWidget(self._selector, 1)
        self._reload_btn = ToolButton(getattr(FIF, "SYNC", FIF.UPDATE), card)
        self._install_fluent_tip(self._reload_btn, "重载扩展")
        self._set_square_tool_button(self._reload_btn)
        self._reload_btn.clicked.connect(lambda checked=False: self.reload_requested.emit())
        selector_row.addWidget(self._reload_btn)
        layout.addWidget(self._selector_row_widget)

        self._description_label = CaptionLabel("暂无可用扩展", card)
        self._description_label.setWordWrap(True)
        self._description_label.setStyleSheet(secondary_text_style_sheet(font_size=12))
        self._description_section_label = make_section_label("扩展说明", card)
        layout.addWidget(self._description_section_label)
        layout.addWidget(self._description_label)

        self._add_section_divider(layout, card)
        self._config_section_label = make_section_label("配置", card)
        layout.addWidget(self._config_section_label)
        self._config_row_widget = QWidget(card)
        config_row = QHBoxLayout(self._config_row_widget)
        config_row.setContentsMargins(0, 0, 0, 0)
        config_row.setSpacing(6)
        self._config_selector = ComboBox(card)
        config_row.addWidget(self._config_selector, 1)
        self._config_load_btn = ToolButton(FIF.FOLDER, card)
        self._install_fluent_tip(self._config_load_btn, "加载当前选中的扩展配置")
        self._set_square_tool_button(self._config_load_btn)
        self._config_load_btn.clicked.connect(self._load_selected_config)
        config_row.addWidget(self._config_load_btn)
        self._config_add_btn = ToolButton(FIF.ADD, card)
        self._install_fluent_tip(self._config_add_btn, "将当前配置另存为全局扩展配置")
        self._set_square_tool_button(self._config_add_btn)
        self._config_add_btn.clicked.connect(self._save_current_as_config)
        config_row.addWidget(self._config_add_btn)
        self._config_overwrite_btn = ToolButton(FIF.SAVE, card)
        self._install_fluent_tip(self._config_overwrite_btn, "覆盖当前选中的自定义扩展配置")
        self._set_square_tool_button(self._config_overwrite_btn)
        self._config_overwrite_btn.clicked.connect(self._overwrite_selected_config)
        config_row.addWidget(self._config_overwrite_btn)
        inline_apply_icon = getattr(FIF, "SEND", getattr(FIF, "PLAY", FIF.SYNC))
        self._inline_apply_btn = ToolButton(inline_apply_icon, card)
        self._install_fluent_tip(self._inline_apply_btn, self._action_text)
        self._set_square_tool_button(self._inline_apply_btn)
        self._inline_apply_btn.clicked.connect(self._apply_current)
        self._inline_apply_btn.hide()
        config_row.addWidget(self._inline_apply_btn)
        layout.addWidget(self._config_row_widget)

        self._config_row_divider = make_hsep(card)
        layout.addWidget(self._config_row_divider)

        self._add_section_divider(layout, card)
        self._parameter_section_label = make_section_label("参数", card)
        layout.addWidget(self._parameter_section_label)

        self._usage_hint_label = CaptionLabel("参数会按扩展字段自动生成控件。", card)
        self._usage_hint_label.setWordWrap(True)
        layout.addWidget(self._usage_hint_label)

        self._config_help_area = SmoothScrollArea(card)
        self._config_help_area.setWidgetResizable(True)
        self._config_help_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._config_help_area.setMinimumHeight(124)
        self._config_help_area.setMaximumHeight(172)
        self._config_help_area.setStyleSheet("background: transparent; border: none;")
        self._config_help_container = QWidget(self._config_help_area)
        help_layout = QVBoxLayout(self._config_help_container)
        help_layout.setContentsMargins(0, 0, 0, 0)
        help_layout.setSpacing(0)
        self._config_help_label = CaptionLabel("保留 {} 使用默认参数。", self._config_help_container)
        self._config_help_label.setWordWrap(True)
        help_layout.addWidget(self._config_help_label)
        help_layout.addStretch()
        self._config_help_area.setWidget(self._config_help_container)
        layout.addWidget(self._config_help_area, 0)

        self._editor = ExtensionOptionsForm(card)
        self._editor.setMinimumHeight(240)
        layout.addWidget(self._editor, 1)

        self._add_section_divider(layout, card)
        self._action_row_widget = QWidget(card)
        btn_row = QHBoxLayout(self._action_row_widget)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)
        self._apply_btn = PrimaryPushButton(self._action_text, card)
        self._apply_btn.clicked.connect(self._apply_current)
        btn_row.addWidget(self._apply_btn)
        self._remove_btn = PushButton("撤销应用", card)
        self._remove_btn.clicked.connect(self._remove_current)
        self._remove_btn.hide()
        btn_row.addWidget(self._remove_btn)
        self._reset_btn = ToolButton(getattr(FIF, "SYNC", FIF.UPDATE), card)
        self._install_fluent_tip(self._reset_btn, "重置配置")
        self._set_square_tool_button(self._reset_btn)
        self._reset_btn.clicked.connect(self._reset_current)
        btn_row.addWidget(self._reset_btn)
        self._clear_btn = ToolButton(getattr(FIF, "COPY", FIF.DOCUMENT), card)
        self._install_fluent_tip(self._clear_btn, "复制配置")
        self._set_square_tool_button(self._clear_btn)
        self._clear_btn.clicked.connect(self._copy_current_config)
        btn_row.addWidget(self._clear_btn)
        layout.addWidget(self._action_row_widget)

        root.addWidget(card)
        self._set_empty_state()
        self._apply_panel_mode()

    def set_panel_mode(self, mode: str) -> None:
        self._panel_mode = mode if mode in {"full", "help_only", "compact"} else "full"
        if hasattr(self, "_title_label"):
            self._apply_panel_mode()

    def set_help_area_layout(
        self,
        *,
        expanding: Optional[bool] = None,
        min_height: Optional[int] = None,
        max_height: Optional[int] = None,
    ) -> None:
        self._help_area_expanding_override = expanding
        self._help_area_min_height_override = min_height
        self._help_area_max_height_override = max_height
        if hasattr(self, "_config_help_area"):
            self._apply_panel_mode()

    def add_bottom_widget(self, widget: QWidget, *, stretch: int = 0) -> None:
        self._surface_layout.addWidget(widget, stretch)

    def _apply_panel_mode(self) -> None:
        is_full = self._panel_mode == "full"
        is_help_only = self._panel_mode == "help_only"
        is_compact = self._panel_mode == "compact"
        help_area_expands = is_help_only if self._help_area_expanding_override is None else bool(self._help_area_expanding_override)
        help_area_min_height = self._help_area_min_height_override if self._help_area_min_height_override is not None else 124
        if self._help_area_max_height_override is not None:
            help_area_max_height = max(self._help_area_max_height_override, help_area_min_height)
        else:
            help_area_max_height = 16777215 if help_area_expands else 172

        self._title_label.setVisible(is_full)
        self._status_row_widget.setVisible(is_full)
        self._extension_section_label.setVisible(is_full or is_help_only)
        self._extension_section_label.setText(self._status_title)
        self._current_entry_label.setVisible(is_help_only)
        self._current_entry_label.setStyleSheet("" if is_help_only else card_title_style_sheet(font_size=14))
        self._selector_row_widget.setVisible(not is_help_only)
        self._description_section_label.setVisible(is_help_only)
        self._description_label.setVisible(is_full or is_help_only)
        self._config_section_label.setVisible(is_full and self._config_entry_visible)
        self._config_row_widget.setVisible((not is_help_only) and (self._config_entry_visible or is_compact))
        self._config_row_divider.setVisible((not is_help_only) and (self._config_entry_visible or is_compact))
        self._parameter_section_label.setVisible(not is_compact or is_help_only)
        self._parameter_section_label.setText("参数说明" if is_help_only else "参数")
        self._usage_hint_label.setVisible(is_full)
        self._config_help_area.setVisible(is_full or is_help_only)
        self._config_help_area.setMinimumHeight(help_area_min_height)
        self._config_help_area.setMaximumHeight(help_area_max_height)
        if help_area_expands:
            self._config_help_area.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        else:
            self._config_help_area.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._editor.setVisible(not is_help_only)
        self._action_row_widget.setVisible(is_full)
        self._surface.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )
        self._root_layout.setAlignment(self._surface, Qt.AlignmentFlag(0))
        self._surface_layout.setStretchFactor(self._config_help_area, 1 if help_area_expands else 0)

        for index, divider in enumerate(self._section_dividers):
            if is_full:
                divider.setVisible(index != 1 or self._config_entry_visible)
            elif is_help_only:
                divider.setVisible(index == 0)
            else:
                divider.setVisible(False)

    @staticmethod
    def _entry_supports_settings(entry: Optional[dict]) -> bool:
        return bool(entry and entry.get("settings"))

    def set_status_context(self, category: Optional[str], title: Optional[str] = None) -> None:
        self._status_category = category.strip().lower() if category else None
        self._config_category = self._status_category
        if title:
            self._status_title = title
        self._refresh_status_summary()

    def set_panel_title(self, title: str) -> None:
        self._status_title = title or "扩展"
        self._title_label.setText(title or "自定义扩展")
        self._apply_panel_mode()

    def set_action_text(self, text: str) -> None:
        self._action_text = text or "应用扩展"
        self._apply_btn.setText(self._action_text)
        self._inline_apply_btn.setToolTip(self._action_text)

    def set_inline_apply_action(self, *, visible: bool, tooltip: Optional[str] = None) -> None:
        self._inline_apply_visible = bool(visible)
        self._inline_apply_btn.setVisible(self._inline_apply_visible)
        self._apply_btn.setVisible(not self._inline_apply_visible)
        self._inline_apply_btn.setEnabled(self._inline_apply_visible and self._editor.isEnabled())
        self._apply_btn.setEnabled((not self._inline_apply_visible) and self._editor.isEnabled())
        self._install_fluent_tip(self._inline_apply_btn, tooltip or self._action_text)

    def set_remove_action(self, *, visible: bool, enabled: Optional[bool] = None, text: Optional[str] = None) -> None:
        self._remove_btn.setVisible(bool(visible))
        if text is not None:
            self._remove_btn.setText(text)
        if enabled is not None:
            self._remove_btn.setEnabled(bool(enabled))

    def set_context(self, page_name: str, target_name: str) -> None:
        del page_name, target_name

    def set_entries(
        self,
        entries: List[dict],
        *,
        saved_options: Optional[Dict[str, Dict[str, Any]]] = None,
        current_type: Optional[str] = None,
    ) -> None:
        self._entries = [dict(item) for item in entries]
        self._saved_options = {key: dict(value) for key, value in (saved_options or {}).items()}
        self._ensure_default_configs()
        self._selector.blockSignals(True)
        self._selector.clear()
        if not self._entries:
            self._selector.addItem("暂无已注册扩展")
            self._selector.blockSignals(False)
            self._set_empty_state()
            return
        for entry in self._entries:
            self._selector.addItem(entry.get("label") or entry.get("name") or entry.get("type", "扩展"))
        target_type = current_type or self._entries[0].get("type")
        target_index = next((index for index, entry in enumerate(self._entries) if entry.get("type") == target_type), 0)
        self._selector.setCurrentIndex(target_index)
        self._selector.blockSignals(False)
        self._on_selection_changed(target_index)
        self._refresh_status_summary()

    def current_type(self) -> Optional[str]:
        if not self._entries:
            return None
        idx = self._selector.currentIndex()
        if idx < 0 or idx >= len(self._entries):
            return None
        return self._entries[idx].get("type")

    def load_config_by_id(self, config_id: str) -> bool:
        config_item = global_assets.get_extension_config(config_id)
        if config_item is None:
            return False
        if self._config_category and str(config_item.category or "").strip().lower() != self._config_category:
            return False
        target_type = str(config_item.extension_type or "").strip()
        if not target_type:
            return False
        target_index = next(
            (index for index, entry in enumerate(self._entries) if str(entry.get("type") or "").strip() == target_type),
            -1,
        )
        if target_index < 0:
            return False
        self._selected_config_ids[target_type] = config_item.id
        if self._selector.currentIndex() != target_index:
            self._selector.setCurrentIndex(target_index)
        else:
            self._on_selection_changed(target_index)
        self._saved_options[target_type] = dict(config_item.options or {})
        self._refresh_config_selector(target_type)
        self._set_editor_options(target_type, dict(config_item.options or {}))
        self._warn_if_outdated_config_version(self._entry_for_type(target_type), config_item)
        return True

    def current_options(self) -> Dict[str, Any]:
        return self._editor.current_options()

    def _entry_for_type(self, type_id: Optional[str]) -> Optional[dict]:
        if not type_id:
            return None
        return next((entry for entry in self._entries if entry.get("type") == type_id), None)

    def _default_options_for_type(self, type_id: Optional[str]) -> Dict[str, Any]:
        entry = self._entry_for_type(type_id)
        if entry is None:
            return {}
        return dict(entry.get("resolved_options") or {})

    def _entry_fields(self, entry: Optional[dict]) -> List[dict]:
        if entry is None:
            return []
        return [
            dict(item)
            for item in (entry.get("normalized_config_fields") or entry.get("config_fields") or [])
            if isinstance(item, dict)
        ]

    def _set_editor_options(self, type_id: Optional[str], options: Dict[str, Any]) -> None:
        entry = self._entry_for_type(type_id)
        fields = self._entry_fields(entry)
        known_keys = {str(field.get("key") or "").strip() for field in fields}
        option_dict = dict(options or {})
        infer_unknown_fields = any(key not in known_keys for key in option_dict)
        self._editor.set_fields(fields, option_dict, infer_unknown_fields=infer_unknown_fields)

    def _entry_version(self, entry: Optional[dict]) -> str:
        if entry is None:
            return normalize_extension_version(None)
        try:
            return normalize_extension_version(str(entry.get("version") or ""))
        except ValueError:
            return normalize_extension_version(None)

    def _warn_if_outdated_config_version(self, entry: Optional[dict], config_item: Optional[Any]) -> None:
        if entry is None or config_item is None:
            return
        current_version = self._entry_version(entry)
        try:
            saved_version = normalize_extension_version(str(getattr(config_item, "extension_version", "") or ""))
        except ValueError:
            saved_version = normalize_extension_version(None)
        if compare_extension_versions(saved_version, current_version) < 0:
            InfoBar.warning(
                "配置版本较旧",
                f'配置 "{config_item.name}" 的版本 {saved_version} 低于当前扩展版本 {current_version}，请检查参数兼容性',
                parent=self._notification_parent(),
                position=InfoBarPosition.TOP,
            )

    def _preset_items_for_type(self, type_id: Optional[str]) -> List[Any]:
        if not self._config_category or not type_id:
            return []
        return sorted(
            global_assets.list_extension_configs(category=self._config_category, extension_type=type_id),
            key=lambda item: (0 if item.is_default else 1, str(item.name or "").casefold(), str(item.name or "")),
        )

    def _ensure_default_configs(self) -> None:
        if not self._config_category:
            return
        for entry in self._entries:
            if not self._entry_supports_settings(entry):
                continue
            type_id = str(entry.get("type") or "").strip()
            if not type_id:
                continue
            global_assets.ensure_extension_default_config(
                self._config_category,
                type_id,
                str(entry.get("name") or type_id),
                dict(entry.get("resolved_options") or {}),
                extension_version=self._entry_version(entry),
            )

    def _refresh_config_selector(self, type_id: Optional[str]) -> None:
        entry = self._entry_for_type(type_id)
        if not self._entry_supports_settings(entry):
            self._config_selector.blockSignals(True)
            self._config_selector.clear()
            self._config_ids = []
            self._config_selector.blockSignals(False)
            self._config_selector.setEnabled(False)
            self._config_load_btn.setEnabled(False)
            self._config_add_btn.setEnabled(False)
            self._config_overwrite_btn.setEnabled(False)
            return
        self._config_selector.blockSignals(True)
        self._config_selector.clear()
        self._config_ids = []
        items = self._preset_items_for_type(type_id)
        if not items:
            self._config_selector.addItem("默认配置")
            self._config_ids.append(None)
            self._config_selector.blockSignals(False)
            self._config_load_btn.setEnabled(False)
            self._config_add_btn.setEnabled(type_id is not None)
            self._config_overwrite_btn.setEnabled(False)
            return
        selected_id = self._selected_config_ids.get(type_id or "")
        selected_index = 0
        for index, item in enumerate(items):
            self._config_selector.addItem(item.name)
            self._config_ids.append(item.id)
            if item.id == selected_id:
                selected_index = index
        self._config_selector.setCurrentIndex(selected_index)
        self._config_selector.blockSignals(False)
        self._config_load_btn.setEnabled(True)
        self._config_add_btn.setEnabled(type_id is not None)
        current_item = items[selected_index] if 0 <= selected_index < len(items) else None
        self._config_overwrite_btn.setEnabled(bool(current_item is not None and not current_item.is_default))

    def _current_config_id(self) -> Optional[str]:
        idx = self._config_selector.currentIndex()
        if idx < 0 or idx >= len(self._config_ids):
            return None
        return self._config_ids[idx]

    def _current_config_item(self) -> Optional[Any]:
        config_id = self._current_config_id()
        if not config_id:
            return None
        return global_assets.get_extension_config(config_id)

    def _config_help_text(self, entry: dict) -> str:
        help_text = extension_entry_parameter_help_text(entry)
        if help_text:
            return help_text
        default_options = dict(entry.get("resolved_options") or {})
        if default_options:
            lines = ["默认字段："]
            for key, value in default_options.items():
                lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
            return "\n".join(lines)
        return "无需额外参数，保留 {} 即可。"

    def _set_empty_state(self) -> None:
        self._config_entry_visible = False
        self._set_entry_summary(None)
        if self._panel_mode == "help_only":
            self._current_entry_label.setText("当前扩展: 未选择扩展")
            self._description_label.setText("在左侧选择扩展后，这里会显示扩展说明。")
        else:
            self._current_entry_label.setText("当前扩展: 当前页没有可用扩展")
            self._description_label.setText("当前页没有可用扩展")
        self._config_help_label.setText("保留 {} 使用默认参数。")
        self._editor.set_fields([], {})
        self._editor.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._inline_apply_btn.setEnabled(False)
        self._remove_btn.setVisible(False)
        self._remove_btn.setEnabled(False)
        self._reload_btn.setEnabled(True)
        self._config_selector.setEnabled(False)
        self._config_load_btn.setEnabled(False)
        self._config_add_btn.setEnabled(False)
        self._config_overwrite_btn.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
        self._apply_panel_mode()
        self._refresh_status_summary()
        self.selection_changed.emit("")

    def _refresh_status_summary(self) -> None:
        status = get_extension_load_status(self._status_category)
        label = status["label"]
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
            status_text = f"{label} {registered_count} 项可用{source_suffix}，{error_count} 项失败"
        elif registered_count:
            status_text = f"{label} {registered_count} 项可用{source_suffix}"
        else:
            status_text = f"{label} 暂无可用项"
        self._status_summary_btn.setText(status_text)
        has_details = bool(status["details"].get("loaded") or status["details"].get("errors"))
        if error_count:
            self._status_summary_btn.setStyleSheet(flat_status_button_style(warning_color()))
        elif registered_count:
            self._status_summary_btn.setStyleSheet(flat_status_button_style(accent_color()))
        else:
            self._status_summary_btn.setStyleSheet(flat_status_button_style(placeholder_color()))
        self._status_summary_btn.setEnabled(has_details)

    def _show_status_details(self) -> None:
        show_extension_load_report_dialog(self, f"{self._status_title}详情", self._status_category)

    def _set_entry_summary(self, entry: Optional[dict]) -> None:
        info = extension_entry_display_info(entry, category_label=self._status_title)
        panel_title = info.get("panel_title") or "未选择扩展"
        self._extension_section_label.setText(info.get("category_label") or self._status_title or "扩展")
        self._current_entry_label.setText(f"当前扩展: {panel_title}")
        self._description_label.setText(
            info.get("description") or ("在左侧选择扩展后，这里会显示扩展说明。" if self._panel_mode == "help_only" else "暂无说明")
        )

    def _on_selection_changed(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._entries):
            self._set_empty_state()
            return
        entry = self._entries[idx]
        type_id = entry.get("type")
        type_key = str(type_id or "")
        self._set_entry_summary(entry)
        self._config_help_label.setText(self._config_help_text(entry))
        self._config_entry_visible = self._entry_supports_settings(entry)
        self._apply_panel_mode()
        self._refresh_config_selector(type_id)
        config_item = self._current_config_item()
        options = self._saved_options.get(type_key, dict(config_item.options) if config_item is not None else self._default_options_for_type(type_id))
        self._editor.setEnabled(True)
        self._apply_btn.setEnabled(not self._inline_apply_visible)
        self._inline_apply_btn.setEnabled(self._inline_apply_visible)
        self._reload_btn.setEnabled(True)
        self._config_selector.setEnabled(self._config_entry_visible)
        self._reset_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self._set_editor_options(type_id, options)
        self.selection_changed.emit(type_id or "")

    def _reset_current(self) -> None:
        type_id = self.current_type()
        if type_id is None:
            return
        default_config = global_assets.get_extension_default_config(self._config_category or "", type_id)
        if default_config is not None:
            self._selected_config_ids[type_id] = default_config.id
            self._refresh_config_selector(type_id)
            self._set_editor_options(type_id, dict(default_config.options or {}))
            return
        self._set_editor_options(type_id, self._default_options_for_type(type_id))

    def _apply_current(self) -> None:
        type_id = self.current_type()
        if type_id is None:
            return
        options = self.current_options()
        self._saved_options[type_id] = dict(options)
        self.apply_requested.emit(type_id, options)

    def _load_selected_config(self) -> None:
        type_id = self.current_type()
        config_item = self._current_config_item()
        if type_id is None or config_item is None:
            return
        self._selected_config_ids[type_id] = config_item.id
        self._saved_options[type_id] = dict(config_item.options or {})
        self._set_editor_options(type_id, dict(config_item.options or {}))
        self._warn_if_outdated_config_version(self._entry_for_type(type_id), config_item)

    def _save_current_as_config(self) -> None:
        type_id = self.current_type()
        entry = self._entry_for_type(type_id)
        if type_id is None or entry is None or not self._config_category or not self._entry_supports_settings(entry):
            return
        try:
            options = self.current_options()
        except ValueError as exc:
            InfoBar.error("保存失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        name, accepted = TextInputDialog.get_text(self.window() if self.window() is not None else self, "新增配置", "配置名称:")
        if not accepted:
            return
        try:
            saved = global_assets.add_extension_config(
                category=self._config_category,
                extension_type=type_id,
                extension_name=str(entry.get("name") or type_id),
                extension_version=self._entry_version(entry),
                name=name,
                options=options,
            )
        except ValueError as exc:
            InfoBar.warning("新增失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        self._selected_config_ids[type_id] = saved.id
        self._refresh_config_selector(type_id)
        self.configs_changed.emit()
        InfoBar.success("已保存", f'配置 "{saved.name}" 已加入全局扩展配置', parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _overwrite_selected_config(self) -> None:
        type_id = self.current_type()
        config_item = self._current_config_item()
        if type_id is None or config_item is None or not self._entry_supports_settings(self._entry_for_type(type_id)):
            return
        if config_item.is_default:
            InfoBar.warning("无法覆盖", "默认配置不可覆盖，请新增一个自定义配置", parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        try:
            options = self.current_options()
        except ValueError as exc:
            InfoBar.error("覆盖失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        global_assets.update_extension_config(
            config_item.id,
            options=options,
            extension_version=self._entry_version(self._entry_for_type(type_id)),
        )
        self._selected_config_ids[type_id] = config_item.id
        self._refresh_config_selector(type_id)
        self.configs_changed.emit()
        InfoBar.success("已覆盖", f'配置 "{config_item.name}" 已更新', parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _copy_current_config(self) -> None:
        QApplication.clipboard().setText(self._editor.toPlainText().strip() or "{}")
        InfoBar.success("已复制", "当前扩展配置已复制到剪贴板", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _remove_current(self) -> None:
        type_id = self.current_type()
        if type_id is None:
            return
        self.remove_requested.emit(type_id)