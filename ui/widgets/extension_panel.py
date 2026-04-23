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
from core.extension_api import compare_extension_versions, format_extension_load_report, get_extension_load_status, normalize_extension_version
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.widgets.focus_commit import install_click_away_focus_commit
from ui.theme import (
    WORKBENCH_BUTTON_HEIGHT,
    accent_color,
    card_title_style_sheet,
    flat_status_button_style,
    install_fluent_tooltip,
    make_hint_label,
    make_hsep,
    make_section_label,
    notification_parent,
    placeholder_color,
    placeholder_text_style_sheet,
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

    def __init__(self, title: str = "自定义扩展", action_text: str = "应用扩展", parent=None):
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
        self._section_dividers: List[QWidget] = []
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

        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self._title_label = BodyLabel(title, card)
        self._title_label.setStyleSheet(card_title_style_sheet(font_size=17))
        layout.addWidget(self._title_label)

        status_row = QHBoxLayout()
        self._status_summary_btn = PushButton("尚未扫描扩展。", card)
        self._status_summary_btn.setFlat(True)
        self._status_summary_btn.clicked.connect(self._show_status_details)
        status_row.addWidget(self._status_summary_btn, 1)
        self._status_label = make_hint_label("尚未扫描扩展。", card)
        self._status_label.hide()
        self._status_detail_btn = None
        layout.addLayout(status_row)

        layout.addWidget(make_section_label("扩展", card))

        selector_row = QHBoxLayout()
        self._selector = ComboBox(card)
        self._selector.currentIndexChanged.connect(self._on_selection_changed)
        selector_row.addWidget(self._selector, 1)
        self._reload_btn = ToolButton(getattr(FIF, "SYNC", FIF.UPDATE), card)
        self._install_fluent_tip(self._reload_btn, "重载扩展")
        self._set_square_tool_button(self._reload_btn)
        self._reload_btn.clicked.connect(lambda checked=False: self.reload_requested.emit())
        selector_row.addWidget(self._reload_btn)
        layout.addLayout(selector_row)

        self._description_label = CaptionLabel("暂无可用扩展", card)
        self._description_label.setWordWrap(True)
        self._description_label.setStyleSheet(placeholder_text_style_sheet(font_size=12))
        layout.addWidget(self._description_label)

        self._add_section_divider(layout, card)
        layout.addWidget(make_section_label("配置", card))
        config_row = QHBoxLayout()
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
        layout.addLayout(config_row)

        self._add_section_divider(layout, card)
        layout.addWidget(make_section_label("参数", card))

        self._usage_hint_label = CaptionLabel("参数会按 JSON 传入扩展。", card)
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
        layout.addWidget(self._config_help_area)

        self._editor = PlainTextEdit(card)
        self._editor.setPlaceholderText('{\n  "option": "value"\n}')
        self._editor.setMinimumHeight(240)
        layout.addWidget(self._editor, 1)

        self._add_section_divider(layout, card)
        btn_row = QHBoxLayout()
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
        layout.addLayout(btn_row)

        root.addWidget(card, 1)
        self._set_empty_state()

    def set_status_context(self, category: Optional[str], title: Optional[str] = None) -> None:
        self._status_category = category.strip().lower() if category else None
        self._config_category = self._status_category
        if title:
            self._status_title = title
        self._refresh_status_summary()

    def set_panel_title(self, title: str) -> None:
        self._title_label.setText(title or "自定义扩展")

    def set_action_text(self, text: str) -> None:
        self._action_text = text or "应用扩展"
        self._apply_btn.setText(self._action_text)

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
        self._editor.setPlainText(json.dumps(dict(config_item.options or {}), ensure_ascii=False, indent=2))
        self._warn_if_outdated_config_version(self._entry_for_type(target_type), config_item)
        return True

    def current_options(self) -> Dict[str, Any]:
        text = self._editor.toPlainText().strip() or "{}"
        try:
            data = json.loads(text)
        except Exception as exc:
            raise ValueError(f"扩展配置不是合法 JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("扩展配置必须是 JSON 对象")
        return data

    def _entry_for_type(self, type_id: Optional[str]) -> Optional[dict]:
        if not type_id:
            return None
        return next((entry for entry in self._entries if entry.get("type") == type_id), None)

    def _default_options_for_type(self, type_id: Optional[str]) -> Dict[str, Any]:
        entry = self._entry_for_type(type_id)
        if entry is None:
            return {}
        return dict(entry.get("default_options") or {})

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
            type_id = str(entry.get("type") or "").strip()
            if not type_id:
                continue
            global_assets.ensure_extension_default_config(
                self._config_category,
                type_id,
                str(entry.get("name") or type_id),
                dict(entry.get("default_options") or {}),
                extension_version=self._entry_version(entry),
            )

    def _refresh_config_selector(self, type_id: Optional[str]) -> None:
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
        fields = list(entry.get("config_fields") or [])
        if fields:
            lines = ["字段："]
            for field in fields:
                key = field.get("key") or "option"
                field_type = field.get("field_type") or "string"
                required = "必选" if field.get("required") else "可选"
                parts = [f"{key}: {field_type}", required]
                description = str(field.get("description") or "").strip()
                if description:
                    parts.append(description)
                choices = field.get("choices") or []
                if choices:
                    parts.append(f"可选值: {', '.join(str(choice) for choice in choices)}")
                lines.append(f"- {'; '.join(parts)}")
            return "\n".join(lines)

        default_options = dict(entry.get("default_options") or {})
        if default_options:
            lines = ["默认字段："]
            for key, value in default_options.items():
                lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
            return "\n".join(lines)
        return "无需额外参数，保留 {} 即可。"

    def _set_empty_state(self) -> None:
        self._description_label.setText("当前页没有可用扩展。")
        self._config_help_label.setText("保留 {} 使用默认参数。")
        self._editor.setPlainText("{}")
        self._editor.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._remove_btn.setVisible(False)
        self._remove_btn.setEnabled(False)
        self._reload_btn.setEnabled(True)
        self._config_selector.setEnabled(False)
        self._config_load_btn.setEnabled(False)
        self._config_add_btn.setEnabled(False)
        self._config_overwrite_btn.setEnabled(False)
        self._reset_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
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
            status_text = f"{label} {registered_count} 项可用{source_suffix}，{error_count} 项失败。"
        elif registered_count:
            status_text = f"{label} {registered_count} 项可用{source_suffix}。"
        else:
            status_text = f"{label} 暂无可用项。"
        self._status_label.setText(status_text)
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

    def _on_selection_changed(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._entries):
            self._set_empty_state()
            return
        entry = self._entries[idx]
        type_id = entry.get("type")
        self._description_label.setText((entry.get("description") or "暂无说明").strip())
        self._config_help_label.setText(self._config_help_text(entry))
        self._refresh_config_selector(type_id)
        config_item = self._current_config_item()
        options = self._saved_options.get(type_id, dict(config_item.options) if config_item is not None else self._default_options_for_type(type_id))
        self._editor.setEnabled(True)
        self._apply_btn.setEnabled(True)
        self._reload_btn.setEnabled(True)
        self._config_selector.setEnabled(True)
        self._reset_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self._editor.setPlainText(json.dumps(options, ensure_ascii=False, indent=2))
        self.selection_changed.emit(type_id or "")

    def _reset_current(self) -> None:
        type_id = self.current_type()
        if type_id is None:
            return
        default_config = global_assets.get_extension_default_config(self._config_category or "", type_id)
        if default_config is not None:
            self._selected_config_ids[type_id] = default_config.id
            self._refresh_config_selector(type_id)
            self._editor.setPlainText(json.dumps(dict(default_config.options or {}), ensure_ascii=False, indent=2))
            return
        self._editor.setPlainText(json.dumps(self._default_options_for_type(type_id), ensure_ascii=False, indent=2))

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
        self._editor.setPlainText(json.dumps(dict(config_item.options or {}), ensure_ascii=False, indent=2))
        self._warn_if_outdated_config_version(self._entry_for_type(type_id), config_item)

    def _save_current_as_config(self) -> None:
        type_id = self.current_type()
        entry = self._entry_for_type(type_id)
        if type_id is None or entry is None or not self._config_category:
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
        if type_id is None or config_item is None:
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