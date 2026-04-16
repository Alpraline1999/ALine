"""高级绘图设置对话框"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, CheckBox, ComboBox, FluentIcon as FIF,
    LineEdit, PrimaryPushButton, PushButton, SubtitleLabel,
)


class AdvancedFigureDialog(QDialog):
    """高级绘图设置弹窗 — 坐标轴/图例/主题/尺寸。"""

    def __init__(self, parent: Optional[QWidget] = None, current_config: Optional[dict] = None):
        super().__init__(parent)
        self.setWindowTitle("高级绘图设置")
        self.setMinimumWidth(400)
        self._cfg = dict(current_config or {})
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(SubtitleLabel("坐标轴", self))

        grid = QGridLayout()
        grid.setSpacing(8)

        # X 轴范围
        grid.addWidget(BodyLabel("X 范围 最小:", self), 0, 0)
        self._x_min = LineEdit(self)
        self._x_min.setPlaceholderText("自动")
        self._x_min.setText(str(self._cfg.get("x_min", "")))
        grid.addWidget(self._x_min, 0, 1)
        grid.addWidget(BodyLabel("最大:", self), 0, 2)
        self._x_max = LineEdit(self)
        self._x_max.setPlaceholderText("自动")
        self._x_max.setText(str(self._cfg.get("x_max", "")))
        grid.addWidget(self._x_max, 0, 3)

        # Y 轴范围
        grid.addWidget(BodyLabel("Y 范围 最小:", self), 1, 0)
        self._y_min = LineEdit(self)
        self._y_min.setPlaceholderText("自动")
        self._y_min.setText(str(self._cfg.get("y_min", "")))
        grid.addWidget(self._y_min, 1, 1)
        grid.addWidget(BodyLabel("最大:", self), 1, 2)
        self._y_max = LineEdit(self)
        self._y_max.setPlaceholderText("自动")
        self._y_max.setText(str(self._cfg.get("y_max", "")))
        grid.addWidget(self._y_max, 1, 3)

        # X 轴标签
        grid.addWidget(BodyLabel("X 轴标签:", self), 2, 0)
        self._x_label = LineEdit(self)
        self._x_label.setPlaceholderText("X")
        self._x_label.setText(self._cfg.get("x_label", ""))
        grid.addWidget(self._x_label, 2, 1, 1, 3)

        # Y 轴标签
        grid.addWidget(BodyLabel("Y 轴标签:", self), 3, 0)
        self._y_label = LineEdit(self)
        self._y_label.setPlaceholderText("Y")
        self._y_label.setText(self._cfg.get("y_label", ""))
        grid.addWidget(self._y_label, 3, 1, 1, 3)

        layout.addLayout(grid)

        # 对数坐标 + 双 Y 轴
        log_row = QHBoxLayout()
        self._x_log = CheckBox("X 对数坐标", self)
        self._x_log.setChecked(bool(self._cfg.get("x_log", False)))
        log_row.addWidget(self._x_log)
        self._y_log = CheckBox("Y 对数坐标", self)
        self._y_log.setChecked(bool(self._cfg.get("y_log", False)))
        log_row.addWidget(self._y_log)
        self._grid_cb = CheckBox("显示网格", self)
        self._grid_cb.setChecked(bool(self._cfg.get("grid", True)))
        log_row.addWidget(self._grid_cb)
        log_row.addStretch()
        layout.addLayout(log_row)

        # 图例位置
        legend_row = QHBoxLayout()
        legend_row.addWidget(BodyLabel("图例位置:", self))
        self._legend_pos = ComboBox(self)
        self._legend_pos.addItems([
            "best", "upper right", "upper left", "lower left", "lower right",
            "right", "center left", "center right", "lower center", "upper center", "center",
        ])
        cur_pos = self._cfg.get("legend_pos", "best")
        idx = self._legend_pos.findText(cur_pos)
        if idx >= 0:
            self._legend_pos.setCurrentIndex(idx)
        legend_row.addWidget(self._legend_pos, 1)
        layout.addLayout(legend_row)

        # 字体大小
        font_row = QHBoxLayout()
        font_row.addWidget(BodyLabel("字体大小:", self))
        self._font_size = LineEdit(self)
        self._font_size.setPlaceholderText("10")
        self._font_size.setText(str(self._cfg.get("font_size", 10)))
        self._font_size.setFixedWidth(60)
        font_row.addWidget(self._font_size)
        font_row.addStretch()
        layout.addLayout(font_row)

        # 主题
        theme_row = QHBoxLayout()
        theme_row.addWidget(BodyLabel("图表主题:", self))
        self._theme = ComboBox(self)
        self._theme.addItems(["默认", "Nature", "IEEE", "ACS", "简洁黑白"])
        cur_theme = self._cfg.get("theme", "默认")
        t_idx = self._theme.findText(cur_theme)
        if t_idx >= 0:
            self._theme.setCurrentIndex(t_idx)
        theme_row.addWidget(self._theme, 1)
        layout.addLayout(theme_row)

        # 误差棒
        self._errbar = CheckBox("显示误差棒", self)
        self._errbar.setChecked(bool(self._cfg.get("show_errbar", False)))
        layout.addWidget(self._errbar)

        layout.addStretch()

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = PushButton("取消", self)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = PrimaryPushButton("确定", self)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def get_config(self) -> dict:
        return {
            "x_min": self._x_min.text().strip() or None,
            "x_max": self._x_max.text().strip() or None,
            "y_min": self._y_min.text().strip() or None,
            "y_max": self._y_max.text().strip() or None,
            "x_label": self._x_label.text().strip(),
            "y_label": self._y_label.text().strip(),
            "x_log": self._x_log.isChecked(),
            "y_log": self._y_log.isChecked(),
            "grid": self._grid_cb.isChecked(),
            "legend_pos": self._legend_pos.currentText(),
            "font_size": _safe_int(self._font_size.text(), 10),
            "theme": self._theme.currentText(),
            "show_errbar": self._errbar.isChecked(),
        }


def _safe_int(v: str, default: int) -> int:
    try:
        return int(v.strip())
    except Exception:
        return default
