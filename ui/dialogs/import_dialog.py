"""数据导入对话框 — 3步列选择向导"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QSizePolicy, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, ComboBox, InfoBar, InfoBarPosition,
    LineEdit, PrimaryPushButton, PushButton, SubtitleLabel,
)

from models.schemas import DataSeries

_ROLES = ["X 轴", "Y 轴", "Y 误差棒", "X 误差棒", "跳过"]


class ImportDialog(QDialog):
    """文件导入向导 — 三步流程：选文件 → 列角色 → 确认。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入数据文件")
        self.setMinimumSize(600, 480)
        self.imported_series: List[DataSeries] = []

        self._file_path: str = ""
        self._raw_headers: List[str] = []
        self._raw_rows: List[List[float]] = []  # 全量数据行

        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(12)

        # 步骤指示器
        self._step_label = BodyLabel("步骤 1 / 3：选择文件", self)
        root.addWidget(self._step_label)

        # 页面栈
        self._stack = QStackedWidget(self)
        root.addWidget(self._stack, 1)

        self._page1 = self._build_page1()
        self._page2 = self._build_page2()
        self._page3 = self._build_page3()
        self._stack.addWidget(self._page1)
        self._stack.addWidget(self._page2)
        self._stack.addWidget(self._page3)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_back = PushButton("上一步", self)
        self._btn_back.setEnabled(False)
        self._btn_back.clicked.connect(self._go_back)
        btn_row.addWidget(self._btn_back)
        self._btn_next = PrimaryPushButton("下一步", self)
        self._btn_next.setEnabled(False)
        self._btn_next.clicked.connect(self._go_next)
        btn_row.addWidget(self._btn_next)
        self._btn_cancel = PushButton("取消", self)
        self._btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_cancel)
        root.addLayout(btn_row)

    # ── Step 1 ──────────────────────────────────────────────────────────

    def _build_page1(self) -> QWidget:
        w = QWidget(self)
        lv = QVBoxLayout(w)
        lv.setSpacing(12)

        lv.addWidget(SubtitleLabel("选择数据文件", w))

        row = QHBoxLayout()
        self._path_edit = LineEdit(w)
        self._path_edit.setReadOnly(True)
        self._path_edit.setPlaceholderText("CSV / Excel / JSON / NumPy 文件…")
        self._path_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        browse_btn = PushButton("浏览…", w)
        browse_btn.clicked.connect(self._browse)
        row.addWidget(self._path_edit)
        row.addWidget(browse_btn)
        lv.addLayout(row)

        self._p1_info = BodyLabel("", w)
        self._p1_info.setWordWrap(True)
        lv.addWidget(self._p1_info)
        lv.addStretch()
        return w

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择数据文件", "",
            "数据文件 (*.csv *.txt *.dat *.tsv *.xlsx *.xls *.json *.npy *.npz);;所有文件 (*)",
        )
        if not path:
            return
        self._file_path = path
        self._path_edit.setText(path)
        try:
            headers, rows = _parse_file_preview(path)
            self._raw_headers = headers
            self._raw_rows = rows
            n_rows = len(rows)
            n_cols = len(headers)
            self._p1_info.setText(f"✓ 检测到 {n_cols} 列，{n_rows} 行数据")
            self._btn_next.setEnabled(True)
        except Exception as e:
            self._p1_info.setText(f"⚠ 读取失败：{e}")
            self._btn_next.setEnabled(False)

    # ── Step 2 ──────────────────────────────────────────────────────────

    def _build_page2(self) -> QWidget:
        w = QWidget(self)
        lv = QVBoxLayout(w)
        lv.setSpacing(8)

        lv.addWidget(SubtitleLabel("分配列角色", w))
        lv.addWidget(BodyLabel("为每一列选择导入角色（X轴/Y轴/误差棒/跳过）", w))

        self._col_table = QTableWidget(w)
        self._col_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._col_table.verticalHeader().setVisible(False)
        self._col_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        lv.addWidget(self._col_table, 1)

        name_row = QHBoxLayout()
        name_row.addWidget(BodyLabel("系列名称前缀:", w))
        self._series_prefix = LineEdit(w)
        self._series_prefix.setPlaceholderText("留空则使用文件名")
        name_row.addWidget(self._series_prefix, 1)
        lv.addLayout(name_row)
        return w

    def _populate_col_table(self):
        """用当前文件数据填充列角色选择表格。"""
        if not self._raw_headers:
            return
        n_cols = len(self._raw_headers)
        preview_rows = self._raw_rows[:8]  # 显示前8行

        # 行数 = 1(角色选择) + 1(列名) + len(preview_rows)
        self._col_table.setRowCount(2 + len(preview_rows))
        self._col_table.setColumnCount(n_cols)

        # 第0行：角色下拉框
        self._role_combos: List[ComboBox] = []
        for c in range(n_cols):
            combo = ComboBox(self)
            combo.addItems(_ROLES)
            # 默认：第0列 → X轴，其余 → Y轴
            default_idx = 0 if c == 0 else 1
            combo.setCurrentIndex(default_idx)
            self._col_table.setCellWidget(0, c, combo)
            self._role_combos.append(combo)

        # 第1行：列名
        for c, name in enumerate(self._raw_headers):
            item = QTableWidgetItem(name)
            item.setTextAlignment(Qt.AlignCenter)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            self._col_table.setItem(1, c, item)

        # 数据预览行
        for r, row in enumerate(preview_rows):
            for c, val in enumerate(row):
                txt = f"{val:.6g}"
                it = QTableWidgetItem(txt)
                it.setTextAlignment(Qt.AlignCenter)
                self._col_table.setItem(2 + r, c, it)

        # 行高
        self._col_table.setRowHeight(0, 36)

    # ── Step 3 ──────────────────────────────────────────────────────────

    def _build_page3(self) -> QWidget:
        w = QWidget(self)
        lv = QVBoxLayout(w)
        lv.setSpacing(8)
        lv.addWidget(SubtitleLabel("确认导入", w))
        self._p3_summary = BodyLabel("", w)
        self._p3_summary.setWordWrap(True)
        lv.addWidget(self._p3_summary)
        lv.addStretch()
        return w

    # ── 导航 ─────────────────────────────────────────────────────────────

    def _go_next(self):
        cur = self._stack.currentIndex()
        if cur == 0:
            # Step1 → Step2: populate col table
            self._populate_col_table()
            self._stack.setCurrentIndex(1)
            self._step_label.setText("步骤 2 / 3：分配列角色")
            self._btn_back.setEnabled(True)
            self._btn_next.setText("导入")
        elif cur == 1:
            # Step2 → 执行导入 → Step3
            try:
                self.imported_series = self._do_import()
            except Exception as e:
                InfoBar.error(
                    title="导入失败", content=str(e),
                    position=InfoBarPosition.TOP, duration=4000, parent=self,
                )
                return
            summary = f"✓ 成功导入 {len(self.imported_series)} 条数据系列：\n"
            summary += "\n".join(f"  • {s.name} ({len(s.x)} 点)" for s in self.imported_series[:8])
            if len(self.imported_series) > 8:
                summary += f"\n  ... 共 {len(self.imported_series)} 条"
            self._p3_summary.setText(summary)
            self._stack.setCurrentIndex(2)
            self._step_label.setText("步骤 3 / 3：完成")
            self._btn_next.setText("完成")
            self._btn_next.clicked.disconnect()
            self._btn_next.clicked.connect(self.accept)

    def _go_back(self):
        cur = self._stack.currentIndex()
        if cur == 1:
            self._stack.setCurrentIndex(0)
            self._step_label.setText("步骤 1 / 3：选择文件")
            self._btn_back.setEnabled(False)
            self._btn_next.setText("下一步")

    # ── 导入逻辑 ─────────────────────────────────────────────────────────

    def _do_import(self) -> List[DataSeries]:
        if not self._raw_rows or not self._raw_headers:
            raise ValueError("没有可用的数据")

        roles = [combo.currentText() for combo in self._role_combos]
        prefix = self._series_prefix.text().strip() or Path(self._file_path).stem

        x_cols = [i for i, r in enumerate(roles) if r == "X 轴"]
        y_cols = [i for i, r in enumerate(roles) if r == "Y 轴"]
        ye_cols = [i for i, r in enumerate(roles) if r == "Y 误差棒"]
        xe_cols = [i for i, r in enumerate(roles) if r == "X 误差棒"]

        if not x_cols:
            raise ValueError("至少需要指定一列作为 X 轴")
        if not y_cols:
            raise ValueError("至少需要指定一列作为 Y 轴")

        x_idx = x_cols[0]  # 取第一个 X 轴列
        arr = np.array(self._raw_rows, dtype=float)
        x_data = arr[:, x_idx].tolist()

        series_list: List[DataSeries] = []
        for y_idx in y_cols:
            y_data = arr[:, y_idx].tolist()
            col_name = self._raw_headers[y_idx] if y_idx < len(self._raw_headers) else f"col_{y_idx}"
            s_name = f"{prefix} / {col_name}" if prefix else col_name

            # 匹配 Y 误差棒（按照 y_cols 顺序对应 ye_cols）
            y_pos = y_cols.index(y_idx)
            y_err = None
            if ye_cols and y_pos < len(ye_cols):
                y_err = arr[:, ye_cols[y_pos]].tolist()

            series_list.append(DataSeries(
                name=s_name,
                x=x_data,
                y=y_data,
                y_err=y_err,
                x_label=self._raw_headers[x_idx] if x_idx < len(self._raw_headers) else "x",
                y_label=col_name,
                source="imported_file",
            ))

        return series_list

    def get_results(self) -> List[DataSeries]:
        return self.imported_series


