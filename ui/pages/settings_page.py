from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QFrame, QFormLayout, QKeySequenceEdit)
from PySide6.QtCore import Qt, QTimer, Signal
from qfluentwidgets import (ComboBox, setTheme, Theme, CardWidget, PushButton,
    BodyLabel, SubtitleLabel, TitleLabel, SmoothScrollArea,
    LineEdit, PrimaryPushButton, InfoBar, InfoBarPosition)

from ui.theme import text_color, secondary_color, placeholder_color
from core.shortcut_manager import shortcut_manager


class SettingsPage(QWidget):
    """设置页面 - 主题切换、快捷键自定义等配置"""

    shortcuts_changed = Signal()  # 快捷键保存后发出

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title_label = None
        self._theme_label = None
        self._appearance_title = None
        self._lang_title = None
        self._lang_placeholder = None
        self._shortcuts_title = None
        self._appearance_card = None
        self._lang_card = None
        self._shortcuts_card = None
        self.theme_combo = None
        self._shortcut_edits: dict[str, QKeySequenceEdit] = {}
        self._shortcut_labels: list[BodyLabel] = []
        self._conflict_labels: dict[str, BodyLabel] = {}  # action -> red warning label
        self.setup_ui()

    def setup_ui(self):
        outer = SmoothScrollArea(self)
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)
        outer.setWidget(content)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(outer)

        # 标题
        self._title_label = BodyLabel("设置", content)
        self._title_label.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {text_color()};")
        layout.addWidget(self._title_label)

        # ── 外观设置 ──
        self._appearance_card = CardWidget(content)
        appearance_layout = QVBoxLayout(self._appearance_card)

        self._appearance_title = BodyLabel("外观", self._appearance_card)
        self._appearance_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {text_color()};")
        appearance_layout.addWidget(self._appearance_title)

        theme_layout = QVBoxLayout()
        self._theme_label = BodyLabel("主题", content)
        self._theme_label.setStyleSheet(f"color: {text_color()};")
        theme_layout.addWidget(self._theme_label)

        self.theme_combo = ComboBox(content)
        self.theme_combo.addItems(["浅色", "深色", "跟随系统"])
        self.theme_combo.setCurrentIndex(2)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        theme_layout.addWidget(self.theme_combo)

        appearance_layout.addLayout(theme_layout)
        layout.addWidget(self._appearance_card)

        # ── 语言设置（预留）──
        self._lang_card = CardWidget(content)
        lang_layout = QVBoxLayout(self._lang_card)

        self._lang_title = BodyLabel("语言", self._lang_card)
        self._lang_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {text_color()};")
        lang_layout.addWidget(self._lang_title)

        self._lang_placeholder = BodyLabel("语言设置（预留）", content)
        self._lang_placeholder.setStyleSheet(f"color: {placeholder_color()}; font-style: italic;")
        lang_layout.addWidget(self._lang_placeholder)

        layout.addWidget(self._lang_card)
        self._lang_card.hide()  # 暂不实现语言设置

        # ── 快捷键自定义 ──
        self._shortcuts_card = CardWidget(content)
        shortcuts_layout = QVBoxLayout(self._shortcuts_card)

        self._shortcuts_title = BodyLabel("快捷键", self._shortcuts_card)
        self._shortcuts_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {text_color()};")
        shortcuts_layout.addWidget(self._shortcuts_title)

        hint = BodyLabel("点击输入框后按下新快捷键即可修改。按 → 应用快捷键 保存。", self._shortcuts_card)
        hint.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
        hint.setWordWrap(True)
        shortcuts_layout.addWidget(hint)

        sc_content = QWidget(self._shortcuts_card)
        sc_form = QFormLayout(sc_content)
        sc_form.setSpacing(6)
        sc_form.setContentsMargins(0, 4, 0, 4)

        for action, label in shortcut_manager.LABELS.items():
            from ui.theme import card_background_color, border_color
            edit = QKeySequenceEdit(sc_content)
            from PySide6.QtGui import QKeySequence
            edit.setKeySequence(QKeySequence(shortcut_manager.get(action)))
            edit.setStyleSheet(
                f"background: {card_background_color()}; color: {text_color()};"
                f" border: 1px solid {border_color()}; border-radius: 4px; padding: 3px;"
            )
            row_lbl = BodyLabel(label + ":", sc_content)
            row_lbl.setStyleSheet(f"color: {text_color()};")

            # 冲突提示标签
            conflict_lbl = BodyLabel("", sc_content)
            conflict_lbl.setStyleSheet("color: #e81123; font-size: 10px;")
            conflict_lbl.setVisible(False)

            # 垂直堆叠 edit + conflict_lbl
            edit_col = QWidget(sc_content)
            ecol_layout = QVBoxLayout(edit_col)
            ecol_layout.setContentsMargins(0, 0, 0, 0)
            ecol_layout.setSpacing(1)
            ecol_layout.addWidget(edit)
            ecol_layout.addWidget(conflict_lbl)

            sc_form.addRow(row_lbl, edit_col)
            self._shortcut_edits[action] = edit
            self._shortcut_labels.append(row_lbl)
            self._conflict_labels[action] = conflict_lbl
            edit.keySequenceChanged.connect(lambda ks, a=action: self._check_shortcut_conflict(a, ks))

        shortcuts_layout.addWidget(sc_content)

        btn_row = QHBoxLayout()
        apply_btn = PushButton("应用快捷键", self._shortcuts_card)
        apply_btn.clicked.connect(self._on_apply_shortcuts)
        reset_btn = PushButton("恢复默认", self._shortcuts_card)
        reset_btn.clicked.connect(self._on_reset_shortcuts)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        shortcuts_layout.addLayout(btn_row)

        layout.addWidget(self._shortcuts_card)

        # ── AI 接口配置 ──
        self._ai_card = CardWidget(content)
        ai_layout = QVBoxLayout(self._ai_card)

        ai_title = BodyLabel("AI 接口", self._ai_card)
        ai_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {text_color()};")
        ai_layout.addWidget(ai_title)

        form = QFormLayout()
        form.setSpacing(8)

        self._ai_provider_combo = ComboBox(self._ai_card)
        self._ai_provider_combo.addItems(["OpenAI 兼容 API", "Ollama"])
        self._ai_provider_combo.currentIndexChanged.connect(self._on_ai_provider_changed)
        form.addRow("接口类型:", self._ai_provider_combo)

        self._ai_url_edit = LineEdit(self._ai_card)
        self._ai_url_edit.setPlaceholderText("https://api.openai.com/v1")
        form.addRow("API 地址:", self._ai_url_edit)

        self._ai_key_edit = LineEdit(self._ai_card)
        self._ai_key_edit.setPlaceholderText("sk-...")
        form.addRow("API Key:", self._ai_key_edit)

        self._ai_model_edit = LineEdit(self._ai_card)
        self._ai_model_edit.setPlaceholderText("gpt-4o-mini")
        form.addRow("模型名称:", self._ai_model_edit)

        self._ai_timeout_edit = LineEdit(self._ai_card)
        self._ai_timeout_edit.setPlaceholderText("60")
        form.addRow("超时(秒):", self._ai_timeout_edit)

        self._ai_temperature_edit = LineEdit(self._ai_card)
        self._ai_temperature_edit.setPlaceholderText("0.7")
        form.addRow("Temperature:", self._ai_temperature_edit)

        self._ai_max_tokens_edit = LineEdit(self._ai_card)
        self._ai_max_tokens_edit.setPlaceholderText("2048")
        form.addRow("Max Tokens:", self._ai_max_tokens_edit)

        ai_layout.addLayout(form)

        ai_btn_row = QHBoxLayout()
        save_ai_btn = PrimaryPushButton("保存配置")
        save_ai_btn.clicked.connect(self._save_ai_config)
        test_ai_btn = PushButton("测试连接")
        test_ai_btn.clicked.connect(self._test_ai_connection)
        ai_btn_row.addWidget(save_ai_btn)
        ai_btn_row.addWidget(test_ai_btn)
        ai_btn_row.addStretch()
        ai_layout.addLayout(ai_btn_row)

        layout.addWidget(self._ai_card)

        # ── 报告模板管理 ──
        self._tmpl_card = CardWidget(content)
        tmpl_layout = QVBoxLayout(self._tmpl_card)

        tmpl_title = BodyLabel("报告模板", self._tmpl_card)
        tmpl_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {text_color()};")
        tmpl_layout.addWidget(tmpl_title)

        from qfluentwidgets import ListWidget as _ListWidget
        self._tmpl_list = _ListWidget(self._tmpl_card)
        self._tmpl_list.setMaximumHeight(160)
        tmpl_layout.addWidget(self._tmpl_list)

        tmpl_btn_row = QHBoxLayout()
        from qfluentwidgets import FluentIcon as FIF_
        new_tmpl_btn = PushButton("新建")
        new_tmpl_btn.clicked.connect(self._on_new_template)
        edit_tmpl_btn = PushButton("编辑")
        edit_tmpl_btn.clicked.connect(self._on_edit_template)
        del_tmpl_btn = PushButton("删除")
        del_tmpl_btn.clicked.connect(self._on_delete_template)
        tmpl_btn_row.addWidget(new_tmpl_btn)
        tmpl_btn_row.addWidget(edit_tmpl_btn)
        tmpl_btn_row.addWidget(del_tmpl_btn)
        tmpl_btn_row.addStretch()
        tmpl_layout.addLayout(tmpl_btn_row)

        layout.addWidget(self._tmpl_card)

        layout.addStretch()

        # 加载 AI 配置
        self._load_ai_config()

    def _on_apply_shortcuts(self):
        """保存用户修改的快捷键"""
        mapping = {}
        for action, edit in self._shortcut_edits.items():
            mapping[action] = edit.keySequence().toString()
        shortcut_manager.apply_all(mapping)
        self.shortcuts_changed.emit()

    def _check_shortcut_conflict(self, changed_action: str, ks):
        """实时检测快捷键冲突"""
        ks_str = ks.toString() if not isinstance(ks, str) else ks
        # 清空所有冲突提示
        for a, lbl in self._conflict_labels.items():
            lbl.setVisible(False)
        if not ks_str:
            return
        # 找所有与此序列重复的 action
        conflicts = []
        for a, edit in self._shortcut_edits.items():
            if a != changed_action and edit.keySequence().toString() == ks_str:
                conflicts.append(a)
        if conflicts:
            from core.shortcut_manager import shortcut_manager as sm
            conflict_names = " / ".join(sm.LABELS.get(a, a) for a in conflicts)
            self._conflict_labels[changed_action].setText(f"与「{conflict_names}」冲突")
            self._conflict_labels[changed_action].setVisible(True)
            for a in conflicts:
                if a in self._conflict_labels:
                    cur_ks = self._shortcut_edits[changed_action].keySequence().toString()
                    changed_name = sm.LABELS.get(changed_action, changed_action)
                    self._conflict_labels[a].setText(f"与「{changed_name}」冲突")
                    self._conflict_labels[a].setVisible(True)

    def _on_reset_shortcuts(self):
        """恢复所有快捷键为默认值"""
        shortcut_manager.reset_to_defaults()
        from PySide6.QtGui import QKeySequence
        for action, edit in self._shortcut_edits.items():
            edit.setKeySequence(QKeySequence(shortcut_manager.get(action)))
        self.shortcuts_changed.emit()

    def on_theme_changed(self, index):
        themes = [Theme.LIGHT, Theme.DARK, Theme.AUTO]
        setTheme(themes[index])
        QTimer.singleShot(50, self._update_colors)

    def _update_colors(self):
        """更新界面颜色以适应新主题"""
        from ui.theme import card_background_color, border_color
        tc = text_color()
        pc = placeholder_color()
        self._title_label.setStyleSheet(f"font-size: 32px; font-weight: bold; color: {tc};")
        self._appearance_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {tc};")
        self._theme_label.setStyleSheet(f"color: {tc};")
        if self._shortcuts_title:
            self._shortcuts_title.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {tc};")
        # 快捷键行标签
        for lbl in self._shortcut_labels:
            lbl.setStyleSheet(f"color: {tc};")
        # QKeySequenceEdit 样式
        bg = card_background_color()
        bc = border_color()
        for edit in self._shortcut_edits.values():
            edit.setStyleSheet(
                f"background: {bg}; color: {tc};"
                f" border: 1px solid {bc}; border-radius: 4px; padding: 3px;"
            )
        # hint label（找到快捷键卡片下方的说明标签）
        for lbl in self._shortcuts_card.findChildren(BodyLabel):
            ss = lbl.styleSheet()
            if 'font-size: 11px' in ss:
                lbl.setStyleSheet(f"color: {pc}; font-size: 11px;")

    # ── AI 配置方法 ──────────────────────────────────────────

    def _load_ai_config(self) -> None:
        from core.ai_client import AIConfig
        cfg = AIConfig.load()
        providers = ["openai_compatible", "ollama"]
        idx = providers.index(cfg.provider) if cfg.provider in providers else 0
        self._ai_provider_combo.setCurrentIndex(idx)
        self._ai_url_edit.setText(cfg.base_url)
        self._ai_key_edit.setText(cfg.api_key)
        self._ai_model_edit.setText(cfg.model)
        self._ai_timeout_edit.setText(str(cfg.timeout))
        self._ai_temperature_edit.setText(str(cfg.temperature))
        self._ai_max_tokens_edit.setText(str(cfg.max_tokens))
        self._on_ai_provider_changed(idx)

    def _on_ai_provider_changed(self, idx: int) -> None:
        is_ollama = idx == 1
        if is_ollama:
            if not self._ai_url_edit.text().strip():
                self._ai_url_edit.setText("http://localhost:11434/v1")
            self._ai_key_edit.setEnabled(False)
        else:
            self._ai_key_edit.setEnabled(True)

    def _save_ai_config(self) -> None:
        from core.ai_client import AIConfig
        providers = ["openai_compatible", "ollama"]
        provider = providers[self._ai_provider_combo.currentIndex()]
        try:
            timeout = int(self._ai_timeout_edit.text() or "60")
        except ValueError:
            timeout = 60
        try:
            temperature = float(self._ai_temperature_edit.text() or "0.7")
            temperature = max(0.0, min(2.0, temperature))
        except ValueError:
            temperature = 0.7
        try:
            max_tokens = int(self._ai_max_tokens_edit.text() or "2048")
        except ValueError:
            max_tokens = 2048
        cfg = AIConfig(
            provider=provider,
            base_url=self._ai_url_edit.text().strip() or "https://api.openai.com/v1",
            api_key=self._ai_key_edit.text().strip(),
            model=self._ai_model_edit.text().strip() or "gpt-4o-mini",
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        cfg.save()
        InfoBar.success("已保存", "AI 配置已保存", parent=self, position=InfoBarPosition.TOP)

    def _test_ai_connection(self) -> None:
        self._save_ai_config()
        InfoBar.info("测试中", "正在测试 AI 连接…", parent=self, position=InfoBarPosition.TOP)
        import asyncio
        from core.ai_client import AIClient
        client = AIClient()

        async def _test():
            return await client.test_connection()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在 Qt 事件循环中异步执行（需要 qasync 或类似库）
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _test())
                    ok, msg = future.result(timeout=30)
            else:
                ok, msg = loop.run_until_complete(_test())
        except Exception as e:
            ok, msg = False, str(e)

        if ok:
            InfoBar.success("连接成功", msg, parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.error("连接失败", msg, parent=self, position=InfoBarPosition.TOP)

    # ── 报告模板方法 ──────────────────────────────────────────

    def refresh_templates(self) -> None:
        """刷新报告模板列表。"""
        from core.project_manager import project_manager
        self._tmpl_list.clear()
        p = project_manager.current_project
        if p is None:
            return
        for t in p.report_templates:
            self._tmpl_list.addItem(f"{'[内置] ' if t.is_builtin else ''}{t.name}")

    def _on_new_template(self):
        from PySide6.QtWidgets import QInputDialog
        from core.project_manager import project_manager
        name, ok = QInputDialog.getText(self, "新建报告模板", "模板名称:")
        if not ok or not name.strip():
            return
        p = project_manager.current_project
        if p is None:
            InfoBar.warning("提示", "请先打开项目", parent=self, position=InfoBarPosition.TOP)
            return
        project_manager.add_report_template(name.strip(), "# 报告\n\n**日期：** {{date}}\n")
        self.refresh_templates()

    def _on_edit_template(self):
        from core.project_manager import project_manager
        p = project_manager.current_project
        if p is None:
            return
        idx = self._tmpl_list.currentRow()
        templates = p.report_templates
        if idx < 0 or idx >= len(templates):
            return
        tmpl = templates[idx]
        if tmpl.is_builtin:
            InfoBar.warning("提示", "内置模板不可编辑，请先复制", parent=self, position=InfoBarPosition.TOP)
            return
        from ui.dialogs.report_template_dialog import ReportTemplateDialog
        dlg = ReportTemplateDialog(self)
        # 预加载模板内容
        dlg._editor.setPlainText(tmpl.content)
        dlg._on_preview()
        if dlg.exec():
            tmpl.content = dlg._editor.toPlainText()
            p.is_modified = True

    def _on_delete_template(self):
        from core.project_manager import project_manager
        p = project_manager.current_project
        if p is None:
            return
        idx = self._tmpl_list.currentRow()
        templates = p.report_templates
        if idx < 0 or idx >= len(templates):
            return
        tmpl = templates[idx]
        if tmpl.is_builtin:
            InfoBar.warning("提示", "内置模板不可删除", parent=self, position=InfoBarPosition.TOP)
            return
        project_manager.delete_report_template(tmpl.id)
        self.refresh_templates()