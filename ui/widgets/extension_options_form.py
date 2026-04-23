from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QIntValidator
from PySide6.QtWidgets import QAbstractItemView, QFileDialog, QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ColorPickerButton,
    ComboBox,
    DoubleSpinBox,
    FlowLayout,
    LineEdit,
    ListWidget,
    MessageBoxBase,
    PushButton,
    Slider,
    SmoothScrollArea,
    SpinBox,
    SubtitleLabel,
    ToolTipPosition,
)

from core.extension_api import normalize_extension_lines_config
from ui.theme import (
    WORKBENCH_BUTTON_HEIGHT,
    WORKBENCH_INLINE_LABEL_WIDTH,
    apply_button_metrics,
    install_fluent_tooltip,
    make_hint_label,
    make_inline_label,
    placeholder_color,
    secondary_color,
)
from ui.widgets.focus_commit import install_click_away_focus_commit


def _looks_like_color(value: str) -> bool:
    text = str(value or "").strip()
    if not text.startswith("#"):
        return False
    if len(text) not in {4, 7, 9}:
        return False
    try:
        int(text[1:], 16)
    except ValueError:
        return False
    return True


def _normalize_field_type(field: Dict[str, Any]) -> str:
    explicit = str(field.get("field_type") or "string").strip().lower()
    if explicit in {"bool", "boolean", "checkbox"}:
        return "boolean"
    if explicit in {"int", "integer", "spinbox"}:
        return "integer"
    if explicit in {"float", "double", "number"}:
        return "number"
    if explicit in {"choice", "select", "selective", "enum", "combobox"} or field.get("choices"):
        return "selective"
    if explicit in {"colour", "color", "colourpicker", "colorpicker"}:
        return "color"
    if explicit in {"slider", "range", "limited"}:
        return "limited"
    if explicit in {"image", "file", "path", "figure"}:
        return "figure"
    if explicit == "lines":
        return "lines"
    if explicit == "string" and "color" in str(field.get("key") or "").casefold():
        return "color"
    return "string"


def _copy_field(field: Dict[str, Any]) -> Dict[str, Any]:
    copied = copy.deepcopy(dict(field or {}))
    copied["field_type"] = _normalize_field_type(copied)
    return copied


def _infer_field_from_option(key: str, value: Any) -> Optional[Dict[str, Any]]:
    if key == "lines" and isinstance(value, dict):
        return {
            "key": key,
            "label": "输入曲线",
            "description": "扩展输入曲线协议。",
            "field_type": "lines",
            "default": normalize_extension_lines_config(value, preserve_legacy_all=True),
        }
    if isinstance(value, bool):
        field_type = "boolean"
    elif isinstance(value, int) and not isinstance(value, bool):
        field_type = "integer"
    elif isinstance(value, float):
        field_type = "number"
    elif isinstance(value, str):
        field_type = "color" if _looks_like_color(value) and "color" in key.casefold() else "string"
    else:
        return None
    return {
        "key": key,
        "label": key,
        "description": "",
        "field_type": field_type,
        "default": copy.deepcopy(value),
    }


def _field_label(field: Dict[str, Any]) -> str:
    key = str(field.get("key") or "").strip()
    return str(field.get("label") or key or "参数")


def _serialize_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


@dataclass
class _FieldBinding:
    key: str
    field: Dict[str, Any]
    getter: Callable[[], Any]
    setter: Callable[[Any], None]
    refresh: Optional[Callable[[], None]] = None