# ─────────────────────── 文件解析工具 ──────────────────────────────────

def _parse_file_preview(file_path: str):
    """解析文件，返回 (headers: List[str], rows: List[List[float]])。"""
    suffix = Path(file_path).suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return _parse_excel(file_path)
    if suffix == ".json":
        return _parse_json(file_path)
    if suffix in (".npy", ".npz"):
        return _parse_npy(file_path)
    return _parse_csv(file_path)


def _parse_csv(file_path: str):
    raw_lines: List[str] = []
    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            with open(file_path, encoding=enc, newline="") as f:
                raw_lines = f.readlines()
            break
        except UnicodeDecodeError:
            continue
    data_lines = [l.rstrip("\r\n") for l in raw_lines
                  if l.strip() and not l.lstrip().startswith(("#", "%", "!", "/"))]
    if not data_lines:
        raise ValueError("文件为空")

    sep = "\t" if "\t" in "\n".join(data_lines[:5]) else (
        "," if data_lines[0].count(",") >= data_lines[0].count(";") else ";"
        if ";" in data_lines[0] else None
    )

    def split(line):
        if sep is None:
            return re.split(r"\s+", line.strip())
        return line.split(sep)

    headers: Optional[List[str]] = None
    start = 0
    first = split(data_lines[0])
    try:
        [float(v.strip()) for v in first if v.strip()]
    except ValueError:
        headers = [v.strip().strip('"\'') for v in first]
        start = 1

    rows: List[List[float]] = []
    for line in data_lines[start:]:
        parts = split(line)
        try:
            row = [float(v) for v in parts if v.strip()]
            if row:
                rows.append(row)
        except ValueError:
            continue
    if not rows:
        raise ValueError("未找到数值数据")

    ncols = max(set(len(r) for r in rows), key=lambda c: sum(1 for r in rows if len(r) == c))
    rows = [r for r in rows if len(r) == ncols]
    if headers is None or len(headers) != ncols:
        headers = [f"col_{i}" for i in range(ncols)]
    return headers, rows


