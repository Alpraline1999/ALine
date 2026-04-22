from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon as FIF,
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

from core.extension_api import format_extension_load_report, get_extension_load_status
from ui.theme import make_hint_label, make_hsep, make_section_label


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
    dialog_parent = parent.window() if hasattr(parent, "window") and parent is not None else parent
    dialog = _ExtensionLoadReportDialog(title, format_extension_load_report(category), dialog_parent)
    dialog.exec()


class ExtensionConfigPanel(QWidget):
    """页面级自定义扩展侧边栏。"""

    apply_requested = Signal(str, dict)
    reload_requested = Signal()
    remove_requested = Signal(str)
    selection_changed = Signal(str)

    def __init__(self, title: str = "自定义扩展", action_text: str = "应用扩展", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(280)
        self.setMaximumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._entries: List[dict] = []
        self._saved_options: Dict[str, Dict[str, Any]] = {}
        self._action_text = action_text
        self._status_category: Optional[str] = None
        self._status_title = title or "扩展"
        self._section_dividers: List[QWidget] = []
        self._setup_ui(title)

    def _add_section_divider(self, layout: QVBoxLayout, parent: QWidget) -> None:
        divider = make_hsep(parent)
        self._section_dividers.append(divider)
        layout.addWidget(divider)

    @staticmethod
    def _install_fluent_tip(widget: ToolButton, text: str, position=ToolTipPosition.TOP) -> None:
        widget.setToolTip(text)
        widget.installEventFilter(ToolTipFilter(widget, 300, position))

    def _setup_ui(self, title: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self._title_label = BodyLabel(title, card)
        self._title_label.setStyleSheet("font-size: 17px; font-weight: 700;")
        layout.addWidget(self._title_label)

        layout.addWidget(make_section_label("扩展", card))

        selector_row = QHBoxLayout()
        self._selector = ComboBox(card)
        self._selector.currentIndexChanged.connect(self._on_selection_changed)
        selector_row.addWidget(self._selector, 1)
        self._reload_btn = ToolButton(getattr(FIF, "SYNC", FIF.UPDATE), card)
        self._install_fluent_tip(self._reload_btn, "重载扩展")
        self._reload_btn.clicked.connect(lambda checked=False: self.reload_requested.emit())
        selector_row.addWidget(self._reload_btn)
        layout.addLayout(selector_row)

        self._add_section_divider(layout, card)
        layout.addWidget(make_section_label("状态", card))
        status_row = QHBoxLayout()
        self._status_label = make_hint_label("尚未扫描扩展。", card)
        status_row.addWidget(self._status_label, 1)
        self._status_detail_btn = PushButton("详情", card)
        self._status_detail_btn.clicked.connect(self._show_status_details)
        status_row.addWidget(self._status_detail_btn)
        layout.addLayout(status_row)

        self._add_section_divider(layout, card)
        layout.addWidget(make_section_label("说明", card))

        self._description_label = CaptionLabel("暂无可用扩展", card)
        self._description_label.setWordWrap(True)
        layout.addWidget(self._description_label)

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
        self._reset_btn.clicked.connect(self._reset_current)
        btn_row.addWidget(self._reset_btn)
        self._clear_btn = ToolButton(FIF.DELETE, card)
        self._install_fluent_tip(self._clear_btn, "清空配置")
        self._clear_btn.clicked.connect(lambda: self._editor.setPlainText("{}"))
        btn_row.addWidget(self._clear_btn)
        layout.addLayout(btn_row)

        root.addWidget(card, 1)
        self._set_empty_state()

    def set_status_context(self, category: Optional[str], title: Optional[str] = None) -> None:
        self._status_category = category.strip().lower() if category else None
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
            self._status_label.setText(f"{label} {registered_count} 项可用{source_suffix}，{error_count} 项失败。")
        elif registered_count:
            self._status_label.setText(f"{label} {registered_count} 项可用{source_suffix}。")
        else:
            self._status_label.setText(f"{label} 暂无可用项。")
        has_details = bool(status["details"].get("loaded") or status["details"].get("errors"))
        self._status_detail_btn.setEnabled(has_details)

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
        options = self._saved_options.get(type_id, self._default_options_for_type(type_id))
        self._editor.setEnabled(True)
        self._apply_btn.setEnabled(True)
        self._reload_btn.setEnabled(True)
        self._reset_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self._editor.setPlainText(json.dumps(options, ensure_ascii=False, indent=2))
        self.selection_changed.emit(type_id or "")

    def _reset_current(self) -> None:
        type_id = self.current_type()
        if type_id is None:
            return
        self._editor.setPlainText(
            json.dumps(self._default_options_for_type(type_id), ensure_ascii=False, indent=2)
        )

    def _apply_current(self) -> None:
        type_id = self.current_type()
        if type_id is None:
            return
        options = self.current_options()
        self._saved_options[type_id] = dict(options)
        self.apply_requested.emit(type_id, options)

    def _remove_current(self) -> None:
        type_id = self.current_type()
        if type_id is None:
            return
        self.remove_requested.emit(type_id)