"""报告模板对话框 — Markdown 模板编辑 + 预览 + 导出"""
from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QSplitter, QVBoxLayout, QWidget,
)
from qfluentwidgets import (
    BodyLabel, ComboBox, FluentIcon as FIF,
    InfoBar, InfoBarPosition,
    PlainTextEdit, PrimaryPushButton, PushButton, SubtitleLabel,
)
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _HAS_WEB = True
except ImportError:
    _HAS_WEB = False

from core.project_manager import project_manager
from core.analysis_engine import render_report, _DEFAULT_REPORT_TEMPLATE


class ReportTemplateDialog(QDialog):
    """Markdown 报告模板编辑/渲染/导出对话框。"""

    def __init__(
        self,
        parent=None,
        result: Optional[Dict[str, Any]] = None,
        template_id: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("生成分析报告")
        self.setMinimumSize(800, 560)
        self._result = result or {}
        self._template_id = template_id
        self._setup_ui()
        self._load_template_list()
        self._on_preview()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # 顶部：模板选择
        top_row = QHBoxLayout()
        top_row.addWidget(BodyLabel("模板:", self))
        self._tmpl_combo = ComboBox(self)
        self._tmpl_combo.currentIndexChanged.connect(self._on_template_selected)
        top_row.addWidget(self._tmpl_combo, 1)
        btn_save_tmpl = PushButton(FIF.SAVE, "保存为模板", self)
        btn_save_tmpl.clicked.connect(self._on_save_template)
        top_row.addWidget(btn_save_tmpl)
        root.addLayout(top_row)

        # 主区域：左编辑器 | 右预览
        splitter = QSplitter(Qt.Horizontal, self)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(SubtitleLabel("模板编辑器", left))
        self._editor = PlainTextEdit(left)
        self._editor.setPlaceholderText("在此输入 Markdown 模板…")
        self._editor.textChanged.connect(self._on_preview)
        lv.addWidget(self._editor, 1)
        splitter.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(SubtitleLabel("预览", right))
        if _HAS_WEB:
            self._preview = QWebEngineView(right)
            rv.addWidget(self._preview, 1)
        else:
            # Fallback: plain text preview
            self._preview = PlainTextEdit(right)
            self._preview.setReadOnly(True)
            rv.addWidget(self._preview, 1)
        splitter.addWidget(right)
        splitter.setSizes([400, 400])
        root.addWidget(splitter, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_preview = PushButton(FIF.SYNC, "刷新预览", self)
        btn_preview.clicked.connect(self._on_preview)
        btn_row.addWidget(btn_preview)
        btn_export = PrimaryPushButton(FIF.SHARE, "导出 .md", self)
        btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(btn_export)
        btn_close = PushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def _load_template_list(self):
        self._tmpl_combo.blockSignals(True)
        self._tmpl_combo.clear()
        self._tmpl_combo.addItem("默认模板")
        p = project_manager.current_project
        selected_index = 0
        if p:
            for idx, tmpl in enumerate(p.report_templates, start=1):
                self._tmpl_combo.addItem(tmpl.name)
                if self._template_id and tmpl.id == self._template_id:
                    selected_index = idx
        self._tmpl_combo.blockSignals(False)
        self._tmpl_combo.setCurrentIndex(selected_index)
        if selected_index == 0:
            self._editor.setPlainText(_DEFAULT_REPORT_TEMPLATE)
        else:
            self._on_template_selected(selected_index)

    def _on_template_selected(self, idx: int):
        if idx == 0:
            self._editor.setPlainText(_DEFAULT_REPORT_TEMPLATE)
            return
        p = project_manager.current_project
        if p and idx - 1 < len(p.report_templates):
            self._editor.setPlainText(p.report_templates[idx - 1].content)

    def _on_preview(self):
        content = self._editor.toPlainText()
        rendered = render_report(content, self._result)

        if _HAS_WEB:
            try:
                import markdown
                html_body = markdown.markdown(rendered, extensions=["tables", "fenced_code"])
            except ImportError:
                # Fallback: wrap in <pre>
                import html as html_lib
                html_body = f"<pre>{html_lib.escape(rendered)}</pre>"
            html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; font-size: 14px; margin: 16px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 12px; text-align: left; }}
  th {{ background: #f0f0f0; }}
  pre {{ background: #f8f8f8; padding: 10px; border-radius: 4px; }}
  code {{ font-family: monospace; }}
</style></head>
<body>{html_body}</body></html>"""
            self._preview.setHtml(html)
        else:
            self._preview.setPlainText(rendered)

    def _on_save_template(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "保存报告模板", "模板名称:")
        if not ok or not name.strip():
            return
        p = project_manager.current_project
        if p is None:
            return
        content = self._editor.toPlainText()
        existing = next((t for t in p.report_templates if t.name == name.strip()), None)
        if existing:
            existing.content = content
            p.is_modified = True
        else:
            project_manager.add_report_template(name.strip(), content)
        self._load_template_list()
        InfoBar.success("已保存", f"模板「{name}」已保存", parent=self,
                        position=InfoBarPosition.TOP, duration=2500)

    def _on_export(self):
        content = self._editor.toPlainText()
        rendered = render_report(content, self._result)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出报告", "analysis_report.md", "Markdown (*.md);;所有文件 (*)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(rendered)
            InfoBar.success("导出成功", path, parent=self,
                            position=InfoBarPosition.TOP, duration=3000)