def _parse_excel(file_path: str):
    import openpyxl
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active
    raw = list(ws.iter_rows(values_only=True))
    wb.close()
    if not raw:
        raise ValueError("Excel 工作表为空")
    first = raw[0]
    try:
        [float(v) for v in first if v is not None]
        headers = [f"col_{i}" for i in range(len(first))]
        data_rows = raw
    except (ValueError, TypeError):
        headers = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(first)]
        data_rows = raw[1:]

    rows: List[List[float]] = []
    for row in data_rows:
        try:
            r = [float(v) for v in row if v is not None]
            if r:
                rows.append(r)
        except (ValueError, TypeError):
            continue
    if not rows:
        raise ValueError("Excel 中无数值数据")
    ncols = max(set(len(r) for r in rows), key=lambda c: sum(1 for r in rows if len(r) == c))
    rows = [r for r in rows if len(r) == ncols]
    if len(headers) != ncols:
        headers = [f"col_{i}" for i in range(ncols)]
    return headers, rows


def _parse_json(file_path: str):
    import json
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        # {x:[...], y:[...]} 格式
        keys = list(data.keys())
        rows = list(zip(*[data[k] for k in keys]))
        rows_f = [[float(v) for v in row] for row in rows]
        return keys, rows_f
    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys = list(data[0].keys())
        rows_f = []
        for item in data:
            try:
                rows_f.append([float(item.get(k, float("nan"))) for k in keys])
            except Exception:
                continue
        return keys, rows_f
    raise ValueError("无法识别 JSON 结构")


def _parse_npy(file_path: str):
    arr = np.load(file_path, allow_pickle=False)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2:
        raise ValueError("NumPy 数组应为 1D 或 2D")
    headers = [f"col_{i}" for i in range(arr.shape[1])]
    rows = arr.tolist()
    return headers, rows
