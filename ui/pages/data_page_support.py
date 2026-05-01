from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget
from qfluentwidgets import CaptionLabel, MessageBoxBase, PlainTextEdit, SubtitleLabel

from ui.matplotlib_fonts import bootstrap_matplotlib_qtagg

_matplotlib, FigureCanvas, Figure, _MATPLOTLIB_ERROR = bootstrap_matplotlib_qtagg()
HAS_MATPLOTLIB = _matplotlib is not None


# ── 树节点类型常量 ────────────────────────────────────────────
_TYPE_ROOT    = "root"
_TYPE_IMAGE   = "image"
_TYPE_CURVE   = "curve"
_TYPE_DATASET = "dataset"
_TYPE_SERIES  = "series"
_TYPE_ANALYSIS_ROOT = "analysis_root"
_TYPE_ANALYSIS = "analysis"
_SOURCE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
_TEXT_PREVIEW_SUFFIXES = {".csv", ".txt", ".dat", ".tsv", ".json", ".md", ".log", ".py", ".yaml", ".yml", ".ini"}
_TABULAR_PREVIEW_SUFFIXES = {".xlsx", ".xls", ".npy", ".npz"}
_EXTENSION_FIELD_HELP_COMPACT_HEIGHT = 202
_EXTENSION_FIELD_HELP_EXPANDED_HEIGHT = math.ceil(_EXTENSION_FIELD_HELP_COMPACT_HEIGHT * 1.6)
_FOLDER_GROUP_LABELS = {
    "source_files": "源文件",
    "datasets": "数据集",
    "images": "数字化",
    "pictures": "图片集",
    "tools": "工具",
    "pipeline_group": "Pipelines",
    "figure_template_group": "绘图模板",
    "report_template_group": "报告模板",
    "analysis_result_group": "分析结果",
    "ai_group": "AI 工具",
    "prompt_group": "Prompts",
    "skill_group": "Skills",
    "agent_group": "Agents",
}


class _TextActionLabel(CaptionLabel):
    """可点击的文本标签。"""
    clicked = Signal()

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setText(text)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mouseReleaseEvent(self, event) -> None:
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if self.isEnabled() and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class _NodeDetailDialog(MessageBoxBase):
    """节点详情对话框。"""
    def __init__(self, title: str, detail_text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._title_label = SubtitleLabel(title, self.widget)
        self.viewLayout.addWidget(self._title_label)

        self._detail_edit = PlainTextEdit(self.widget)
        self._detail_edit.setReadOnly(True)
        self._detail_edit.setPlainText(detail_text)
        self._detail_edit.setMinimumSize(620, 420)
        self.viewLayout.addWidget(self._detail_edit)

        self.widget.setMinimumWidth(660)
        self.yesButton.setText("关闭")
        self.cancelButton.hide()


@dataclass
class _NodePreviewState:
    source_preview_mode: str = "解析"
    plot_type: str = "折线"
    row_limit: int = 80
    skip_rows: int = 0
    row_offset: int = 0
    selected_sheet: str = ""
    external_browser_dir: str = ""
    last_source_path: str = ""


@dataclass
class _PendingImportQueueState:
    paths: list[str] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)
