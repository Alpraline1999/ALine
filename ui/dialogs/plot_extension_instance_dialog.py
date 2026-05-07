from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, MessageBoxBase, SmoothScrollArea, SubtitleLabel

from core.extension_api import extension_entry_display_info, extension_entry_parameter_help_text, build_extension_entry
from ui.widgets.extension_options_form import ExtensionOptionsForm


class PlotExtensionInstanceEditDialog(MessageBoxBase):
    """编辑已加载绘图扩展实例的对话框。"""

    def __init__(
        self,
        extension: Any,
        applied_instance: Dict[str, Any],
        *,
        line_candidates: Optional[Iterable[str]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._extension_entry = build_extension_entry(extension)
        self._applied_instance = dict(applied_instance or {})

        info = extension_entry_display_info(self._extension_entry, category_label="绘图扩展")
        target_identity = str(self._applied_instance.get("curve_identity") or "").strip()
        target_name = str(self._applied_instance.get("curve_display_name") or "").strip() or str(
            self._applied_instance.get("curve_name") or ""
        ).strip()
        if not target_name:
            target_name = "全部可见曲线"
        target_suffix = "（已失效）" if target_identity and not target_name else ""

        title = SubtitleLabel("编辑已加载扩展实例", self.widget)
        title.setWordWrap(True)
        self.viewLayout.addWidget(title)

        summary = BodyLabel(
            f"{info['name']} · 目标：{target_name}{target_suffix} · 版本：{info['version_label'] or info['type_id'] or '未知'}",
            self.widget,
        )
        summary.setWordWrap(True)
        self.viewLayout.addWidget(summary)

        help_text = extension_entry_parameter_help_text(self._extension_entry)
        if help_text:
            self._help_scroll_area = SmoothScrollArea(self.widget)
            self._help_scroll_area.setWidgetResizable(True)
            self._help_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._help_scroll_area.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")
            self._help_scroll_container = QWidget(self._help_scroll_area)
            help_layout = QVBoxLayout(self._help_scroll_container)
            help_layout.setContentsMargins(0, 0, 0, 0)
            help_layout.setSpacing(0)
            help_label = BodyLabel(help_text, self._help_scroll_container)
            help_label.setWordWrap(True)
            help_layout.addWidget(help_label)
            help_layout.addStretch(1)
            self._help_scroll_area.setWidget(self._help_scroll_container)
            self.viewLayout.addWidget(self._help_scroll_area)
            self.widget.installEventFilter(self)
            self._update_help_area_height()
        else:
            self._help_scroll_area = None
            self._help_scroll_container = None

        self._editor = ExtensionOptionsForm(self.widget)
        self._editor.set_show_field_descriptions(True)
        self._editor.set_line_candidates(list(line_candidates or []))
        fields = [
            dict(item)
            for item in (self._extension_entry.get("normalized_config_fields") or self._extension_entry.get("config_fields") or [])
            if isinstance(item, dict)
        ]
        self._editor.set_fields(fields, dict(self._applied_instance.get("options") or {}), infer_unknown_fields=True)
        self.viewLayout.addWidget(self._editor, 1)

        self.widget.setMinimumWidth(760)
        self.widget.setMinimumHeight(560)
        self.widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.yesButton.setText("刷新加载")
        self.cancelButton.setText("取消")

    def _update_help_area_height(self) -> None:
        if self._help_scroll_area is None:
            return
        height = max(int(self.widget.height() * 0.3), 120)
        self._help_scroll_area.setMinimumHeight(height)
        self._help_scroll_area.setMaximumHeight(height)

    def eventFilter(self, watched, event) -> bool:
        if watched is getattr(self, "widget", None) and event.type() in {QEvent.Type.Show, QEvent.Type.Resize}:
            self._update_help_area_height()
        return super().eventFilter(watched, event)

    def current_options(self) -> Dict[str, Any]:
        return self._editor.current_options()

    def extension_entry(self) -> Dict[str, Any]:
        return dict(self._extension_entry)

    def applied_instance(self) -> Dict[str, Any]:
        return dict(self._applied_instance)
