from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QDialog, QHBoxLayout, QHeaderView, QTableWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CaptionLabel, CheckBox, ComboBox, LineEdit, PrimaryPushButton, PushButton, TableWidget

from core.project_manager import project_manager
from ui.widgets.focus_commit import install_click_away_focus_commit
from .export_models import (
    DataExportPlan,
    DataCreateTargetOption,
    BatchDataExportPlan,
    PictureExportPlan,
    AnalysisResultSavePlan,
)


@dataclass(frozen=True)
class CurveFileExportPlan:
    action: str
    file_format: str
    include_timestamp: bool = False
    merged: bool = False


class _DataExportDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        title: str,
        entries: List[dict],
        default_export_name: str,
        default_file_name: str,
        file_suffix: str,
        current_text: Optional[str],
        show_export_name: bool,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self._entries = list(entries)
        self._file_suffix = file_suffix
        self._show_export_name = bool(show_export_name)
        self._default_export_name = (default_export_name or "").strip()
        self._accepted_plan: Optional[DataExportPlan] = None
        self._last_auto_file_name = _ensure_suffix(default_file_name, file_suffix)
        self._file_name_manually_edited = False
        self._click_away_focus_commit = install_click_away_focus_commit(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        self._name_container = QWidget(self)
        name_row = QHBoxLayout(self._name_container)
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(8)
        name_row.addWidget(BodyLabel("名称:", self._name_container))
        self._export_name_edit = LineEdit(self)
        self._export_name_edit.setText(self._default_export_name)
        self._export_name_edit.setPlaceholderText("输入导出名称")
        self._export_name_edit.textChanged.connect(self._on_export_name_changed)
        name_row.addWidget(self._export_name_edit, 1)
        layout.addWidget(self._name_container)
        self._name_container.setVisible(self._show_export_name)

        target_row = QHBoxLayout()
        target_row.addWidget(BodyLabel("目标:", self))
        self._target_combo = ComboBox(self)
        for entry in self._entries:
            self._target_combo.addItem(entry["label"])
        initial_index = next((index for index, entry in enumerate(self._entries) if entry["label"] == current_text), 0)
        self._target_combo.setCurrentIndex(initial_index)
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        target_row.addWidget(self._target_combo, 1)
        layout.addLayout(target_row)

        self._target_hint = CaptionLabel("", self)
        self._target_hint.setWordWrap(True)
        layout.addWidget(self._target_hint)

        self._file_name_container = QWidget(self)
        file_name_row = QHBoxLayout(self._file_name_container)
        file_name_row.setContentsMargins(0, 0, 0, 0)
        file_name_row.setSpacing(8)
        file_name_row.addWidget(BodyLabel("数据文件名称:", self._file_name_container))
        self._data_file_name_edit = LineEdit(self._file_name_container)
        self._data_file_name_edit.setText(self._last_auto_file_name)
        self._data_file_name_edit.setPlaceholderText(f"输入数据文件名称（默认 {file_suffix}）")
        self._data_file_name_edit.textEdited.connect(self._on_file_name_edited)
        file_name_row.addWidget(self._data_file_name_edit, 1)
        layout.addWidget(self._file_name_container)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        confirm_btn = PrimaryPushButton("确定", self)
        confirm_btn.clicked.connect(self._on_accept)
        button_row.addWidget(confirm_btn)
        layout.addLayout(button_row)

        self._on_target_changed(initial_index)

    def _selected_entry(self) -> Optional[dict]:
        index = self._target_combo.currentIndex()
        if 0 <= index < len(self._entries):
            return self._entries[index]
        return None

    def _on_export_name_changed(self, text: str) -> None:
        if self._file_name_manually_edited:
            return
        auto_name = _ensure_suffix(text.strip(), self._file_suffix)
        self._last_auto_file_name = auto_name
        self._data_file_name_edit.setText(auto_name)

    def _on_file_name_edited(self, _text: str) -> None:
        self._file_name_manually_edited = True

    def _on_target_changed(self, _index: int) -> None:
        entry = self._selected_entry()
        create_new = bool(entry and entry.get("mode") == "create_file")
        self._file_name_container.setVisible(create_new)
        self._target_hint.setText(
            "将数据列追加到已有数据文件。" if not create_new else "将创建一个新的数据文件，并写入当前导出数据列。"
        )

    def _on_accept(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        export_name = self._export_name_edit.text().strip() if self._show_export_name else self._default_export_name
        if entry.get("mode") == "append":
            if not export_name:
                self._export_name_edit.setFocus()
                return
            self._accepted_plan = DataExportPlan(export_name=export_name, target_data_file_id=entry["data_file_id"])
            self.accept()
            return
        file_name = _ensure_suffix(self._data_file_name_edit.text().strip(), self._file_suffix)
        if not file_name:
            self._data_file_name_edit.setFocus()
            return
        if not export_name:
            export_name = Path(file_name).stem
        parent_id = entry.get("node_id")
        resolver = entry.get("resolver")
        if parent_id is None and callable(resolver):
            parent_id = resolver()
        if not parent_id:
            return
        self._accepted_plan = DataExportPlan(
            export_name=export_name,
            new_parent_id=parent_id,
            new_data_file_name=file_name,
        )
        self.accept()

    @property
    def accepted_plan(self) -> Optional[DataExportPlan]:
        return self._accepted_plan


class _BatchDataExportDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        title: str,
        entries: List[dict],
        source_labels: List[str],
        default_export_names: List[str],
        default_file_name: str,
        file_suffix: str,
        current_text: Optional[str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        self._entries = list(entries)
        self._file_suffix = file_suffix
        self._accepted_plan: Optional[BatchDataExportPlan] = None
        self._last_auto_file_name = _ensure_suffix(default_file_name, file_suffix)
        self._click_away_focus_commit = install_click_away_focus_commit(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        hint_label = CaptionLabel("可逐项修改每条导出数据列的名称。", self)
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)

        self._name_table = TableWidget(self)
        self._name_table.setColumnCount(2)
        self._name_table.setHorizontalHeaderLabels(["来源", "导出名称"])
        self._name_table.setRowCount(len(default_export_names))
        self._name_table.verticalHeader().setVisible(False)
        self._name_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._name_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self._name_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._name_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, export_name in enumerate(default_export_names):
            source_item = QTableWidgetItem(source_labels[row] if row < len(source_labels) else export_name)
            source_item.setFlags(source_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._name_table.setItem(row, 0, source_item)
            self._name_table.setItem(row, 1, QTableWidgetItem(export_name))
        layout.addWidget(self._name_table)

        target_row = QHBoxLayout()
        target_row.addWidget(BodyLabel("目标:", self))
        self._target_combo = ComboBox(self)
        for entry in self._entries:
            self._target_combo.addItem(entry["label"])
        initial_index = next((index for index, entry in enumerate(self._entries) if entry["label"] == current_text), 0)
        self._target_combo.setCurrentIndex(initial_index)
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        target_row.addWidget(self._target_combo, 1)
        layout.addLayout(target_row)

        self._target_hint = CaptionLabel("", self)
        self._target_hint.setWordWrap(True)
        layout.addWidget(self._target_hint)

        self._file_name_container = QWidget(self)
        file_name_row = QHBoxLayout(self._file_name_container)
        file_name_row.setContentsMargins(0, 0, 0, 0)
        file_name_row.setSpacing(8)
        file_name_row.addWidget(BodyLabel("数据文件名称:", self._file_name_container))
        self._data_file_name_edit = LineEdit(self._file_name_container)
        self._data_file_name_edit.setText(self._last_auto_file_name)
        self._data_file_name_edit.setPlaceholderText(f"输入数据文件名称（默认 {file_suffix}）")
        file_name_row.addWidget(self._data_file_name_edit, 1)
        layout.addWidget(self._file_name_container)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        confirm_btn = PrimaryPushButton("确定", self)
        confirm_btn.clicked.connect(self._on_accept)
        button_row.addWidget(confirm_btn)
        layout.addLayout(button_row)

        self._on_target_changed(initial_index)

    def _selected_entry(self) -> Optional[dict]:
        index = self._target_combo.currentIndex()
        if 0 <= index < len(self._entries):
            return self._entries[index]
        return None

    def _collect_export_names(self) -> Optional[List[str]]:
        export_names: List[str] = []
        for row in range(self._name_table.rowCount()):
            item = self._name_table.item(row, 1)
            name = item.text().strip() if item is not None else ""
            if not name:
                self._name_table.setCurrentCell(row, 1)
                if item is not None:
                    self._name_table.editItem(item)
                return None
            export_names.append(name)
        return export_names

    def _on_target_changed(self, _index: int) -> None:
        entry = self._selected_entry()
        create_new = bool(entry and entry.get("mode") == "create_file")
        self._file_name_container.setVisible(create_new)
        self._target_hint.setText(
            "将多条数据列追加到已有数据文件。" if not create_new else "将创建一个新的数据文件，并写入当前批量导出数据列。"
        )

    def _on_accept(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        export_names = self._collect_export_names()
        if export_names is None:
            return
        if entry.get("mode") == "append":
            self._accepted_plan = BatchDataExportPlan(
                export_names=export_names,
                target_data_file_id=entry["data_file_id"],
            )
            self.accept()
            return
        file_name = _ensure_suffix(self._data_file_name_edit.text().strip(), self._file_suffix)
        if not file_name:
            self._data_file_name_edit.setFocus()
            return
        parent_id = entry.get("node_id")
        resolver = entry.get("resolver")
        if parent_id is None and callable(resolver):
            parent_id = resolver()
        if not parent_id:
            return
        self._accepted_plan = BatchDataExportPlan(
            export_names=export_names,
            new_parent_id=parent_id,
            new_data_file_name=file_name,
        )
        self.accept()

    @property
    def accepted_plan(self) -> Optional[BatchDataExportPlan]:
        return self._accepted_plan


class _PictureExportDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        title: str,
        folder_entries: List[dict],
        default_export_name: str,
        current_text: Optional[str],
        file_suffix: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self._folder_entries = list(folder_entries)
        self._choice_entries = list(folder_entries) + [{"label": "新建图片子文件夹...", "mode": "create_folder", "node_id": None}]
        self._file_suffix = file_suffix
        self._accepted_plan: Optional[PictureExportPlan] = None
        self._click_away_focus_commit = install_click_away_focus_commit(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        name_row = QHBoxLayout()
        name_row.addWidget(BodyLabel("图片名称:", self))
        self._export_name_edit = LineEdit(self)
        self._export_name_edit.setText(_ensure_suffix(default_export_name, file_suffix))
        self._export_name_edit.setPlaceholderText(f"输入图片名称（默认 {file_suffix}）")
        name_row.addWidget(self._export_name_edit, 1)
        layout.addLayout(name_row)

        target_row = QHBoxLayout()
        target_row.addWidget(BodyLabel("图片文件夹:", self))
        self._target_combo = ComboBox(self)
        for entry in self._choice_entries:
            self._target_combo.addItem(entry["label"])
        initial_index = next((index for index, entry in enumerate(self._choice_entries) if entry["label"] == current_text), 0)
        self._target_combo.setCurrentIndex(initial_index)
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        target_row.addWidget(self._target_combo, 1)
        layout.addLayout(target_row)

        self._folder_hint = CaptionLabel("", self)
        self._folder_hint.setWordWrap(True)
        layout.addWidget(self._folder_hint)

        self._new_folder_container = QWidget(self)
        new_folder_layout = QVBoxLayout(self._new_folder_container)
        new_folder_layout.setContentsMargins(0, 0, 0, 0)
        new_folder_layout.setSpacing(8)

        parent_row = QHBoxLayout()
        parent_row.addWidget(BodyLabel("父文件夹:", self._new_folder_container))
        self._parent_combo = ComboBox(self._new_folder_container)
        for entry in self._folder_entries:
            self._parent_combo.addItem(entry["label"])
        parent_row.addWidget(self._parent_combo, 1)
        new_folder_layout.addLayout(parent_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(BodyLabel("新文件夹名称:", self._new_folder_container))
        self._folder_name_edit = LineEdit(self._new_folder_container)
        self._folder_name_edit.setPlaceholderText("输入子文件夹名称")
        folder_row.addWidget(self._folder_name_edit, 1)
        new_folder_layout.addLayout(folder_row)
        layout.addWidget(self._new_folder_container)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        confirm_btn = PrimaryPushButton("确定", self)
        confirm_btn.clicked.connect(self._on_accept)
        button_row.addWidget(confirm_btn)
        layout.addLayout(button_row)

        if current_text:
            parent_index = next((index for index, entry in enumerate(self._folder_entries) if entry["label"] == current_text), 0)
            self._parent_combo.setCurrentIndex(parent_index)
        self._on_target_changed(initial_index)

    def _selected_entry(self) -> Optional[dict]:
        index = self._target_combo.currentIndex()
        if 0 <= index < len(self._choice_entries):
            return self._choice_entries[index]
        return None

    def _on_target_changed(self, _index: int) -> None:
        entry = self._selected_entry()
        creating_folder = bool(entry and entry.get("mode") == "create_folder")
        self._new_folder_container.setVisible(creating_folder)
        self._folder_hint.setText(
            "导出到已有图片文件夹。" if not creating_folder else "在选定父文件夹下创建新的图片子文件夹后导出。"
        )

    def _on_accept(self) -> None:
        export_name = _ensure_suffix(self._export_name_edit.text().strip(), self._file_suffix)
        if not export_name:
            self._export_name_edit.setFocus()
            return
        entry = self._selected_entry()
        if entry is None:
            return
        if entry.get("mode") == "folder":
            self._accepted_plan = PictureExportPlan(export_name=export_name, target_folder_id=entry["node_id"])
            self.accept()
            return
        parent_index = self._parent_combo.currentIndex()
        if not (0 <= parent_index < len(self._folder_entries)):
            return
        folder_name = self._folder_name_edit.text().strip()
        if not folder_name:
            self._folder_name_edit.setFocus()
            return
        parent_entry = self._folder_entries[parent_index]
        folder = project_manager.add_folder(folder_name, parent_id=parent_entry["node_id"], group_type="pictures")
        if folder is None:
            return
        self._accepted_plan = PictureExportPlan(export_name=export_name, target_folder_id=folder.id)
        self.accept()

    @property
    def accepted_plan(self) -> Optional[PictureExportPlan]:
        return self._accepted_plan


class _AnalysisResultSaveDialog(QDialog):
    def __init__(
        self,
        parent,
        *,
        title: str,
        folder_entries: List[dict],
        default_result_name: str,
        current_text: Optional[str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self._folder_entries = list(folder_entries)
        self._choice_entries = list(folder_entries) + [{"label": "新建分析结果子文件夹...", "mode": "create_folder", "node_id": None}]
        self._accepted_plan: Optional[AnalysisResultSavePlan] = None
        self._click_away_focus_commit = install_click_away_focus_commit(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        name_row = QHBoxLayout()
        name_row.addWidget(BodyLabel("结果名称:", self))
        self._result_name_edit = LineEdit(self)
        self._result_name_edit.setText((default_result_name or "").strip())
        self._result_name_edit.setPlaceholderText("输入分析结果名称")
        name_row.addWidget(self._result_name_edit, 1)
        layout.addLayout(name_row)

        target_row = QHBoxLayout()
        target_row.addWidget(BodyLabel("保存位置:", self))
        self._target_combo = ComboBox(self)
        for entry in self._choice_entries:
            self._target_combo.addItem(entry["label"])
        initial_index = next((index for index, entry in enumerate(self._choice_entries) if entry["label"] == current_text), 0)
        self._target_combo.setCurrentIndex(initial_index)
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        target_row.addWidget(self._target_combo, 1)
        layout.addLayout(target_row)

        self._target_hint = CaptionLabel("", self)
        self._target_hint.setWordWrap(True)
        layout.addWidget(self._target_hint)

        self._new_folder_container = QWidget(self)
        new_folder_layout = QVBoxLayout(self._new_folder_container)
        new_folder_layout.setContentsMargins(0, 0, 0, 0)
        new_folder_layout.setSpacing(8)

        parent_row = QHBoxLayout()
        parent_row.addWidget(BodyLabel("父文件夹:", self._new_folder_container))
        self._parent_combo = ComboBox(self._new_folder_container)
        for entry in self._folder_entries:
            self._parent_combo.addItem(entry["label"])
        parent_row.addWidget(self._parent_combo, 1)
        new_folder_layout.addLayout(parent_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(BodyLabel("新文件夹名称:", self._new_folder_container))
        self._folder_name_edit = LineEdit(self._new_folder_container)
        self._folder_name_edit.setPlaceholderText("输入分析结果子文件夹名称")
        folder_row.addWidget(self._folder_name_edit, 1)
        new_folder_layout.addLayout(folder_row)
        layout.addWidget(self._new_folder_container)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        confirm_btn = PrimaryPushButton("确定", self)
        confirm_btn.clicked.connect(self._on_accept)
        button_row.addWidget(confirm_btn)
        layout.addLayout(button_row)

        if current_text:
            parent_index = next((index for index, entry in enumerate(self._folder_entries) if entry["label"] == current_text), 0)
            self._parent_combo.setCurrentIndex(parent_index)
        self._on_target_changed(initial_index)

    def _selected_entry(self) -> Optional[dict]:
        index = self._target_combo.currentIndex()
        if 0 <= index < len(self._choice_entries):
            return self._choice_entries[index]
        return None

    def _on_target_changed(self, _index: int) -> None:
        entry = self._selected_entry()
        creating_folder = bool(entry and entry.get("mode") == "create_folder")
        self._new_folder_container.setVisible(creating_folder)
        self._target_hint.setText(
            "保存到已有分析结果文件夹。" if not creating_folder else "在选定父文件夹下创建新的分析结果子文件夹后保存。"
        )

    def _on_accept(self) -> None:
        result_name = self._result_name_edit.text().strip()
        if not result_name:
            self._result_name_edit.setFocus()
            return
        entry = self._selected_entry()
        if entry is None:
            return
        if entry.get("mode") == "folder":
            self._accepted_plan = AnalysisResultSavePlan(result_name=result_name, target_parent_id=entry["node_id"])
            self.accept()
            return
        parent_index = self._parent_combo.currentIndex()
        if not (0 <= parent_index < len(self._folder_entries)):
            return
        folder_name = self._folder_name_edit.text().strip()
        if not folder_name:
            self._folder_name_edit.setFocus()
            return
        parent_entry = self._folder_entries[parent_index]
        folder = project_manager.add_folder(folder_name, parent_id=parent_entry["node_id"], group_type="analysis_result_group")
        if folder is None:
            return
        self._accepted_plan = AnalysisResultSavePlan(result_name=result_name, target_parent_id=folder.id)
        self.accept()

    @property
    def accepted_plan(self) -> Optional[AnalysisResultSavePlan]:
        return self._accepted_plan


class _CurveFileExportDialog(QDialog):
    _FORMAT_OPTIONS = [
        ("csv", "CSV (.csv)"),
        ("xls", "Excel 97-2003 (.xls)"),
        ("txt", "文本 (.txt)"),
        ("dat", "数据文本 (.dat)"),
    ]

    def __init__(
        self,
        parent,
        *,
        title: str,
        source_labels: List[str],
        merge_supported: bool,
        default_format: str = "csv",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self._source_labels = [str(label or "未命名曲线") for label in source_labels]
        self._merge_supported = bool(merge_supported)
        self._accepted_plan: Optional[CurveFileExportPlan] = None
        self._format_values = [value for value, _label in self._FORMAT_OPTIONS]
        self._click_away_focus_commit = install_click_away_focus_commit(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)

        summary = CaptionLabel(self._summary_text(), self)
        summary.setWordWrap(True)
        layout.addWidget(summary)

        format_row = QHBoxLayout()
        format_row.addWidget(BodyLabel("导出格式:", self))
        self._format_combo = ComboBox(self)
        for _value, label in self._FORMAT_OPTIONS:
            self._format_combo.addItem(label)
        default_index = next((index for index, value in enumerate(self._format_values) if value == default_format), 0)
        self._format_combo.setCurrentIndex(default_index)
        format_row.addWidget(self._format_combo, 1)
        layout.addLayout(format_row)

        self._timestamp_check = CheckBox("导出时添加时间戳", self)
        self._timestamp_check.setChecked(False)
        layout.addWidget(self._timestamp_check)

        self._merge_check = CheckBox("X 对齐时合并为单表", self)
        self._merge_check.setVisible(len(self._source_labels) > 1)
        self._merge_check.setEnabled(self._merge_supported)
        self._merge_check.setChecked(False)
        layout.addWidget(self._merge_check)

        self._merge_hint = CaptionLabel(self._merge_hint_text(), self)
        self._merge_hint.setWordWrap(True)
        layout.addWidget(self._merge_hint)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)
        clipboard_btn = PushButton("复制到剪贴板", self)
        clipboard_btn.clicked.connect(lambda: self._accept_with_action("clipboard"))
        button_row.addWidget(clipboard_btn)
        export_btn = PrimaryPushButton("导出到文件", self)
        export_btn.clicked.connect(lambda: self._accept_with_action("file"))
        button_row.addWidget(export_btn)
        layout.addLayout(button_row)

    def _summary_text(self) -> str:
        count = len(self._source_labels)
        if count <= 3:
            label_text = "、".join(self._source_labels)
        else:
            label_text = "、".join(self._source_labels[:3]) + f" 等 {count} 条曲线"
        return f"当前准备导出 {count} 条曲线: {label_text}"

    def _merge_hint_text(self) -> str:
        if len(self._source_labels) <= 1:
            return "当前为单曲线导出。"
        if self._merge_supported:
            return "多条曲线的 X 坐标已对齐，可选择合并导出为单表。"
        return "多条曲线的 X 坐标未对齐，将按分组导出。"

    def _selected_format(self) -> str:
        index = self._format_combo.currentIndex()
        if 0 <= index < len(self._format_values):
            return self._format_values[index]
        return "csv"

    def _accept_with_action(self, action: str) -> None:
        self._accepted_plan = CurveFileExportPlan(
            action=action,
            file_format=self._selected_format(),
            include_timestamp=self._timestamp_check.isChecked(),
            merged=self._merge_check.isVisible() and self._merge_check.isEnabled() and self._merge_check.isChecked(),
        )
        self.accept()

    @property
    def accepted_plan(self) -> Optional[CurveFileExportPlan]:
        return self._accepted_plan


def choose_data_export_plan(
    parent,
    *,
    title: str,
    default_export_name: str,
    default_file_name: str,
    preferred_target_node_id: Optional[str] = None,
    file_suffix: str = ".data",
    create_target_options: Optional[List[DataCreateTargetOption]] = None,
    allow_append_to_existing: bool = True,
    show_export_name: bool = True,
) -> Optional[DataExportPlan]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return None

    entries = _build_data_target_entries(
        create_target_options=create_target_options,
        allow_append_to_existing=allow_append_to_existing,
    )
    if not entries:
        return None
    current_text = _preferred_target_label(entries, preferred_target_node_id)
    dialog = _DataExportDialog(
        parent,
        title=title,
        entries=entries,
        default_export_name=default_export_name,
        default_file_name=default_file_name,
        file_suffix=file_suffix,
        current_text=current_text,
        show_export_name=show_export_name,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.accepted_plan


def choose_data_export_batch_plan(
    parent,
    *,
    title: str,
    source_labels: List[str],
    default_export_names: List[str],
    default_file_name: str,
    preferred_target_node_id: Optional[str] = None,
    file_suffix: str = ".data",
    create_target_options: Optional[List[DataCreateTargetOption]] = None,
    allow_append_to_existing: bool = True,
) -> Optional[BatchDataExportPlan]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return None

    entries = _build_data_target_entries(
        create_target_options=create_target_options,
        allow_append_to_existing=allow_append_to_existing,
    )
    if not entries:
        return None
    current_text = _preferred_target_label(entries, preferred_target_node_id)
    dialog = _BatchDataExportDialog(
        parent,
        title=title,
        entries=entries,
        source_labels=source_labels,
        default_export_names=default_export_names,
        default_file_name=default_file_name,
        file_suffix=file_suffix,
        current_text=current_text,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.accepted_plan


def choose_picture_export_plan(
    parent,
    *,
    title: str,
    default_export_name: str,
    preferred_target_node_id: Optional[str] = None,
    file_suffix: str = ".png",
) -> Optional[PictureExportPlan]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return None

    folder_entries = _build_picture_folder_entries()
    if not folder_entries:
        return None
    current_text = _preferred_target_label(folder_entries, project_manager.get_picture_target_folder_id(preferred_target_node_id))
    dialog = _PictureExportDialog(
        parent,
        title=title,
        folder_entries=folder_entries,
        default_export_name=default_export_name,
        current_text=current_text,
        file_suffix=file_suffix,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.accepted_plan


def choose_analysis_result_save_plan(
    parent,
    *,
    title: str,
    default_result_name: str,
    preferred_target_node_id: Optional[str] = None,
) -> Optional[AnalysisResultSavePlan]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return None

    folder_entries = _build_analysis_result_folder_entries()
    if not folder_entries:
        return None
    current_text = _preferred_target_label(
        folder_entries,
        project_manager.get_analysis_result_target_folder_id(preferred_target_node_id),
    )
    dialog = _AnalysisResultSaveDialog(
        parent,
        title=title,
        folder_entries=folder_entries,
        default_result_name=default_result_name,
        current_text=current_text,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.accepted_plan


def choose_curve_file_export_plan(
    parent,
    *,
    title: str,
    source_labels: List[str],
    merge_supported: bool,
    default_format: str = "csv",
) -> Optional[CurveFileExportPlan]:
    dialog = _CurveFileExportDialog(
        parent,
        title=title,
        source_labels=source_labels,
        merge_supported=merge_supported,
        default_format=default_format,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.accepted_plan


def curve_export_file_filter(file_format: str) -> str:
    file_format = str(file_format or "csv").strip().lower()
    return {
        "csv": "CSV 文件 (*.csv)",
        "xls": "Excel 97-2003 文件 (*.xls)",
        "txt": "文本文件 (*.txt)",
        "dat": "数据文件 (*.dat)",
    }.get(file_format, "所有文件 (*)")


def _build_data_target_entries(
    create_target_options: Optional[List[DataCreateTargetOption]] = None,
    allow_append_to_existing: bool = True,
) -> List[dict]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return []
    entries: List[dict] = []
    if allow_append_to_existing:
        for node in project.tree.nodes:
            if node.kind == "data_file":
                entries.append({
                    "label": f"追加到数据文件 / {_node_path_label(node.id)}",
                    "mode": "append",
                    "node_id": node.id,
                    "data_file_id": node.data_file_id,
                })
    for node in project.tree.nodes:
        if node.kind == "folder" and _node_belongs_to_group(node.id, "datasets"):
            entries.append({
                "label": f"新建数据文件 / {_node_path_label(node.id)}",
                "mode": "create_file",
                "node_id": node.id,
            })
    for option in create_target_options or []:
        entries.append({
            "label": option.label,
            "mode": "create_file",
            "node_id": option.parent_id,
            "resolver": option.ensure_parent_id,
        })
    return entries


def _build_picture_folder_entries() -> List[dict]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return []
    entries: List[dict] = []
    for node in project.tree.nodes:
        if node.kind == "folder" and _node_belongs_to_group(node.id, "pictures"):
            entries.append({
                "label": _node_path_label(node.id),
                "mode": "folder",
                "node_id": node.id,
            })
    return entries


def _build_analysis_result_folder_entries() -> List[dict]:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return []
    entries: List[dict] = []
    for node in project.tree.nodes:
        if node.kind == "folder" and _node_belongs_to_group(node.id, "analysis_result_group"):
            entries.append({
                "label": _node_path_label(node.id),
                "mode": "folder",
                "node_id": node.id,
            })
    return entries


def _node_belongs_to_group(node_id: str, group_type: str) -> bool:
    project = project_manager.current_project
    if project is None or project.tree is None:
        return False
    current = project.tree.get_node(node_id)
    while current is not None:
        if current.kind == "folder":
            canonical = project_manager.canonical_group_type(getattr(current, "group_type", None))
            if canonical is not None:
                return canonical == group_type
        parent_id = getattr(current, "parent_id", None)
        current = project.tree.get_node(parent_id) if parent_id else None
    return False


def _node_path_label(node_id: str) -> str:
    label = project_manager.format_tree_path_label(node_id, separator="/", omit_root_group=True)
    if label and label != node_id:
        return label
    node = project_manager.get_node_by_id(node_id)
    if node is not None:
        fallback_name = (getattr(node, "name", "") or "").strip()
        if fallback_name:
            return fallback_name
    return label or node_id


def _preferred_target_label(entries: List[dict], preferred_node_id: Optional[str]) -> Optional[str]:
    if not preferred_node_id:
        return entries[0]["label"] if entries else None
    matched = next((entry["label"] for entry in entries if entry.get("node_id") == preferred_node_id), None)
    return matched or (entries[0]["label"] if entries else None)


def _ensure_suffix(name: str, suffix: str) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    candidate = Path(value)
    if candidate.suffix.lower() == suffix.lower():
        return value
    if candidate.suffix:
        return candidate.with_suffix(suffix).name
    return f"{value}{suffix}"