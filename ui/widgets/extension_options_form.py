from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ColorPickerButton,
    ComboBox,
    DoubleSpinBox,
    FluentIcon as FIF,
    InfoBar,
    InfoBarPosition,
    ListWidget,
    LineEdit,
    MessageBoxBase,
    PushButton,
    Slider,
    SmoothScrollArea,
    SpinBox,
    SubtitleLabel,
    ToolButton,
    ToolTip,
    ToolTipPosition,
)

from core.global_assets import global_assets
from core.extension_settings import get_extension_number_decimals
from core.extension_api import (
    extension_lines_picker_visible,
    extension_lines_support_text,
    normalize_extension_lines_list,
    normalize_extension_lines_number,
)
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.theme import (
    WORKBENCH_BUTTON_HEIGHT,
    WORKBENCH_INLINE_LABEL_WIDTH,
    apply_button_metrics,
    border_color,
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
    if explicit == "shot":
        return "shot"
    if explicit in {"pickcolor", "pick_colour", "pick_color"}:
        return "pickcolor"
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
    if explicit == "line":
        return "line"
    if explicit == "string" and "color" in str(field.get("key") or "").casefold():
        return "color"
    return "string"


def _copy_field(field: Dict[str, Any]) -> Dict[str, Any]:
    copied = copy.deepcopy(dict(field or {}))
    copied["field_type"] = _normalize_field_type(copied)
    return copied


def _infer_field_from_option(key: str, value: Any) -> Optional[Dict[str, Any]]:
    if key == "lines_list":
        return {
            "key": key,
            "label": "lines",
            "description": "扩展输入曲线协议。",
            "field_type": "lines",
            "default": normalize_extension_lines_list(value),
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


def _field_lines_number(field: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    extra = dict(field.get("extra") or {}) if isinstance(field.get("extra"), dict) else {}
    try:
        return normalize_extension_lines_number(extra.get("lines_number"))
    except ValueError:
        return (1, 1)


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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._relayout(force=True)

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


def _build_list_frame(parent: QWidget) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame(parent)
    frame.setObjectName("selectionListFrame")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    frame.setStyleSheet(
        f"QFrame#selectionListFrame {{ border: 1px solid {border_color()}; border-radius: 8px; background: transparent; }}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(4, 4, 4, 4)
    layout.setSpacing(0)
    return frame, layout


class _LineSelectionDialog(MessageBoxBase):
    def __init__(
        self,
        title: str,
        candidates: List[str],
        *,
        selected_indices: List[int],
        lines_number: Tuple[int, int],
        available_label: str = "候选区",
        selected_label: str = "已选中",
        parent=None,
    ):
        super().__init__(parent)
        self._candidates = list(candidates)
        self._lines_number = lines_number
        self._title_label = SubtitleLabel(title, self.widget)
        self.viewLayout.addWidget(self._title_label)

        _lower, upper = self._lines_number

        self._status = CaptionLabel("", self.widget)
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {secondary_color()}; font-size: 11px;")
        self.viewLayout.addWidget(self._status)

        lists_row = QHBoxLayout()
        lists_row.setContentsMargins(0, 0, 0, 0)
        lists_row.setSpacing(8)

        left_column = QVBoxLayout()
        left_column.setContentsMargins(0, 0, 0, 0)
        left_column.setSpacing(6)
        self._available_title_label = BodyLabel(available_label, self.widget)
        left_column.addWidget(self._available_title_label)
        available_frame, available_frame_layout = _build_list_frame(self.widget)
        self._available_list = ListWidget(available_frame)
        self._available_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._available_list.setMinimumHeight(236)
        self._available_list.itemDoubleClicked.connect(lambda _item: self._move_to_selected())
        self._available_list.itemSelectionChanged.connect(self._refresh_button_states)
        available_frame_layout.addWidget(self._available_list, 1)
        left_column.addWidget(available_frame, 1)
        lists_row.addLayout(left_column, 1)

        center_column = QVBoxLayout()
        center_column.setContentsMargins(0, 24, 0, 0)
        center_column.setSpacing(6)
        self._select_all_btn = PushButton("全选", self.widget)
        self._move_right_btn = PushButton("添加 →", self.widget)
        self._move_left_btn = PushButton("← 移除", self.widget)
        self._clear_btn = PushButton("清空", self.widget)
        apply_button_metrics(
            self._select_all_btn,
            self._move_right_btn,
            self._move_left_btn,
            self._clear_btn,
            min_width=0,
            height=WORKBENCH_BUTTON_HEIGHT,
        )
        self._select_all_btn.clicked.connect(self._select_all)
        self._move_right_btn.clicked.connect(self._move_to_selected)
        self._move_left_btn.clicked.connect(self._move_to_available)
        self._clear_btn.clicked.connect(self._clear)
        self._select_all_btn.setVisible(upper == -1 and bool(self._candidates))
        self._clear_btn.setVisible(bool(self._candidates))
        center_column.addStretch(1)
        center_column.addWidget(self._select_all_btn)
        center_column.addWidget(self._move_right_btn)
        center_column.addWidget(self._move_left_btn)
        center_column.addWidget(self._clear_btn)
        center_column.addStretch(1)
        lists_row.addLayout(center_column)

        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(6)
        self._selected_title_label = BodyLabel(selected_label, self.widget)
        right_column.addWidget(self._selected_title_label)
        right_list_row = QHBoxLayout()
        right_list_row.setContentsMargins(0, 0, 0, 0)
        right_list_row.setSpacing(6)
        selected_frame, selected_frame_layout = _build_list_frame(self.widget)
        self._selected_list = ListWidget(selected_frame)
        self._selected_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._selected_list.setMinimumHeight(236)
        self._selected_list.itemDoubleClicked.connect(lambda _item: self._move_to_available())
        self._selected_list.itemSelectionChanged.connect(self._refresh_button_states)
        selected_frame_layout.addWidget(self._selected_list, 1)
        right_list_row.addWidget(selected_frame, 1)
        order_column = QVBoxLayout()
        order_column.setContentsMargins(0, 0, 0, 0)
        order_column.setSpacing(6)
        self._move_up_btn = ToolButton(FIF.UP, self.widget)
        self._move_down_btn = ToolButton(FIF.DOWN, self.widget)
        for button, tooltip in ((self._move_up_btn, "上移"), (self._move_down_btn, "下移")):
            button.setToolTip(tooltip)
            button.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
            install_fluent_tooltip(button, delay=300, position=ToolTipPosition.BOTTOM)
        self._move_up_btn.clicked.connect(self._move_selected_up)
        self._move_down_btn.clicked.connect(self._move_selected_down)
        order_column.addWidget(self._move_up_btn)
        order_column.addWidget(self._move_down_btn)
        order_column.addStretch(1)
        right_list_row.addLayout(order_column)
        right_column.addLayout(right_list_row, 1)
        lists_row.addLayout(right_column, 1)

        self.viewLayout.addLayout(lists_row)
        self.widget.setMinimumWidth(620)
        self.widget.setMinimumHeight(380)
        self.yesButton.setText("确认")
        self.cancelButton.setText("取消")

        self._available_indices = list(range(1, len(self._candidates) + 1))
        self._selected_indices = [
            index for index in normalize_extension_lines_list(selected_indices)
            if 1 <= index <= len(self._candidates)
        ]
        selected_set = set(self._selected_indices)
        self._available_indices = [index for index in self._available_indices if index not in selected_set]
        self._rebuild_lists()
        self._update_status()
        self._refresh_button_states()

    def _label_for_index(self, index: int) -> str:
        return f"{index}. {self._candidates[index - 1]}"

    def _populate_list(self, widget: ListWidget, indices: List[int]) -> None:
        widget.clear()
        for index in indices:
            item_text = self._label_for_index(index)
            widget.addItem(item_text)
            widget.item(widget.count() - 1).setData(Qt.ItemDataRole.UserRole, index)
            widget.item(widget.count() - 1).setToolTip(item_text)

    def _rebuild_lists(self) -> None:
        self._populate_list(self._available_list, self._available_indices)
        self._populate_list(self._selected_list, self._selected_indices)

    @staticmethod
    def _restore_list_selection(widget: ListWidget, selected_values: List[int], current_value: Optional[int]) -> None:
        selected_set = set(selected_values)
        current_item = None
        for row in range(widget.count()):
            item = widget.item(row)
            raw_value = item.data(Qt.ItemDataRole.UserRole)
            try:
                numeric = int(raw_value)
            except (TypeError, ValueError):
                continue
            item.setSelected(numeric in selected_set)
            if current_value is not None and numeric == current_value:
                current_item = item
        if current_item is not None:
            widget.setCurrentItem(current_item)

    @staticmethod
    def _selected_index_values(widget: ListWidget) -> List[int]:
        values: List[int] = []
        for item in widget.selectedItems():
            raw = item.data(Qt.ItemDataRole.UserRole)
            try:
                values.append(int(raw))
            except (TypeError, ValueError):
                continue
        return values

    def _select_all(self) -> None:
        if not self._available_indices:
            return
        self._selected_indices.extend(self._available_indices)
        self._available_indices.clear()
        self._rebuild_lists()
        self._update_status()
        self._refresh_button_states()

    def _clear(self) -> None:
        if not self._selected_indices:
            return
        self._available_indices.extend(self._selected_indices)
        self._available_indices.sort()
        self._selected_indices.clear()
        self._rebuild_lists()
        self._update_status()
        self._refresh_button_states()

    def _move_to_selected(self) -> None:
        chosen = self._selected_index_values(self._available_list)
        if not chosen:
            return
        chosen_set = set(chosen)
        self._selected_indices.extend(index for index in self._available_indices if index in chosen_set)
        self._available_indices = [index for index in self._available_indices if index not in chosen_set]
        self._rebuild_lists()
        self._update_status()
        self._refresh_button_states()

    def _move_to_available(self) -> None:
        chosen = self._selected_index_values(self._selected_list)
        if not chosen:
            return
        chosen_set = set(chosen)
        self._available_indices.extend(index for index in self._selected_indices if index in chosen_set)
        self._available_indices.sort()
        self._selected_indices = [index for index in self._selected_indices if index not in chosen_set]
        self._rebuild_lists()
        self._update_status()
        self._refresh_button_states()

    def _move_selected_up(self) -> None:
        chosen = set(self._selected_index_values(self._selected_list))
        if not chosen:
            return
        current_item = self._selected_list.currentItem()
        current_value = None
        if current_item is not None:
            try:
                current_value = int(current_item.data(Qt.ItemDataRole.UserRole))
            except (TypeError, ValueError):
                current_value = None
        for index in range(1, len(self._selected_indices)):
            if self._selected_indices[index] in chosen and self._selected_indices[index - 1] not in chosen:
                self._selected_indices[index - 1], self._selected_indices[index] = self._selected_indices[index], self._selected_indices[index - 1]
        self._rebuild_lists()
        self._restore_list_selection(self._selected_list, list(chosen), current_value)
        self._refresh_button_states()

    def _move_selected_down(self) -> None:
        chosen = set(self._selected_index_values(self._selected_list))
        if not chosen:
            return
        current_item = self._selected_list.currentItem()
        current_value = None
        if current_item is not None:
            try:
                current_value = int(current_item.data(Qt.ItemDataRole.UserRole))
            except (TypeError, ValueError):
                current_value = None
        for index in range(len(self._selected_indices) - 2, -1, -1):
            if self._selected_indices[index] in chosen and self._selected_indices[index + 1] not in chosen:
                self._selected_indices[index + 1], self._selected_indices[index] = self._selected_indices[index], self._selected_indices[index + 1]
        self._rebuild_lists()
        self._restore_list_selection(self._selected_list, list(chosen), current_value)
        self._refresh_button_states()

    def _refresh_button_states(self) -> None:
        available_selected = bool(self._available_list.selectedItems())
        selected_selected = bool(self._selected_list.selectedItems())
        self._move_right_btn.setEnabled(available_selected)
        self._move_left_btn.setEnabled(selected_selected)
        selected_rows = sorted({self._selected_list.row(item) for item in self._selected_list.selectedItems()})
        self._move_up_btn.setEnabled(bool(selected_rows) and selected_rows[0] > 0)
        self._move_down_btn.setEnabled(bool(selected_rows) and selected_rows[-1] < self._selected_list.count() - 1)

    def _update_status(self) -> None:
        lower, upper = self._lines_number
        count = len(self.value())
        support_text = extension_lines_support_text(self._lines_number)
        if upper == -1:
            detail = f"已选择 {count} 条，支持 {support_text}。"
        elif lower == upper:
            detail = f"已选择 {count}/{upper} 条。"
        else:
            detail = f"已选择 {count} 条，支持 {support_text}。"
        self._status.setText(detail)
        self.yesButton.setEnabled(count >= lower and (upper == -1 or count <= upper))

    def value(self) -> List[int]:
        return list(self._selected_indices)

    @classmethod
    def get_indices(
        cls,
        parent,
        title: str,
        candidates: List[str],
        *,
        selected_indices: List[int],
        lines_number: Tuple[int, int],
        available_label: str = "候选区",
        selected_label: str = "已选中",
    ) -> tuple[List[int], bool]:
        dialog = cls(
            title,
            candidates,
            selected_indices=selected_indices,
            lines_number=lines_number,
            available_label=available_label,
            selected_label=selected_label,
            parent=parent,
        )
        accepted = bool(dialog.exec())
        return dialog.value(), accepted


class _SingleLineSelectionDialog(MessageBoxBase):
    def __init__(
        self,
        title: str,
        candidates: List[str],
        *,
        selected_index: Optional[int],
        parent=None,
    ):
        super().__init__(parent)
        self._candidates = list(candidates or [])
        self._selected_index = None

        self._title_label = SubtitleLabel(title, self.widget)
        self.viewLayout.addWidget(self._title_label)

        self._status = CaptionLabel("", self.widget)
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {secondary_color()}; font-size: 11px;")
        self.viewLayout.addWidget(self._status)

        self._list_title_label = BodyLabel("候选曲线", self.widget)
        self.viewLayout.addWidget(self._list_title_label)

        frame, frame_layout = _build_list_frame(self.widget)
        self._list = ListWidget(frame)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setMinimumHeight(236)
        self._list.itemDoubleClicked.connect(lambda _item: self._accept_selection())
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        frame_layout.addWidget(self._list, 1)
        self.viewLayout.addWidget(frame)

        self.widget.setMinimumWidth(420)
        self.widget.setMinimumHeight(340)
        self.yesButton.setText("确认")
        self.cancelButton.setText("取消")

        self._populate_list()
        self._set_selected_index(selected_index)
        self._update_status()

    def _label_for_index(self, index: int) -> str:
        return f"{index}. {self._candidates[index - 1]}"

    def _populate_list(self) -> None:
        self._list.clear()
        for index, candidate in enumerate(self._candidates, start=1):
            del candidate
            item_text = self._label_for_index(index)
            self._list.addItem(item_text)
            item = self._list.item(self._list.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setToolTip(item_text)

    def _set_selected_index(self, selected_index: Optional[int]) -> None:
        try:
            normalized = int(selected_index) if selected_index not in (None, "") else None
        except (TypeError, ValueError):
            normalized = None
        self._selected_index = normalized if normalized is not None and 1 <= normalized <= len(self._candidates) else None
        current_item = None
        for row in range(self._list.count()):
            item = self._list.item(row)
            is_selected = item.data(Qt.ItemDataRole.UserRole) == self._selected_index
            item.setSelected(is_selected)
            if is_selected:
                current_item = item
        if current_item is not None:
            self._list.setCurrentItem(current_item)

    def _on_selection_changed(self) -> None:
        current = self._list.currentItem()
        if current is None:
            selected_items = self._list.selectedItems()
            current = selected_items[0] if selected_items else None
        if current is None:
            self._selected_index = None
        else:
            try:
                self._selected_index = int(current.data(Qt.ItemDataRole.UserRole))
            except (TypeError, ValueError):
                self._selected_index = None
        self._update_status()

    def _update_status(self) -> None:
        if self._selected_index is None:
            self._status.setText("请选择 1 条曲线作为参数。")
            self.yesButton.setEnabled(False)
            return
        self._status.setText(f"当前已选: {self._label_for_index(self._selected_index)}")
        self.yesButton.setEnabled(True)

    def _accept_selection(self) -> None:
        if self._selected_index is None:
            return
        self.accept()

    def value(self) -> Optional[int]:
        return self._selected_index

    @classmethod
    def get_index(
        cls,
        parent,
        title: str,
        candidates: List[str],
        *,
        selected_index: Optional[int],
    ) -> tuple[Optional[int], bool]:
        dialog = cls(title, candidates, selected_index=selected_index, parent=parent)
        accepted = bool(dialog.exec())
        return dialog.value(), accepted


class ExtensionOptionsForm(QWidget):
    optionsChanged = Signal(dict)
    optionsCommitted = Signal(dict)
    interactiveFieldRequested = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._schema_fields: List[Dict[str, Any]] = []
        self._bindings: Dict[str, _FieldBinding] = {}
        self._extra_options: Dict[str, Any] = {}
        self._explicit_option_keys: set[str] = set()
        self._line_candidates: List[str] = []
        self._settings_category: Optional[str] = None
        self._settings_entry: Optional[Dict[str, Any]] = None
        self._settings_config_ids: List[Optional[str]] = []
        self._selected_settings_config_ids: Dict[str, str] = {}
        self._invalid_text: Optional[str] = None
        self._invalid_error: Optional[str] = None
        self._updating = False
        self._show_field_descriptions = False
        self._retain_unknown_options = False
        self._live_tooltip = None
        self._live_tooltip_owner: Optional[QWidget] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._settings_row = QWidget(self)
        settings_layout = QHBoxLayout(self._settings_row)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(6)
        self._settings_selector = ComboBox(self._settings_row)
        settings_layout.addWidget(self._settings_selector, 1)
        self._settings_load_btn = ToolButton(FIF.FOLDER, self._settings_row)
        self._settings_add_btn = ToolButton(FIF.ADD, self._settings_row)
        self._settings_overwrite_btn = ToolButton(FIF.SAVE, self._settings_row)
        for button, tooltip in (
            (self._settings_load_btn, "加载当前选中的扩展配置"),
            (self._settings_add_btn, "将当前参数另存为扩展配置"),
            (self._settings_overwrite_btn, "覆盖当前选中的扩展配置"),
        ):
            button.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
            button.setToolTip(tooltip)
            install_fluent_tooltip(button, delay=300, position=ToolTipPosition.BOTTOM)
            settings_layout.addWidget(button)
        self._settings_load_btn.clicked.connect(self._load_selected_settings_config)
        self._settings_add_btn.clicked.connect(self._save_current_as_settings_config)
        self._settings_overwrite_btn.clicked.connect(self._overwrite_selected_settings_config)
        self._settings_row.hide()
        root.addWidget(self._settings_row)

        self._scroll_area = SmoothScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("background: transparent; border: none;")
        root.addWidget(self._scroll_area, 1)

        self._content = QWidget(self._scroll_area)
        self._flow = QVBoxLayout(self._content)
        self._flow.setContentsMargins(0, 0, 12, 0)
        self._flow.setSpacing(6)
        self._flow.setAlignment(Qt.AlignmentFlag.AlignTop)
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
            if binding.field.get("field_type") in {"line", "lines"} and binding.refresh is not None:
                binding.refresh()

    def set_settings_context(self, category: Optional[str], entry: Optional[Dict[str, Any]]) -> None:
        self._settings_category = str(category or "").strip().lower() or None
        self._settings_entry = dict(entry) if isinstance(entry, dict) else None
        if not self._settings_category or not isinstance(self._settings_entry, dict) or not self._settings_entry.get("settings"):
            self._settings_row.hide()
            self._settings_selector.clear()
            self._settings_config_ids = []
            return

        type_id = str(self._settings_entry.get("type") or "").strip()
        if not type_id:
            self._settings_row.hide()
            return
        global_assets.ensure_extension_default_config(
            self._settings_category,
            type_id,
            str(self._settings_entry.get("name") or type_id),
            dict(self._settings_entry.get("resolved_options") or {}),
            extension_version=str(self._settings_entry.get("version") or "1.0.0"),
        )
        self._settings_row.show()
        self._refresh_settings_selector()

    def _notification_parent(self) -> QWidget:
        window = self.window()
        return window if isinstance(window, QWidget) else self

    def _settings_type_id(self) -> Optional[str]:
        if not isinstance(self._settings_entry, dict):
            return None
        type_id = str(self._settings_entry.get("type") or "").strip()
        return type_id or None

    def _refresh_settings_selector(self) -> None:
        type_id = self._settings_type_id()
        self._settings_selector.blockSignals(True)
        self._settings_selector.clear()
        self._settings_config_ids = []
        if not self._settings_category or not type_id:
            self._settings_selector.blockSignals(False)
            self._settings_load_btn.setEnabled(False)
            self._settings_add_btn.setEnabled(False)
            self._settings_overwrite_btn.setEnabled(False)
            return

        items = sorted(
            global_assets.list_extension_configs(category=self._settings_category, extension_type=type_id),
            key=lambda item: (0 if item.is_default else 1, str(item.name or "").casefold(), str(item.name or "")),
        )
        if not items:
            self._settings_selector.addItem("默认配置")
            self._settings_config_ids.append(None)
            self._settings_selector.blockSignals(False)
            self._settings_load_btn.setEnabled(False)
            self._settings_add_btn.setEnabled(True)
            self._settings_overwrite_btn.setEnabled(False)
            return

        selected_id = self._selected_settings_config_ids.get(type_id, "")
        selected_index = 0
        for index, item in enumerate(items):
            self._settings_selector.addItem(item.name)
            self._settings_config_ids.append(item.id)
            if item.id == selected_id:
                selected_index = index
        self._settings_selector.setCurrentIndex(selected_index)
        self._settings_selector.blockSignals(False)
        self._settings_load_btn.setEnabled(True)
        self._settings_add_btn.setEnabled(True)
        current_item = items[selected_index] if 0 <= selected_index < len(items) else None
        self._settings_overwrite_btn.setEnabled(bool(current_item is not None and not current_item.is_default))

    def _current_settings_config_id(self) -> Optional[str]:
        idx = self._settings_selector.currentIndex()
        if idx < 0 or idx >= len(self._settings_config_ids):
            return None
        return self._settings_config_ids[idx]

    def _current_settings_config_item(self):
        config_id = self._current_settings_config_id()
        if not config_id:
            return None
        return global_assets.get_extension_config(config_id)

    def _load_selected_settings_config(self) -> None:
        type_id = self._settings_type_id()
        config_item = self._current_settings_config_item()
        if type_id is None or config_item is None:
            return
        self._selected_settings_config_ids[type_id] = config_item.id
        self.set_options(dict(config_item.options or {}))
        self._emit_change(committed=True)

    def _save_current_as_settings_config(self) -> None:
        type_id = self._settings_type_id()
        if type_id is None or not self._settings_category or not isinstance(self._settings_entry, dict):
            return
        try:
            options = self.current_options()
        except ValueError as exc:
            InfoBar.error("保存失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        name, accepted = TextInputDialog.get_text(self._notification_parent(), "新增配置", "配置名称:")
        if not accepted:
            return
        try:
            saved = global_assets.add_extension_config(
                category=self._settings_category,
                extension_type=type_id,
                extension_name=str(self._settings_entry.get("name") or type_id),
                extension_version=str(self._settings_entry.get("version") or "1.0.0"),
                name=name,
                options=options,
            )
        except ValueError as exc:
            InfoBar.warning("新增失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        self._selected_settings_config_ids[type_id] = saved.id
        self._refresh_settings_selector()
        InfoBar.success("已保存", f'配置 "{saved.name}" 已加入全局扩展配置', parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _overwrite_selected_settings_config(self) -> None:
        type_id = self._settings_type_id()
        config_item = self._current_settings_config_item()
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
            extension_version=str(self._settings_entry.get("version") or "1.0.0") if isinstance(self._settings_entry, dict) else "1.0.0",
        )
        self._selected_settings_config_ids[type_id] = config_item.id
        self._refresh_settings_selector()
        InfoBar.success("已覆盖", f'配置 "{config_item.name}" 已更新', parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def set_fields(
        self,
        fields: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
        *,
        infer_unknown_fields: bool = False,
    ) -> None:
        merged_fields = [_copy_field(field) for field in fields or []]
        known_keys = {str(field.get("key") or "").strip() for field in merged_fields}
        option_dict = dict(options or {})
        self._retain_unknown_options = bool(infer_unknown_fields)
        if infer_unknown_fields:
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
            self._extra_options = (
                {
                    key: copy.deepcopy(value)
                    for key, value in option_dict.items()
                    if key not in self._bindings
                }
                if self._retain_unknown_options
                else {}
            )
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
                normalized = normalize_extension_lines_list(value)
                lines_number = _field_lines_number(binding.field)
                if extension_lines_picker_visible(lines_number):
                    values[key] = normalized
                    continue
                if key not in self._explicit_option_keys and not normalized and not binding.field.get("default"):
                    continue
                if key not in self._explicit_option_keys and not normalized:
                    continue
                values[key] = normalized
                continue
            if key not in self._explicit_option_keys and value in (None, "") and binding.field.get("default") in (None, ""):
                continue
            values[key] = value
        return values

    def set_field_value(self, key: str, value: Any, *, committed: bool = True) -> bool:
        binding = self._bindings.get(str(key or "").strip())
        if binding is None:
            return False
        self._updating = True
        try:
            binding.setter(copy.deepcopy(value))
            if value in (None, ""):
                self._explicit_option_keys.discard(binding.key)
            else:
                self._explicit_option_keys.add(binding.key)
        finally:
            self._updating = False
        self._emit_change(committed=committed)
        return True

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
        if not self._bindings:
            self._invalid_text = None
            self._invalid_error = None
            self._explicit_option_keys = set(data)
            self._extra_options = copy.deepcopy(data)
            self._emit_change(committed=True)
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

    def _show_live_tooltip(self, widget: QWidget, text: str) -> None:
        self._show_live_tooltip_at(widget, text, ToolTipPosition.TOP)

    def _show_live_tooltip_at(self, widget: QWidget, text: str, position: ToolTipPosition) -> None:
        if not text:
            self._hide_live_tooltip()
            return
        parent = self.window() if isinstance(self.window(), QWidget) else self
        if self._live_tooltip is None:
            self._live_tooltip = ToolTip(text, parent)
        self._live_tooltip.setDuration(0)
        self._live_tooltip.setText(text)
        self._live_tooltip.adjustSize()
        self._live_tooltip.show()
        self._live_tooltip.adjustPos(widget, position)
        self._live_tooltip_owner = widget

    def _hide_live_tooltip(self) -> None:
        if self._live_tooltip is not None:
            self._live_tooltip.hide()
        self._live_tooltip_owner = None

    def _register_live_tooltip_widget(self, widget: QWidget, position: ToolTipPosition = ToolTipPosition.TOP) -> None:
        widget.setProperty("_alineLiveTooltip", True)
        widget.setProperty("_alineLiveTooltipPosition", position)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        if isinstance(watched, QWidget) and bool(watched.property("_alineLiveTooltip")):
            position = watched.property("_alineLiveTooltipPosition") or ToolTipPosition.TOP
            if event.type() in {QEvent.Type.Enter, QEvent.Type.FocusIn}:
                text = watched.toolTip().strip()
                if text:
                    self._show_live_tooltip_at(watched, text, position)
            elif event.type() in {QEvent.Type.Leave, QEvent.Type.FocusOut, QEvent.Type.Hide}:
                is_slider_down = bool(getattr(watched, "isSliderDown", lambda: False)())
                if not is_slider_down:
                    self._hide_live_tooltip()
        return super().eventFilter(watched, event)

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
        if field_type == "pickcolor":
            return self._create_pickcolor_binding(field)
        if field_type == "limited":
            return self._create_limited_binding(field)
        if field_type == "figure":
            return self._create_figure_binding(field)
        if field_type == "shot":
            return self._create_shot_binding(field)
        if field_type == "line":
            return self._create_line_binding(field)
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
        container.setMinimumWidth(0)
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
        layout.addWidget(adaptive_row, 0, Qt.AlignmentFlag.AlignTop)
        description = str(field.get("description") or "").strip()
        if description and self._show_field_descriptions:
            hint = make_hint_label(description, container)
            hint.setStyleSheet(f"color: {secondary_color()}; font-size: 11px;")
            layout.addWidget(hint)
        self._flow.addWidget(container, 0, Qt.AlignmentFlag.AlignTop)
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
        container, layout, field_row = self._make_field_card(field, min_width=132, min_control_width=24)
        checkbox = CheckBox("", container)
        checkbox.setText("")
        checkbox.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        field_row.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        field_row.addStretch(1)
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
        edit = SpinBox(container)
        self._set_expanding_control(edit, 60)
        edit.setKeyboardTracking(False)
        placeholder = str(field.get("placeholder") or "").strip()
        min_value = int(field.get("min_value", -999999999) or -999999999)
        max_value = int(field.get("max_value", 999999999) or 999999999)
        allow_empty = field.get("default") in (None, "")
        sentinel = min_value - 1 if allow_empty and min_value > -2147483647 else min_value
        edit.setRange(sentinel, max_value)
        edit.setSingleStep(max(1, int(field.get("step", 1) or 1)))
        if allow_empty and sentinel < min_value:
            edit.setSpecialValueText("")
        if placeholder and hasattr(edit, "lineEdit"):
            line_edit = edit.lineEdit()
            if line_edit is not None and hasattr(line_edit, "setPlaceholderText"):
                line_edit.setPlaceholderText(placeholder)
        field_row.addWidget(edit, 1)
        edit.valueChanged.connect(lambda _value: self._emit_change(committed=True))

        def _get() -> Any:
            if allow_empty and sentinel < min_value and edit.value() == sentinel:
                return None
            return int(edit.value())

        def _set(value: Any) -> None:
            if value in (None, "") and allow_empty and sentinel < min_value:
                edit.setValue(sentinel)
                return
            edit.setValue(int(str(value)))

        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=_get,
            setter=_set,
        )

    def _create_number_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=144, min_control_width=60)
        edit = DoubleSpinBox(container)
        self._set_expanding_control(edit, 60)
        edit.setKeyboardTracking(False)
        placeholder = str(field.get("placeholder") or "").strip()
        min_value = float(field.get("min_value", -999999999.0) or -999999999.0)
        max_value = float(field.get("max_value", 999999999.0) or 999999999.0)
        raw_decimals = field.get("decimals")
        decimals = get_extension_number_decimals() if raw_decimals in (None, "") else int(raw_decimals)
        decimals = max(0, min(12, decimals))
        step = float(field.get("step", 0.1) or 0.1)
        allow_empty = field.get("default") in (None, "")
        sentinel = min_value - max(abs(step), 1.0) if allow_empty else min_value
        edit.setDecimals(decimals)
        edit.setRange(sentinel, max_value)
        edit.setSingleStep(abs(step) if step else 0.1)
        if allow_empty:
            edit.setSpecialValueText("")
        if placeholder and hasattr(edit, "lineEdit"):
            line_edit = edit.lineEdit()
            if line_edit is not None and hasattr(line_edit, "setPlaceholderText"):
                line_edit.setPlaceholderText(placeholder)
        field_row.addWidget(edit, 1)
        edit.valueChanged.connect(lambda _value: self._emit_change(committed=True))

        def _get() -> Any:
            if allow_empty and edit.value() == sentinel:
                return None
            return float(edit.value())

        def _set(value: Any) -> None:
            if value in (None, "") and allow_empty:
                edit.setValue(sentinel)
                return
            edit.setValue(float(str(value)))

        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=_get,
            setter=_set,
        )

    def _create_color_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=104, min_control_width=36)
        button = ColorPickerButton(QColor("#0078D4"), "", container, enableAlpha=False)
        button.setFixedSize(WORKBENCH_BUTTON_HEIGHT + 2, WORKBENCH_BUTTON_HEIGHT + 2)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        field_row.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        field_row.addStretch(1)
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
        field_row.addWidget(slider, 1)

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

        def _update_tooltip(raw_value: int) -> None:
            text = _format(raw_value)
            slider.setToolTip(text)
            if (self._live_tooltip is not None and self._live_tooltip.isVisible()) or slider.isSliderDown() or slider.underMouse() or slider.hasFocus():
                self._show_live_tooltip_at(slider, text, ToolTipPosition.TOP)

        def _set(value: Any) -> None:
            numeric = float(value if value is not None else min_value)
            slider.setValue(int(round(numeric * scale)))
            _update_tooltip(slider.value())

        slider.setToolTip(_format(slider.value()))
        self._register_live_tooltip_widget(slider, ToolTipPosition.TOP)
        slider.valueChanged.connect(_update_tooltip)
        slider.sliderPressed.connect(lambda: self._show_live_tooltip_at(slider, slider.toolTip(), ToolTipPosition.TOP))
        slider.sliderReleased.connect(self._hide_live_tooltip)
        slider.destroyed.connect(lambda *_args: self._hide_live_tooltip())
        slider.valueChanged.connect(lambda _value: self._emit_change(committed=True))
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=_get,
            setter=_set,
        )

    @staticmethod
    def _normalize_pickcolor_value(value: Any) -> Optional[Dict[str, int]]:
        if isinstance(value, QColor) and value.isValid():
            return {
                "r": int(value.red()),
                "g": int(value.green()),
                "b": int(value.blue()),
            }
        if isinstance(value, dict):
            try:
                return {
                    "r": int(value.get("r", 0) or 0),
                    "g": int(value.get("g", 0) or 0),
                    "b": int(value.get("b", 0) or 0),
                }
            except (TypeError, ValueError):
                return None
        text = str(value or "").strip()
        color = QColor(text)
        if color.isValid():
            return {
                "r": int(color.red()),
                "g": int(color.green()),
                "b": int(color.blue()),
            }
        return None

    @staticmethod
    def _pickcolor_summary(value: Optional[Dict[str, int]]) -> str:
        if not value:
            return "未取色"
        return "#{:02X}{:02X}{:02X}".format(
            int(value.get("r", 0) or 0),
            int(value.get("g", 0) or 0),
            int(value.get("b", 0) or 0),
        )

    @staticmethod
    def _pickcolor_button_style(value: Optional[Dict[str, int]]) -> str:
        if not value:
            return ""
        color = QColor(
            int(value.get("r", 0) or 0),
            int(value.get("g", 0) or 0),
            int(value.get("b", 0) or 0),
        )
        if not color.isValid():
            return ""

        text_color = QColor(255, 255, 255) if color.lightnessF() < 0.5 else QColor(0, 0, 0)
        hover_color = color.lighter(108) if color.lightnessF() < 0.75 else color.darker(105)
        pressed_color = color.lighter(116) if color.lightnessF() < 0.75 else color.darker(112)
        return (
            "ToolButton {"
            f"background: {color.name(QColor.NameFormat.HexRgb)};"
            f"border: 1px solid {border_color()};"
            "border-radius: 6px;"
            f"color: {text_color.name(QColor.NameFormat.HexRgb)};"
            "}"
            "ToolButton:hover {"
            f"background: {hover_color.name(QColor.NameFormat.HexRgb)};"
            f"border: 1px solid {border_color()};"
            "border-radius: 6px;"
            "}"
            "ToolButton:pressed {"
            f"background: {pressed_color.name(QColor.NameFormat.HexRgb)};"
            f"border: 1px solid {border_color()};"
            "border-radius: 6px;"
            "}"
        )

    @staticmethod
    def _shot_summary(value: Any) -> str:
        if isinstance(value, dict):
            size = value.get("size")
            if isinstance(size, (list, tuple)) and len(size) >= 2:
                try:
                    width = int(size[0])
                    height = int(size[1])
                except (TypeError, ValueError):
                    width = height = 0
                if width > 0 and height > 0:
                    return f"已截取 {width}×{height}px"
            bounds = value.get("bounds")
            if isinstance(bounds, (list, tuple)) and len(bounds) >= 4:
                return "已截取区域"
        if value in (None, "", {}):
            return "未截图"
        return "已截取模板"

    def _create_interactive_action_binding(
        self,
        field: Dict[str, Any],
        *,
        icon,
        button_tooltip: str,
        empty_text: str,
        summary_for_value: Callable[[Any], str],
        normalize_value: Optional[Callable[[Any], Any]] = None,
        button_style_for_value: Optional[Callable[[Any], str]] = None,
    ) -> _FieldBinding:
        container, layout, field_row = self._make_field_card(field, min_width=220, min_control_width=132)
        button = ToolButton(icon, container)
        button.setObjectName(f"interactiveFieldButton:{field.get('key')}")
        button.setFixedSize(WORKBENCH_BUTTON_HEIGHT, WORKBENCH_BUTTON_HEIGHT)
        button.setToolTip(button_tooltip)
        install_fluent_tooltip(button, delay=300, position=ToolTipPosition.BOTTOM)
        field_row.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        summary = CaptionLabel(empty_text, container)
        summary.setObjectName(f"interactiveFieldSummary:{field.get('key')}")
        summary.setWordWrap(True)
        summary.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        field_row.addWidget(summary, 1)
        layout.addStretch(1)

        state = {"value": None}

        def _set(value: Any) -> None:
            normalized = normalize_value(value) if normalize_value is not None else copy.deepcopy(value)
            state["value"] = copy.deepcopy(normalized)
            summary_text = summary_for_value(normalized)
            summary.setText(summary_text)
            summary.setToolTip(summary_text if normalized not in (None, "", {}) else "")
            install_fluent_tooltip(summary, delay=300, position=ToolTipPosition.BOTTOM)
            button.setToolTip(summary_text if normalized not in (None, "", {}) else button_tooltip)
            install_fluent_tooltip(button, delay=300, position=ToolTipPosition.BOTTOM)
            button.setStyleSheet(button_style_for_value(normalized) if button_style_for_value is not None else "")

        def _request() -> None:
            self.interactiveFieldRequested.emit(str(field.get("key") or ""), copy.deepcopy(field))

        button.clicked.connect(_request)
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=lambda: copy.deepcopy(state["value"]),
            setter=_set,
        )

    def _create_pickcolor_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        return self._create_interactive_action_binding(
            field,
            icon=FIF.PALETTE,
            button_tooltip="点击后在页面中取色",
            empty_text="未取色",
            summary_for_value=self._pickcolor_summary,
            normalize_value=self._normalize_pickcolor_value,
            button_style_for_value=self._pickcolor_button_style,
        )

    def _create_shot_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        return self._create_interactive_action_binding(
            field,
            icon=FIF.CUT,
            button_tooltip="点击后在页面中截图",
            empty_text="未截图",
            summary_for_value=self._shot_summary,
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

    def _create_line_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        container, _layout, field_row = self._make_field_card(field, min_width=168, min_control_width=96)
        button = PushButton("选择曲线", container)
        self._set_expanding_control(button, 96)
        field_row.addWidget(button, 1)

        state: Dict[str, Optional[int]] = {"line": None}

        def _selected_label() -> str:
            value = state["line"]
            if value is None:
                return ""
            try:
                index = int(value)
            except (TypeError, ValueError):
                return ""
            offset = index - 1
            if 0 <= offset < len(self._line_candidates):
                return self._line_candidates[offset]
            return ""

        def _tooltip_text() -> str:
            if not self._line_candidates:
                return "当前没有可选曲线"
            label = _selected_label()
            if label:
                return f"当前参数曲线: {label}"
            if state["line"] not in (None, ""):
                return "当前参数曲线已不可用，请重新选择"
            return "请选择 1 条曲线作为内部参数"

        def _refresh() -> None:
            button.setEnabled(bool(self._line_candidates))
            button.setText("选择曲线")
            button.setToolTip(_tooltip_text())
            install_fluent_tooltip(button, delay=300, position=ToolTipPosition.BOTTOM)

        def _set(value: Any) -> None:
            if value in (None, ""):
                state["line"] = None
            else:
                try:
                    state["line"] = int(value)
                except (TypeError, ValueError):
                    state["line"] = None
            _refresh()

        def _choose() -> None:
            if not self._line_candidates:
                return
            result, accepted = _SingleLineSelectionDialog.get_index(
                self.window() if self.window() is not None else self,
                _field_label(field),
                self._line_candidates,
                selected_index=state["line"],
            )
            if not accepted:
                return
            state["line"] = result
            _refresh()
            self._emit_change(committed=True)

        button.clicked.connect(_choose)
        _refresh()
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=lambda: state["line"],
            setter=_set,
            refresh=_refresh,
        )

    def _create_lines_binding(self, field: Dict[str, Any]) -> _FieldBinding:
        lines_number = _field_lines_number(field) or (1, 1)
        state = {"lines_list": normalize_extension_lines_list(field.get("default"))}

        if not extension_lines_picker_visible(lines_number):
            return _FieldBinding(
                key=str(field.get("key")),
                field=field,
                getter=lambda: list(state["lines_list"]),
                setter=lambda value: state.update({"lines_list": normalize_extension_lines_list(value)}),
            )

        container, layout, field_row = self._make_field_card(field, min_width=168, min_control_width=96)
        button = PushButton("选择曲线", container)
        self._set_expanding_control(button, 96)
        field_row.addWidget(button, 1)
        summary = CaptionLabel("当前: 未选择", container)
        summary.setWordWrap(True)
        summary.setStyleSheet(f"color: {secondary_color()}; font-size: 11px;")
        layout.addWidget(summary)
        install_fluent_tooltip(summary, delay=300, position=ToolTipPosition.BOTTOM)

        def _selected_labels() -> List[str]:
            labels: List[str] = []
            for index in state["lines_list"]:
                offset = int(index) - 1
                if 0 <= offset < len(self._line_candidates):
                    labels.append(self._line_candidates[offset])
            return labels

        def _tooltip_text() -> str:
            support_text = extension_lines_support_text(lines_number)
            if not self._line_candidates:
                return f"本扩展支持 {support_text}，当前没有可选曲线"
            labels = _selected_labels()
            if labels:
                return f"本扩展支持 {support_text}。已选择: " + "；".join(labels)
            return f"本扩展支持 {support_text}。尚未显式选择曲线。"

        def _refresh() -> None:
            labels = _selected_labels()
            summary_text = "；".join(labels)
            if summary_text:
                summary.setText(f"当前: {summary_text}")
                summary.setToolTip(summary_text)
            else:
                summary.setText("当前: 未选择")
                summary.setToolTip("")
            install_fluent_tooltip(summary, delay=300, position=ToolTipPosition.BOTTOM)
            button.setEnabled(bool(self._line_candidates))
            button.setText("选择曲线")
            button.setToolTip(_tooltip_text())
            install_fluent_tooltip(button, delay=300, position=ToolTipPosition.BOTTOM)

        def _set(value: Any) -> None:
            state["lines_list"] = normalize_extension_lines_list(value)
            _refresh()

        def _choose() -> None:
            if not self._line_candidates:
                return
            selected_indices = [int(item) for item in state["lines_list"]]
            result, accepted = _LineSelectionDialog.get_indices(
                self.window() if self.window() is not None else self,
                _field_label(field),
                self._line_candidates,
                selected_indices=selected_indices,
                lines_number=lines_number,
            )
            if not accepted:
                return
            state["lines_list"] = result
            _refresh()
            self._emit_change(committed=True)

        button.clicked.connect(_choose)
        _refresh()
        return _FieldBinding(
            key=str(field.get("key")),
            field=field,
            getter=lambda: list(state["lines_list"]),
            setter=_set,
            refresh=_refresh,
        )