class _AdaptiveFieldRow(QWidget):
    def __init__(
        self,
        label_text: str,
        *,
        min_control_width: int,
        include_label: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("adaptiveFieldRow")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._min_control_width = max(0, int(min_control_width))
        self._label = None
        self._wrapped = False

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(4)

        if include_label:
            self._label = BodyLabel(f"{label_text}:", self)
            self._label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        self._control_host = QWidget(self)
        self._control_host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._control_layout = QHBoxLayout(self._control_host)
        self._control_layout.setContentsMargins(0, 0, 0, 0)
        self._control_layout.setSpacing(8)

        self._relayout(force=True)

    def control_layout(self) -> QHBoxLayout:
        return self._control_layout

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _required_inline_width(self) -> int:
        margins = self._grid.contentsMargins()
        label_width = self._label.sizeHint().width() if self._label is not None else 0
        spacing = self._grid.horizontalSpacing() if self._label is not None else 0
        return margins.left() + margins.right() + label_width + spacing + self._min_control_width

    def _relayout(self, *, force: bool = False) -> None:
        if self._label is None:
            self._wrapped = False
            self.setProperty("wrapped", False)
            self._grid.addWidget(self._control_host, 0, 0)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 0)
            return

        available_width = max(self.width(), self.minimumWidth())
        wrapped = available_width > 0 and available_width < self._required_inline_width()
        if not force and wrapped == self._wrapped:
            return
        self._wrapped = wrapped
        self.setProperty("wrapped", wrapped)
        self._label.setWordWrap(wrapped)
        if wrapped:
            self._grid.addWidget(self._label, 0, 0)
            self._grid.addWidget(self._control_host, 1, 0)
            self._grid.setColumnStretch(0, 1)
            self._grid.setColumnStretch(1, 0)
            return
        self._grid.addWidget(self._label, 0, 0)
        self._grid.addWidget(self._control_host, 0, 1)
        self._grid.setColumnStretch(0, 0)
        self._grid.setColumnStretch(1, 1)


