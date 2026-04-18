from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, CardWidget, ComboBox, PlainTextEdit, PrimaryPushButton, PushButton


class ExtensionConfigPanel(QWidget):
    """页面级自定义扩展侧边栏。"""

    apply_requested = Signal(str, dict)

    def __init__(self, title: str = "自定义扩展", action_text: str = "应用扩展", parent=None):
        super().__init__(parent)
        self.setFixedWidth(340)
        self._entries: List[dict] = []
        self._saved_options: Dict[str, Dict[str, Any]] = {}
        self._action_text = action_text
        self._setup_ui(title)

    def _setup_ui(self, title: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._title_label = BodyLabel(title, card)
        self._title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self._title_label)

        self._page_label = BodyLabel("当前页面: 未设置", card)
        self._page_label.setWordWrap(True)
        layout.addWidget(self._page_label)

        self._target_label = BodyLabel("当前目标: 未设置", card)
        self._target_label.setWordWrap(True)
        layout.addWidget(self._target_label)

        selector_row = QHBoxLayout()
        self._selector = ComboBox(card)
        self._selector.currentIndexChanged.connect(self._on_selection_changed)
        selector_row.addWidget(self._selector, 1)
        self._reset_btn = PushButton("重置配置", card)
        self._reset_btn.clicked.connect(self._reset_current)
        selector_row.addWidget(self._reset_btn)
        layout.addLayout(selector_row)

        desc_title = BodyLabel("说明", card)
        desc_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(desc_title)

        self._description_label = BodyLabel("暂无已注册扩展", card)
        self._description_label.setWordWrap(True)
        layout.addWidget(self._description_label)

        self._usage_hint_label = CaptionLabel("配置 JSON 会在应用时作为 params/options 传给扩展处理函数。", card)
        self._usage_hint_label.setWordWrap(True)
        layout.addWidget(self._usage_hint_label)

        config_title = BodyLabel("扩展配置 JSON", card)
        config_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(config_title)

        self._config_help_label = CaptionLabel("保持 {} 可使用默认配置。", card)
        self._config_help_label.setWordWrap(True)
        layout.addWidget(self._config_help_label)

        self._editor = PlainTextEdit(card)
        self._editor.setPlaceholderText('{\n  "option": "value"\n}')
        self._editor.setFixedHeight(220)
        layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        self._apply_btn = PrimaryPushButton(self._action_text, card)
        self._apply_btn.clicked.connect(self._apply_current)
        btn_row.addWidget(self._apply_btn)
        clear_btn = PushButton("清空配置", card)
        clear_btn.clicked.connect(lambda: self._editor.setPlainText("{}"))
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        root.addWidget(card)
        self._set_empty_state()

    def set_panel_title(self, title: str) -> None:
        self._title_label.setText(title or "自定义扩展")

    def set_action_text(self, text: str) -> None:
        self._action_text = text or "应用扩展"
        self._apply_btn.setText(self._action_text)

    def set_context(self, page_name: str, target_name: str) -> None:
        self._page_label.setText(f"当前页面: {page_name or '未设置'}")
        self._target_label.setText(f"当前目标: {target_name or '未设置'}")

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
            lines = ["字段说明:"]
            for field in fields:
                key = field.get("key") or "option"
                label = field.get("label") or key
                field_type = field.get("field_type") or "string"
                required = "必填" if field.get("required") else "可选"
                line = f"- {label} ({key}, {field_type}, {required})"
                choices = field.get("choices") or []
                if choices:
                    line += f"，可选值: {', '.join(str(choice) for choice in choices)}"
                lines.append(line)
                if field.get("description"):
                    lines.append(f"  {field['description']}")
            return "\n".join(lines)

        default_options = dict(entry.get("default_options") or {})
        if default_options:
            lines = ["默认配置字段:"]
            for key, value in default_options.items():
                lines.append(f"- {key}: {json.dumps(value, ensure_ascii=False)}")
            return "\n".join(lines)
        return "此扩展不需要额外配置，保持 {} 即可。"

    def _set_empty_state(self) -> None:
        self._description_label.setText("当前页面还没有已注册的自定义扩展。")
        self._config_help_label.setText("保持 {} 可使用默认配置。")
        self._editor.setPlainText("{}")
        self._editor.setEnabled(False)
        self._apply_btn.setEnabled(False)
        self._reset_btn.setEnabled(False)

    def _on_selection_changed(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._entries):
            self._set_empty_state()
            return
        entry = self._entries[idx]
        type_id = entry.get("type")
        self._description_label.setText(entry.get("description") or "无扩展说明")
        self._config_help_label.setText(self._config_help_text(entry))
        options = self._saved_options.get(type_id, self._default_options_for_type(type_id))
        self._editor.setEnabled(True)
        self._apply_btn.setEnabled(True)
        self._reset_btn.setEnabled(True)
        self._editor.setPlainText(json.dumps(options, ensure_ascii=False, indent=2))

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