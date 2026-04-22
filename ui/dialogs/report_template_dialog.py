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

from core.global_assets import global_assets
from core.analysis_engine import render_report, _DEFAULT_REPORT_TEMPLATE, list_report_template_placeholders
from models.schemas import ReportTemplate
from ui.dialogs.fluent_dialogs import TextInputDialog


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
        self._template_ids: list[Optional[str]] = [None]
        self._placeholder_entries = list_report_template_placeholders(self._result)
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

        placeholder_row = QHBoxLayout()
        placeholder_row.addWidget(BodyLabel("占位符:", self))
        self._placeholder_combo = ComboBox(self)
        self._placeholder_combo.currentIndexChanged.connect(self._on_placeholder_changed)
        placeholder_row.addWidget(self._placeholder_combo, 1)
        self._insert_placeholder_btn = PushButton(FIF.ADD, "插入占位符", self)
        self._insert_placeholder_btn.clicked.connect(self._insert_selected_placeholder)
        placeholder_row.addWidget(self._insert_placeholder_btn)
        root.addLayout(placeholder_row)

        self._placeholder_hint = BodyLabel("", self)
        self._placeholder_hint.setWordWrap(True)
        self._placeholder_hint.setStyleSheet("color: #666; font-size: 12px;")
        root.addWidget(self._placeholder_hint)

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

        self._refresh_placeholder_entries()

    def _load_template_list(self):
        self._tmpl_combo.blockSignals(True)
        self._tmpl_combo.clear()
        self._tmpl_combo.addItem("默认模板")
        self._template_ids = [None]
        selected_index = 0
        for idx, tmpl in enumerate(global_assets.list_report_templates(include_builtin=False), start=1):
            self._tmpl_combo.addItem(tmpl.name)
            self._template_ids.append(tmpl.id)
            if self._template_id and tmpl.id == self._template_id:
                selected_index = idx
        self._tmpl_combo.blockSignals(False)
        self._tmpl_combo.setCurrentIndex(selected_index)
        if selected_index == 0:
            self._template_id = None
            self._editor.setPlainText(_DEFAULT_REPORT_TEMPLATE)
        else:
            self._on_template_selected(selected_index)

    def _on_template_selected(self, idx: int):
        if idx == 0:
            self._template_id = None
            self._editor.setPlainText(_DEFAULT_REPORT_TEMPLATE)
            return
        if idx >= len(self._template_ids):
            return
        template_id = self._template_ids[idx]
        template = global_assets.get_report_template(template_id) if template_id else None
        if template is None:
            self._template_id = None
            self._editor.setPlainText(_DEFAULT_REPORT_TEMPLATE)
            return
        self._template_id = template.id
        self._editor.setPlainText(template.content)

    def _selected_placeholder_entry(self) -> Optional[Dict[str, str]]:
        index = self._placeholder_combo.currentIndex()
        if 0 <= index < len(self._placeholder_entries):
            return self._placeholder_entries[index]
        return None

    def _refresh_placeholder_entries(self) -> None:
        current_token = None
        current_entry = self._selected_placeholder_entry() if hasattr(self, "_placeholder_combo") else None
        if current_entry is not None:
            current_token = current_entry.get("token")

        self._placeholder_entries = list_report_template_placeholders(self._result)
        self._placeholder_combo.blockSignals(True)
        self._placeholder_combo.clear()
        for entry in self._placeholder_entries:
            self._placeholder_combo.addItem(f"{entry['label']} · {entry['token']}")
        if self._placeholder_entries:
            target_index = next(
                (index for index, entry in enumerate(self._placeholder_entries) if entry.get("token") == current_token),
                0,
            )
            self._placeholder_combo.setCurrentIndex(target_index)
        self._placeholder_combo.blockSignals(False)
        self._on_placeholder_changed(self._placeholder_combo.currentIndex())

    def _on_placeholder_changed(self, _idx: int) -> None:
        entry = self._selected_placeholder_entry()
        if entry is None:
            self._placeholder_hint.setText("")
            return
        self._placeholder_hint.setText(f"{entry['token']}：{entry['description']}")

    def _insert_selected_placeholder(self) -> None:
        entry = self._selected_placeholder_entry()
        if entry is None:
            return
        self._editor.insertPlainText(entry["token"])
        self._editor.setFocus()

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
        current_name = ""
        current_template = global_assets.get_report_template(self._template_id) if self._template_id else None
        if current_template is not None:
            current_name = current_template.name
        name, ok = TextInputDialog.get_text(
            self,
            "保存报告模板",
            "模板名称:",
            placeholder="输入模板名称",
            text=current_name,
        )
        if not ok or not name.strip():
            return
        clean_name = name.strip()
        if clean_name == "默认模板":
            InfoBar.warning("提示", "默认模板为内置模板，请使用其他名称保存副本", parent=self,
                            position=InfoBarPosition.TOP, duration=2500)
            return
        content = self._editor.toPlainText()
        target = current_template
        if target is None:
            target = next((item for item in global_assets.list_report_templates(include_builtin=False) if item.name == clean_name), None)
        if target is not None:
            global_assets.update_report_template(target.id, name=clean_name, content=content)
            self._template_id = target.id
        else:
            saved = global_assets.add_report_template(ReportTemplate(name=clean_name, content=content))
            self._template_id = saved.id
        self._load_template_list()
        InfoBar.success("已保存", f"模板「{clean_name}」已保存", parent=self,
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