class _LineSelectionDialog(MessageBoxBase):
    def __init__(
        self,
        title: str,
        candidates: List[str],
        *,
        selected_indices: List[int],
        number: int,
        parent=None,
    ):
        super().__init__(parent)
        self._candidates = list(candidates)
        self._number = int(number)
        self._title_label = SubtitleLabel(title, self.widget)
        self.viewLayout.addWidget(self._title_label)

        allow_select_all = self._number == -1 and bool(self._candidates)
        hint = "从已选择列表中勾选要传给扩展的曲线。"
        if allow_select_all:
            hint += " 可使用“全选”。"
        elif self._number > 1:
            hint += f" 需要恰好选择 {self._number} 条。"
        hint_label = BodyLabel(hint, self.widget)
        hint_label.setWordWrap(True)
        self.viewLayout.addWidget(hint_label)

        if allow_select_all:
            btn_row = QHBoxLayout()
            self._select_all_btn = PushButton("全选", self.widget)
            self._clear_btn = PushButton("清空", self.widget)
            apply_button_metrics(self._select_all_btn, self._clear_btn, min_width=0, height=WORKBENCH_BUTTON_HEIGHT)
            self._select_all_btn.clicked.connect(self._select_all)
            self._clear_btn.clicked.connect(self._clear)
            btn_row.addWidget(self._select_all_btn)
            btn_row.addWidget(self._clear_btn)
            btn_row.addStretch(1)
            self.viewLayout.addLayout(btn_row)

        self._list = ListWidget(self.widget)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for index, label in enumerate(self._candidates, start=1):
            self._list.addItem(f"{index}. {label}")
        self.viewLayout.addWidget(self._list)
        self.widget.setMinimumWidth(420)
        self.widget.setMinimumHeight(360)

        selected_set = {int(item) for item in selected_indices if int(item) > 0}
        self._select_rows([row - 1 for row in sorted(selected_set) if row > 0])

    def _select_all(self) -> None:
        self._select_rows(list(range(self._list.count())))

    def _select_rows(self, rows: List[int]) -> None:
        selection_model = self._list.selectionModel()
        if selection_model is None:
            return
        valid_rows = {row for row in rows if 0 <= row < self._list.count()}
        selection_model.clearSelection()
        if not valid_rows:
            selection_model.clearCurrentIndex()
            for row in range(self._list.count()):
                item = self._list.item(row)
                if item is not None:
                    item.setSelected(False)
            self._list.setFocus(Qt.FocusReason.OtherFocusReason)
            self._list.viewport().update()
            self._list.viewport().repaint()
            return
        selection = QItemSelection()
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item is not None:
                item.setSelected(row in valid_rows)
        for row in sorted(valid_rows):
            index = self._list.model().index(row, 0)
            selection.select(index, index)
        selection_model.select(
            selection,
            QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows,
        )
        current_index = self._list.model().index(min(valid_rows), 0)
        selection_model.setCurrentIndex(current_index, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._list.setFocus(Qt.FocusReason.OtherFocusReason)
        self._list.viewport().update()
        self._list.viewport().repaint()

    def _clear(self) -> None:
        self._select_rows([])

    def value(self) -> List[int]:
        result: List[int] = []
        for item in self._list.selectedItems():
            row = self._list.row(item)
            result.append(row + 1)
        return sorted(result)

    @classmethod
    def get_indices(
        cls,
        parent,
        title: str,
        candidates: List[str],
        *,
        selected_indices: List[int],
        number: int,
    ) -> tuple[List[int], bool]:
        dialog = cls(title, candidates, selected_indices=selected_indices, number=number, parent=parent)
        accepted = bool(dialog.exec())
        return dialog.value(), accepted


class ExtensionOptionsForm(QWidget):
    optionsChanged = Signal(dict)
    optionsCommitted = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._schema_fields: List[Dict[str, Any]] = []
        self._bindings: Dict[str, _FieldBinding] = {}
        self._extra_options: Dict[str, Any] = {}
        self._explicit_option_keys: set[str] = set()
        self._line_candidates: List[str] = []
        self._invalid_text: Optional[str] = None
        self._invalid_error: Optional[str] = None
        self._updating = False
        self._show_field_descriptions = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll_area = SmoothScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("background: transparent; border: none;")
        root.addWidget(self._scroll_area, 1)

        self._content = QWidget(self._scroll_area)
        self._flow = FlowLayout(self._content, needAni=False, isTight=False)
        self._flow.setContentsMargins(0, 0, 0, 0)
        self._flow.setHorizontalSpacing(8)
        self._flow.setVerticalSpacing(6)
        self._scroll_area.setWidget(self._content)

        self._click_away_focus_commit = install_click_away_focus_commit(self)

    def clear(self) -> None:
        self._schema_fields = []
        self._bindings.clear()
        self._extra_options = {}
        self._explicit_option_keys.clear()
        self._invalid_text = None
        self._invalid_error = None
        while self._flow.count():
            item = self._flow.takeAt(0)
            if isinstance(item, QWidget):
                widget = item
            else:
                widget = item.widget() if hasattr(item, "widget") else None
            if widget is not None:
                widget.deleteLater()

    def set_show_field_descriptions(self, visible: bool) -> None:
        self._show_field_descriptions = bool(visible)

    def set_line_candidates(self, candidates: List[str]) -> None:
        self._line_candidates = list(candidates or [])
        for binding in self._bindings.values():
            if binding.field.get("field_type") == "lines" and binding.refresh is not None:
                binding.refresh()

    def set_fields(self, fields: List[Dict[str, Any]], options: Optional[Dict[str, Any]] = None) -> None:
        merged_fields = [_copy_field(field) for field in fields or []]
        known_keys = {str(field.get("key") or "").strip() for field in merged_fields}
        option_dict = dict(options or {})
        for key, value in option_dict.items():
            if key in known_keys:
                continue
            inferred = _infer_field_from_option(str(key), value)
            if inferred is not None:
                merged_fields.append(_copy_field(inferred))
        self.clear()
        self._schema_fields = merged_fields
        for field in merged_fields:
            key = str(field.get("key") or "").strip()
            if not key:
                continue
            binding = self._create_binding(field)
            if binding is not None:
                self._bindings[key] = binding
        self.set_options(option_dict)

    def set_options(self, options: Optional[Dict[str, Any]]) -> None:
        option_dict = dict(options or {})
        self._updating = True
        try:
            self._invalid_text = None
            self._invalid_error = None
            self._explicit_option_keys = set(option_dict)
            self._extra_options = {
                key: copy.deepcopy(value)
                for key, value in option_dict.items()
                if key not in self._bindings
            }
            for key, binding in self._bindings.items():
                if key in option_dict:
                    binding.setter(copy.deepcopy(option_dict[key]))
                    continue
                binding.setter(copy.deepcopy(binding.field.get("default")))
        finally:
            self._updating = False

    def current_options(self) -> Dict[str, Any]:
        if self._invalid_text is not None:
            raise ValueError(f"扩展配置不是合法 JSON: {self._invalid_error or 'unknown error'}")
        values = copy.deepcopy(self._extra_options)
        for key, binding in self._bindings.items():
            value = binding.getter()
            if binding.field.get("field_type") == "lines":
                normalized = normalize_extension_lines_config(value, preserve_legacy_all=True)
                if key not in self._explicit_option_keys and normalized == {"number": 0, "lines_list": ""}:
                    continue
                if key not in self._explicit_option_keys and normalized.get("number", 0) == 1 and not normalized.get("lines_list"):
                    continue
                values[key] = normalized
                continue
            if key not in self._explicit_option_keys and value in (None, "") and binding.field.get("default") in (None, ""):
                continue
            values[key] = value
        return values

    def toPlainText(self) -> str:
        if self._invalid_text is not None:
            return self._invalid_text
        return _serialize_json(self.current_options())

    def setPlainText(self, text: str) -> None:
        clean_text = str(text or "").strip() or "{}"
        try:
            data = json.loads(clean_text)
        except Exception as exc:
            self._invalid_text = clean_text
            self._invalid_error = str(exc)
            return
        if not isinstance(data, dict):
            self._invalid_text = clean_text
            self._invalid_error = "扩展配置必须是 JSON 对象"
            return
        self.set_options(data)

    def _emit_change(self, *, committed: bool) -> None:
        if self._updating:
            return
        try:
            options = self.current_options()
        except ValueError:
            return
        self.optionsChanged.emit(copy.deepcopy(options))
        if committed:
            self.optionsCommitted.emit(copy.deepcopy(options))

    def _create_binding(self, field: Dict[str, Any]) -> Optional[_FieldBinding]:
        field_type = field.get("field_type") or "string"
        key = str(field.get("key") or "").strip()
        if not key:
            return None
        if field_type == "boolean":
            return self._create_boolean_binding(field)
        if field_type == "selective":
            return self._create_selective_binding(field)
        if field_type == "integer":
            return self._create_integer_binding(field)
        if field_type == "number":
            return self._create_number_binding(field)
        if field_type == "color":
            return self._create_color_binding(field)
        if field_type == "limited":
            return self._create_limited_binding(field)
        if field_type == "figure":
            return self._create_figure_binding(field)
        if field_type == "lines":
            return self._create_lines_binding(field)
        return self._create_string_binding(field)

    def _make_field_card(
        self,
        field: Dict[str, Any],
        *,
        min_width: int = 220,
        min_control_width: int = 140,
        include_label: bool = True,
    ) -> tuple[QWidget, QVBoxLayout, QHBoxLayout]:
        container = QWidget(self._content)
        container.setMinimumWidth(min_width)
        container.setMaximumWidth(16777215)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        adaptive_row = _AdaptiveFieldRow(
            _field_label(field),
            min_control_width=min_control_width,
            include_label=include_label,
            parent=container,
        )
        adaptive_row.setMinimumWidth(min_width)
        adaptive_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        adaptive_row._relayout(force=True)
        layout.addWidget(adaptive_row)
        description = str(field.get("description") or "").strip()
        if description and self._show_field_descriptions:
            hint = make_hint_label(description, container)
            hint.setStyleSheet(f"color: {secondary_color()}; font-size: 11px;")
            layout.addWidget(hint)
        self._flow.addWidget(container)
        return container, layout, adaptive_row.control_layout()

    @staticmethod
    def _set_expanding_control(widget: QWidget, min_width: int) -> None:
        widget.setMinimumWidth(max(0, int(min_width)))
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def _create_string_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=152, min_control_width=75)
        edit = LineEdit(container)
        edit.setClearButtonEnabled(True)
        self._set_expanding_control(edit, 75)
        placeholder = str(field.get("placeholder") or "").strip()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        field_row.addWidget(edit, 1)
        edit.editingFinished.connect(lambda: self._emit_change(committed=True))
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=lambda: edit.text(),
            setter=lambda value: edit.setText("" if value is None else str(value)),
        )

    def _create_boolean_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, layout, field_row = self._make_field_card(field, min_width=180, min_control_width=120, include_label=False)
        checkbox = CheckBox(_field_label(field), container)
        field_row.addWidget(checkbox, 1)
        description = str(field.get("description") or "").strip()
        if description and self._show_field_descriptions:
            hint = make_hint_label(description, container)
            hint.setStyleSheet(f"color: {secondary_color()}; font-size: 11px;")
            layout.addWidget(hint)
        checkbox.stateChanged.connect(lambda _state: self._emit_change(committed=True))
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=lambda: bool(checkbox.isChecked()),
            setter=lambda value: checkbox.setChecked(bool(value)),
        )

    def _create_selective_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=152, min_control_width=75)
        combo = ComboBox(container)
        self._set_expanding_control(combo, 75)
        raw_choices = list(field.get("choices") or [])
        display_choices = [str(choice) for choice in raw_choices]
        for choice in display_choices:
            combo.addItem(choice)
        field_row.addWidget(combo, 1)
        combo.currentIndexChanged.connect(lambda _idx: self._emit_change(committed=True))

        def _get() -> Any:
            index = combo.currentIndex()
            if 0 <= index < len(raw_choices):
                return copy.deepcopy(raw_choices[index])
            return combo.currentText().strip()

        def _set(value: Any) -> None:
            marker = str(value)
            index = next((idx for idx, choice in enumerate(raw_choices) if str(choice) == marker), -1)
            if index >= 0:
                combo.setCurrentIndex(index)
                return
            if display_choices:
                combo.setCurrentIndex(0)

        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=_get,
            setter=_set,
        )

    def _create_integer_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=144, min_control_width=60)
        edit = LineEdit(container)
        edit.setClearButtonEnabled(True)
        self._set_expanding_control(edit, 60)
        placeholder = str(field.get("placeholder") or "").strip()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        min_value = int(field.get("min_value", -999999999) or -999999999)
        max_value = int(field.get("max_value", 999999999) or 999999999)
        edit.setValidator(QIntValidator(min_value, max_value, edit))
        field_row.addWidget(edit, 1)
        edit.editingFinished.connect(lambda: self._emit_change(committed=True))

        def _get() -> Any:
            text = edit.text().strip()
            if not text:
                return None
            try:
                return int(text)
            except ValueError:
                default = field.get("default")
                return None if default in (None, "") else int(default)

        def _set(value: Any) -> None:
            edit.setText("" if value in (None, "") else str(int(value)))

        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=_get,
            setter=_set,
        )

    def _create_number_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=144, min_control_width=60)
        edit = LineEdit(container)
        edit.setClearButtonEnabled(True)
        self._set_expanding_control(edit, 60)
        placeholder = str(field.get("placeholder") or "").strip()
        if placeholder:
            edit.setPlaceholderText(placeholder)
        min_value = float(field.get("min_value", -999999999.0) or -999999999.0)
        max_value = float(field.get("max_value", 999999999.0) or 999999999.0)
        validator = QDoubleValidator(min_value, max_value, 12, edit)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        edit.setValidator(validator)
        field_row.addWidget(edit, 1)
        edit.editingFinished.connect(lambda: self._emit_change(committed=True))

        def _get() -> Any:
            text = edit.text().strip()
            if not text:
                return None
            try:
                return float(text)
            except ValueError:
                default = field.get("default")
                return None if default in (None, "") else float(default)

        def _set(value: Any) -> None:
            if value in (None, ""):
                edit.clear()
                return
            numeric = float(value)
            text = f"{numeric:.12f}".rstrip("0").rstrip(".")
            edit.setText(text or "0")

        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=_get,
            setter=_set,
        )

    def _create_color_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=144, min_control_width=60)
        button = ColorPickerButton(QColor("#0078D4"), "", container, enableAlpha=False)
        button.setFixedHeight(WORKBENCH_BUTTON_HEIGHT + 2)
        self._set_expanding_control(button, 60)
        field_row.addWidget(button, 1)
        button.colorChanged.connect(lambda _color: self._emit_change(committed=True))

        def _set(value: Any) -> None:
            text = str(value or "#0078D4")
            button.setColor(QColor(text))
            button.setToolTip(text)
            install_fluent_tooltip(button, delay=300, position=ToolTipPosition.BOTTOM)

        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=lambda: button.color.name(QColor.NameFormat.HexArgb if button.color.alpha() < 255 else QColor.NameFormat.HexRgb),
            setter=_set,
        )

    def _create_limited_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=196, min_control_width=90)
        slider = Slider(Qt.Orientation.Horizontal, container)
        self._set_expanding_control(slider, 90)
        value_label = CaptionLabel("", container)
        value_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        field_row.addWidget(slider, 1)
        field_row.addWidget(value_label)

        min_value = float(field.get("min_value", 0.0) or 0.0)
        max_value = float(field.get("max_value", 100.0) or 100.0)
        step = float(field.get("step", 1.0) or 1.0)
        scale = 1 if abs(step - int(step)) < 1e-9 else max(1, int(round(1.0 / step)))
        slider.setRange(int(round(min_value * scale)), int(round(max_value * scale)))
        slider.setSingleStep(max(1, int(round(step * scale))))
        slider.setPageStep(max(1, int(round(step * scale))))

        def _format(raw_value: int) -> str:
            value = raw_value / scale
            if scale == 1:
                return str(int(value))
            text = f"{value:.4f}".rstrip("0").rstrip(".")
            return text or "0"

        def _get() -> Any:
            value = slider.value() / scale
            return int(value) if scale == 1 else value

        def _set(value: Any) -> None:
            numeric = float(value if value is not None else min_value)
            slider.setValue(int(round(numeric * scale)))
            value_label.setText(_format(slider.value()))

        slider.valueChanged.connect(lambda raw_value: value_label.setText(_format(raw_value)))
        slider.valueChanged.connect(lambda _value: self._emit_change(committed=True))
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=_get,
            setter=_set,
        )

    def _create_figure_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, layout, field_row = self._make_field_card(field, min_width=260, min_control_width=160)
        button = PushButton("选择图片", container)
        self._set_expanding_control(button, 160)
        caption = CaptionLabel("未选择文件", container)
        caption.setWordWrap(True)
        caption.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        field_row.addWidget(button, 1)
        layout.addWidget(caption)
        state = {"path": ""}

        def _set(value: Any) -> None:
            state["path"] = "" if value is None else str(value)
            caption.setText(Path(state["path"]).name if state["path"] else "未选择文件")
            caption.setToolTip(state["path"] or "")
            install_fluent_tooltip(caption, delay=300, position=ToolTipPosition.BOTTOM)

        def _choose() -> None:
            current = state["path"]
            path, _selected_filter = QFileDialog.getOpenFileName(
                self.window() if self.window() is not None else self,
                _field_label(field),
                str(Path(current).parent) if current else "",
                "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;全部文件 (*)",
            )
            if not path:
                return
            _set(path)
            self._emit_change(committed=True)

        button.clicked.connect(_choose)
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=lambda: state["path"],
            setter=_set,
        )

    def _create_lines_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        default_lines = normalize_extension_lines_config(field.get("default"), preserve_legacy_all=True)
        state = dict(default_lines)
        number = int(state.get("number", 0) or 0)

        if number in {0, 1}:
            return _FieldBinding(
                key=str(field.get("key")),
                field=field,
                getter=lambda: dict(state),
                setter=lambda value: state.update(normalize_extension_lines_config(value, preserve_legacy_all=True)),
            )

        container, layout, field_row = self._make_field_card(field, min_width=280, min_control_width=160)
        button = PushButton("选择曲线", container)
        self._set_expanding_control(button, 160)
        summary = CaptionLabel("", container)
        summary.setWordWrap(True)
        summary.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        field_row.addWidget(button, 1)
        layout.addWidget(summary)

        def _selected_labels() -> List[str]:
            labels: List[str] = []
            lines_list = state.get("lines_list")
            if not isinstance(lines_list, list):
                return labels
            for index in lines_list:
                offset = int(index) - 1
                if 0 <= offset < len(self._line_candidates):
                    labels.append(self._line_candidates[offset])
            return labels

        def _summary_text() -> str:
            if not self._line_candidates:
                return "当前没有可选曲线"
            labels = _selected_labels()
            if labels:
                return "当前: " + "；".join(labels)
            lines_list = state.get("lines_list")
            if isinstance(lines_list, list) and lines_list:
                return f"当前已选 {len(lines_list)} 条"
            if number == -1:
                return "当前未显式指定，运行时沿用已选择列表"
            return f"当前未显式指定，需要 {number} 条输入曲线"

        def _refresh() -> None:
            button.setEnabled(bool(self._line_candidates))
            if number == -1:
                button.setText("选择曲线")
            else:
                button.setText(f"选择 {number} 条曲线")
            summary.setText(_summary_text())
            summary.setToolTip("；".join(_selected_labels()) or summary.text())
            install_fluent_tooltip(summary, delay=300, position=ToolTipPosition.BOTTOM)

        def _set(value: Any) -> None:
            state.update(normalize_extension_lines_config(value, preserve_legacy_all=True))
            _refresh()

        def _choose() -> None:
            if not self._line_candidates:
                return
            selected = state.get("lines_list")
            if isinstance(selected, list):
                selected_indices = [int(item) for item in selected]
            else:
                selected_indices = []
            result, accepted = _LineSelectionDialog.get_indices(
                self.window() if self.window() is not None else self,
                _field_label(field),
                self._line_candidates,
                selected_indices=selected_indices,
                number=number,
            )
            if not accepted:
                return
            if number > 0 and len(result) != number:
                summary.setText(f"需要选择 {number} 条曲线，当前为 {len(result)} 条")
                return
            state["lines_list"] = result
            _refresh()
            self._emit_change(committed=True)

        button.clicked.connect(_choose)
        _refresh()
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=lambda: dict(state),
            setter=_set,
            refresh=_refresh,
        )