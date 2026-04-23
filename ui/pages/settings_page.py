from typing import Literal, cast

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QFileDialog, QFrame, QFormLayout, QKeySequenceEdit)
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from qfluentwidgets import (ComboBox, setTheme, Theme, CardWidget, PushButton,
    BodyLabel, SubtitleLabel, TitleLabel, SmoothScrollArea,
    LineEdit, PrimaryPushButton, InfoBar, InfoBarPosition, PlainTextEdit,
    CheckBox, TabWidget, TabCloseButtonDisplayMode)

from ui.theme import (
    accent_color,
    body_text_style_sheet,
    border_color,
    card_background_color,
    card_title_style_sheet,
    error_text_style_sheet,
    install_fluent_tooltip,
    notification_parent,
    placeholder_text_style_sheet,
    secondary_text_style_sheet,
    text_color,
)
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.widgets.focus_commit import install_click_away_focus_commit
from core.shortcut_manager import shortcut_manager
from core.ui_preferences import TreeNameDisplayMode, get_tree_name_display_mode, set_tree_name_display_mode
from core.ai.providers import (
    get_provider_preset,
    list_builtin_models,
    list_provider_keys,
)


class SettingsPage(QWidget):
    """设置页面 - 主题切换、快捷键自定义等配置"""

    shortcuts_changed = Signal()  # 快捷键保存后发出
    tree_display_mode_changed = Signal(str)
    ai_panel_visibility_changed = Signal(bool)
    extensions_reloaded = Signal()
    project_modified = Signal()
    assets_modified = Signal()
    replay_onboarding_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title_label = None
        self._theme_label = None
        self._tree_display_mode_label = None
        self._tree_display_mode_combo = None
        self._tree_display_mode_keys = ["wrap", "elide"]
        self._appearance_title = None
        self._extension_card = None
        self._extension_title = None
        self._extension_hint = None
        self._external_extensions_dir_label = None
        self._external_extensions_dir_edit = None
        self._browse_external_extensions_dir_btn = None
        self._builtin_extensions_enabled_checkbox = None
        self._builtin_extension_list_label = None
        self._builtin_extension_empty_hint = None
        self._builtin_extension_options_widget = None
        self._builtin_extension_options_layout = None
        self._builtin_extension_checkboxes: dict[str, CheckBox] = {}
        self._save_extension_settings_btn = None
        self._onboarding_label = None
        self._onboarding_hint = None
        self._replay_onboarding_btn = None
        self._lang_title = None
        self._lang_placeholder = None
        self._shortcuts_title = None
        self._appearance_card = None
        self._lang_card = None
        self._shortcuts_card = None
        self.theme_combo = None
        self._shortcut_filter_edit = None
        self._shortcut_edits: dict[str, QKeySequenceEdit] = {}
        self._shortcut_rows: dict[str, QWidget] = {}
        self._shortcut_labels: list[BodyLabel] = []
        self._conflict_labels: dict[str, BodyLabel] = {}  # action -> red warning label
        self._provider_keys = list_provider_keys()
        self._active_provider_key = (
            "openai_compatible"
            if "openai_compatible" in self._provider_keys
            else (self._provider_keys[0] if self._provider_keys else "openai_compatible")
        )
        self.setup_ui()

    @staticmethod
    def _tab_content_margins() -> tuple[int, int, int, int]:
        return (14, 12, 14, 12)

    def _notification_parent(self) -> QWidget:
        parent = notification_parent(self)
        return parent if isinstance(parent, QWidget) else self

    def setup_ui(self):
        tabs = TabWidget(self)
        tabs.tabBar.setAddButtonVisible(False)
        tabs.tabBar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        self._tabs = tabs

        tabs.addTab(self._build_general_tab(), "常规")
        tabs.addTab(self._build_shortcuts_tab(), "快捷键")
        self._hidden_ai_tab = self._build_ai_tab()
        self._hidden_ai_tab.hide()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(tabs)

        self._load_ai_config()
        self._load_extension_settings()
        self._refresh_ai_tools_panel()
        self._install_tooltip_filters()
        self._click_away_focus_commit = install_click_away_focus_commit(self)

    def _install_tooltip_filters(self) -> None:
        for widget in self.findChildren(QWidget):
            install_fluent_tooltip(widget, delay=400)

    def _shortcut_edit_style(self, *, focused: bool) -> str:
        border = accent_color() if focused else border_color()
        border_width = 2 if focused else 1
        background = card_background_color()
        return (
            f"background: {background}; color: {text_color()};"
            f" border: {border_width}px solid {border}; border-radius: 6px; padding: 3px;"
        )

    def _apply_shortcut_edit_style(self, edit: QKeySequenceEdit, *, focused: bool) -> None:
        edit.setStyleSheet(self._shortcut_edit_style(focused=focused))

    def eventFilter(self, watched, event):
        if isinstance(watched, QKeySequenceEdit) and watched in self._shortcut_edits.values():
            if event.type() == QEvent.Type.FocusIn:
                self._apply_shortcut_edit_style(watched, focused=True)
            elif event.type() == QEvent.Type.FocusOut:
                self._apply_shortcut_edit_style(watched, focused=False)
        return super().eventFilter(watched, event)

    @staticmethod
    def _apply_card_layout_metrics(layout) -> None:
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

    def _apply_shortcut_filter_style(self) -> None:
        if self._shortcut_filter_edit is None:
            return
        self._shortcut_filter_edit.setFixedHeight(36)
        self._shortcut_filter_edit.setStyleSheet(
            f"background: {card_background_color()}; color: {text_color()};"
            f" border: 1px solid {accent_color()}; border-radius: 8px; padding: 4px 8px;"
        )

    def _build_general_tab(self) -> QWidget:
        outer = SmoothScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(*self._tab_content_margins())
        outer.setWidget(content)

        # ── 外观设置 ──
        self._appearance_card = CardWidget(content)
        appearance_layout = QVBoxLayout(self._appearance_card)
        self._apply_card_layout_metrics(appearance_layout)

        self._appearance_title = BodyLabel("外观", self._appearance_card)
        self._appearance_title.setStyleSheet(card_title_style_sheet(font_size=18))
        appearance_layout.addWidget(self._appearance_title)

        theme_layout = QVBoxLayout()
        self._theme_label = BodyLabel("主题", content)
        self._theme_label.setStyleSheet(body_text_style_sheet())
        theme_layout.addWidget(self._theme_label)

        self.theme_combo = ComboBox(content)
        self.theme_combo.addItems(["浅色", "深色", "跟随系统"])
        self.theme_combo.setCurrentIndex(2)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        theme_layout.addWidget(self.theme_combo)

        appearance_layout.addLayout(theme_layout)

        tree_mode_layout = QVBoxLayout()
        self._tree_display_mode_label = BodyLabel("项目树长名称显示", content)
        self._tree_display_mode_label.setStyleSheet(body_text_style_sheet())
        tree_mode_layout.addWidget(self._tree_display_mode_label)

        self._tree_display_mode_combo = ComboBox(content)
        self._tree_display_mode_combo.addItems(["自动换行", "部分隐藏"])
        current_mode = get_tree_name_display_mode()
        current_index = 1 if current_mode == "elide" else 0
        self._tree_display_mode_combo.setCurrentIndex(current_index)
        self._tree_display_mode_combo.currentIndexChanged.connect(self._on_tree_display_mode_changed)
        tree_mode_layout.addWidget(self._tree_display_mode_combo)
        appearance_layout.addLayout(tree_mode_layout)

        onboarding_layout = QVBoxLayout()
        self._onboarding_label = BodyLabel("新手引导", content)
        self._onboarding_label.setStyleSheet(body_text_style_sheet())
        onboarding_layout.addWidget(self._onboarding_label)

        self._onboarding_hint = BodyLabel("点击后会重新播放主页引导，并重置数据管理、处理、可视化、分析和图片数据化页面的 TeachingTip 状态。", content)
        self._onboarding_hint.setWordWrap(True)
        self._onboarding_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        onboarding_layout.addWidget(self._onboarding_hint)

        self._replay_onboarding_btn = PushButton("重新显示引导", content)
        self._replay_onboarding_btn.clicked.connect(self.replay_onboarding_requested.emit)
        onboarding_layout.addWidget(self._replay_onboarding_btn, alignment=Qt.AlignmentFlag.AlignLeft)
        appearance_layout.addLayout(onboarding_layout)

        layout.addWidget(self._appearance_card)

        self._extension_card = CardWidget(content)
        extension_layout = QVBoxLayout(self._extension_card)
        self._apply_card_layout_metrics(extension_layout)

        self._extension_title = BodyLabel("扩展", self._extension_card)
        self._extension_title.setStyleSheet(card_title_style_sheet(font_size=18))
        extension_layout.addWidget(self._extension_title)

        self._extension_hint = BodyLabel(
            "内置扩展会随程序一起分发。这里可以统一关闭内置扩展，或单独停用指定内置扩展；外部扩展仍会从配置目录自动扫描。",
            self._extension_card,
        )
        self._extension_hint.setWordWrap(True)
        self._extension_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        extension_layout.addWidget(self._extension_hint)

        external_dir_row = QHBoxLayout()
        self._external_extensions_dir_label = BodyLabel("外部扩展目录", self._extension_card)
        self._external_extensions_dir_label.setStyleSheet(body_text_style_sheet())
        external_dir_row.addWidget(self._external_extensions_dir_label)
        self._external_extensions_dir_edit = LineEdit(self._extension_card)
        self._external_extensions_dir_edit.setPlaceholderText("~/.config/aline/extensions")
        external_dir_row.addWidget(self._external_extensions_dir_edit, 1)
        self._browse_external_extensions_dir_btn = PushButton("浏览", self._extension_card)
        self._browse_external_extensions_dir_btn.clicked.connect(self._choose_external_extensions_directory)
        external_dir_row.addWidget(self._browse_external_extensions_dir_btn)
        extension_layout.addLayout(external_dir_row)

        self._builtin_extensions_enabled_checkbox = CheckBox("启动时加载内置扩展", self._extension_card)
        self._builtin_extensions_enabled_checkbox.stateChanged.connect(self._on_builtin_extensions_enabled_changed)
        extension_layout.addWidget(self._builtin_extensions_enabled_checkbox)

        self._builtin_extension_list_label = BodyLabel("内置扩展项", self._extension_card)
        self._builtin_extension_list_label.setStyleSheet(body_text_style_sheet())
        extension_layout.addWidget(self._builtin_extension_list_label)

        self._builtin_extension_empty_hint = BodyLabel("当前未发现内置扩展。", self._extension_card)
        self._builtin_extension_empty_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        extension_layout.addWidget(self._builtin_extension_empty_hint)

        self._builtin_extension_options_widget = QWidget(self._extension_card)
        self._builtin_extension_options_layout = QVBoxLayout(self._builtin_extension_options_widget)
        self._builtin_extension_options_layout.setContentsMargins(0, 0, 0, 0)
        self._builtin_extension_options_layout.setSpacing(6)
        extension_layout.addWidget(self._builtin_extension_options_widget)

        extension_btn_row = QHBoxLayout()
        self._save_extension_settings_btn = PrimaryPushButton("保存并重载扩展", self._extension_card)
        self._save_extension_settings_btn.clicked.connect(self._save_extension_settings)
        extension_btn_row.addWidget(self._save_extension_settings_btn)
        extension_btn_row.addStretch()
        extension_layout.addLayout(extension_btn_row)

        layout.addWidget(self._extension_card)

        # ── 语言设置（预留）──
        self._lang_card = CardWidget(content)
        lang_layout = QVBoxLayout(self._lang_card)
        self._apply_card_layout_metrics(lang_layout)

        self._lang_title = BodyLabel("语言", self._lang_card)
        self._lang_title.setStyleSheet(card_title_style_sheet(font_size=18))
        lang_layout.addWidget(self._lang_title)

        self._lang_placeholder = BodyLabel("语言设置（预留）", content)
        self._lang_placeholder.setStyleSheet(placeholder_text_style_sheet(font_size=12, italic=True))
        lang_layout.addWidget(self._lang_placeholder)

        layout.addWidget(self._lang_card)
        self._lang_card.hide()  # 暂不实现语言设置

        layout.addStretch()
        return outer

    def _build_shortcuts_tab(self) -> QWidget:
        outer = SmoothScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(*self._tab_content_margins())
        outer.setWidget(content)

        self._shortcuts_card = CardWidget(content)
        shortcuts_layout = QVBoxLayout(self._shortcuts_card)
        self._apply_card_layout_metrics(shortcuts_layout)

        self._shortcuts_title = BodyLabel("快捷键", self._shortcuts_card)
        self._shortcuts_title.setStyleSheet(card_title_style_sheet(font_size=18))
        shortcuts_layout.addWidget(self._shortcuts_title)

        hint = BodyLabel("所有已注册的界面动作都会显示在这里。点击输入框后按下新快捷键，再点击“应用快捷键”保存。", self._shortcuts_card)
        hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        hint.setWordWrap(True)
        shortcuts_layout.addWidget(hint)

        self._shortcut_filter_edit = LineEdit(self._shortcuts_card)
        self._shortcut_filter_edit.setPlaceholderText("筛选快捷键动作，例如“分析”或“导出”")
        self._shortcut_filter_edit.setClearButtonEnabled(True)
        self._shortcut_filter_edit.setToolTip("按动作名称、分类或关键词筛选快捷键")
        self._shortcut_filter_edit.textChanged.connect(self._filter_shortcut_rows)
        self._apply_shortcut_filter_style()
        shortcuts_layout.addWidget(self._shortcut_filter_edit)

        sc_content = QWidget(self._shortcuts_card)
        sc_form = QFormLayout(sc_content)
        sc_form.setSpacing(6)
        sc_form.setContentsMargins(0, 4, 0, 4)

        from ui.theme import card_background_color, border_color
        from PySide6.QtGui import QKeySequence

        for definition in shortcut_manager.list_definitions():
            action = definition.action
            label = f"[{definition.category}] {definition.label}"
            edit = QKeySequenceEdit(sc_content)
            edit.setKeySequence(QKeySequence(shortcut_manager.get(action)))
            self._apply_shortcut_edit_style(edit, focused=False)
            edit.installEventFilter(self)
            row_lbl = BodyLabel(label + ":", sc_content)
            row_lbl.setStyleSheet(body_text_style_sheet())

            conflict_lbl = BodyLabel("", sc_content)
            conflict_lbl.setStyleSheet(error_text_style_sheet(font_size=10))
            conflict_lbl.setVisible(False)

            edit_col = QWidget(sc_content)
            ecol_layout = QVBoxLayout(edit_col)
            ecol_layout.setContentsMargins(0, 0, 0, 0)
            ecol_layout.setSpacing(1)
            ecol_layout.addWidget(edit)
            ecol_layout.addWidget(conflict_lbl)

            sc_form.addRow(row_lbl, edit_col)
            self._shortcut_edits[action] = edit
            self._shortcut_rows[action] = edit_col
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
        layout.addStretch()
        return outer

    def _build_ai_tab(self) -> QWidget:
        outer = SmoothScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(*self._tab_content_margins())
        outer.setWidget(content)

        # ── AI 接口配置 ──
        self._ai_card = CardWidget(content)
        ai_layout = QVBoxLayout(self._ai_card)
        self._apply_card_layout_metrics(ai_layout)

        ai_title = BodyLabel("AI 接口", self._ai_card)
        ai_title.setStyleSheet(card_title_style_sheet(font_size=18))
        ai_layout.addWidget(ai_title)

        self._ai_provider_hint = BodyLabel("", self._ai_card)
        self._ai_provider_hint.setWordWrap(True)
        self._ai_provider_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        ai_layout.addWidget(self._ai_provider_hint)

        form = QFormLayout()
        form.setSpacing(8)

        self._ai_provider_combo = ComboBox(self._ai_card)
        for provider_key in self._provider_keys:
            self._ai_provider_combo.addItem(get_provider_preset(provider_key)["label"])
        self._ai_provider_combo.currentIndexChanged.connect(self._on_ai_provider_changed)
        form.addRow("接口类型:", self._ai_provider_combo)

        self._ai_url_edit = LineEdit(self._ai_card)
        self._ai_url_edit.setPlaceholderText("例: https://api.openai.com/v1  或  http://localhost:11434")
        self._ai_url_edit.setToolTip("AI 接口的 Base URL，OpenAI 填官方地址，Ollama 填本地地址")
        form.addRow("API 地址:", self._ai_url_edit)

        self._ai_key_edit = LineEdit(self._ai_card)
        self._ai_key_edit.setPlaceholderText("sk-...（OpenAI 必填，Ollama 可选）")
        self._ai_key_edit.setToolTip("API 认证密钥，OpenAI/商用接口通常必填；Ollama 本地部署可留空，服务端代理可填写")
        form.addRow("API Key:", self._ai_key_edit)

        self._ai_model_preset_combo = ComboBox(self._ai_card)
        self._ai_model_preset_combo.currentIndexChanged.connect(self._on_model_preset_changed)
        form.addRow("推荐模型:", self._ai_model_preset_combo)

        self._ai_model_edit = LineEdit(self._ai_card)
        form.addRow("模型名称:", self._ai_model_edit)

        self._ai_timeout_edit = LineEdit(self._ai_card)
        self._ai_timeout_edit.setPlaceholderText("60")
        self._ai_timeout_edit.setToolTip("等待 AI 响应的超时秒数，网络较慢或模型较大时可适当增大")
        form.addRow("超时(秒):", self._ai_timeout_edit)

        self._ai_temperature_edit = LineEdit(self._ai_card)
        self._ai_temperature_edit.setPlaceholderText("0.7")
        self._ai_temperature_edit.setToolTip("控制回复随机性：0 = 完全确定性，1-2 = 创造性更高。\n一般推荐 0.5~0.8，精确计算任务建议 0")
        form.addRow("Temperature:", self._ai_temperature_edit)

        self._ai_top_p_edit = LineEdit(self._ai_card)
        self._ai_top_p_edit.setPlaceholderText("1.0")
        self._ai_top_p_edit.setToolTip("核采样概率阈值，与 Temperature 配合使用。\n1.0 表示不限制，通常保持默认 1.0 即可")
        form.addRow("Top P:", self._ai_top_p_edit)

        self._ai_max_tokens_edit = LineEdit(self._ai_card)
        self._ai_max_tokens_edit.setPlaceholderText("2048")
        self._ai_max_tokens_edit.setToolTip("单次回复的最大 token 数量，超出后截断\n日常对话 2048 足够，长文档分析可调高至 4096")
        form.addRow("Max Tokens:", self._ai_max_tokens_edit)

        self._ai_ollama_keep_alive_edit = LineEdit(self._ai_card)
        self._ai_ollama_keep_alive_edit.setPlaceholderText("5m")
        self._ai_ollama_keep_alive_edit.setToolTip("Ollama 模型在内存中保持加载的时长\n格式：数字+单位，如 5m / 1h / 0（永久）。仅 Ollama 接口生效")
        form.addRow("Ollama Keep-Alive:", self._ai_ollama_keep_alive_edit)

        self._ai_ollama_num_ctx_edit = LineEdit(self._ai_card)
        self._ai_ollama_num_ctx_edit.setPlaceholderText("4096")
        self._ai_ollama_num_ctx_edit.setToolTip("Ollama 模型上下文窗口大小（token 数量）\n越大可处理更长的历史记录，但内存占用也更高。仅 Ollama 接口生效")
        form.addRow("Ollama Num Ctx:", self._ai_ollama_num_ctx_edit)

        self._ai_system_prompt_edit = PlainTextEdit(self._ai_card)
        self._ai_system_prompt_edit.setPlaceholderText("全局系统提示，例如：优先用中文回答，并保持术语统一。")
        self._ai_system_prompt_edit.setFixedHeight(96)
        form.addRow("系统提示:", self._ai_system_prompt_edit)

        self._ai_show_panel_cb = CheckBox("显示右侧 AI 助手栏", self._ai_card)
        self._ai_show_panel_cb.setChecked(True)
        ai_layout.addWidget(self._ai_show_panel_cb)

        ai_layout.addLayout(form)

        ai_btn_row = QHBoxLayout()
        save_ai_btn = PrimaryPushButton("保存配置")
        save_ai_btn.clicked.connect(self._save_ai_config)
        test_ai_btn = PushButton("测试连接")
        test_ai_btn.clicked.connect(self._test_ai_connection)
        self._ai_refresh_models_btn = PushButton("探测模型")
        self._ai_refresh_models_btn.clicked.connect(self._refresh_available_models)
        ai_btn_row.addWidget(save_ai_btn)
        ai_btn_row.addWidget(test_ai_btn)
        ai_btn_row.addWidget(self._ai_refresh_models_btn)
        ai_btn_row.addStretch()
        ai_layout.addLayout(ai_btn_row)

        layout.addWidget(self._ai_card)

        self._ai_tool_items: list[dict] = []  # {source, type, name, desc, item}

        self._ai_tools_card = CardWidget(content)
        ai_tools_layout = QVBoxLayout(self._ai_tools_card)
        self._apply_card_layout_metrics(ai_tools_layout)

        ai_tools_title = BodyLabel("AI 工具管理", self._ai_tools_card)
        ai_tools_title.setStyleSheet(card_title_style_sheet(font_size=18))
        ai_tools_layout.addWidget(ai_tools_title)

        self._ai_tools_project_label = BodyLabel("当前项目: 未打开", self._ai_tools_card)
        self._ai_tools_project_label.setStyleSheet(body_text_style_sheet())
        ai_tools_layout.addWidget(self._ai_tools_project_label)

        self._ai_tools_summary_label = BodyLabel("内置 0 · Prompt 0 · Skill 0 · Agent 0", self._ai_tools_card)
        self._ai_tools_summary_label.setStyleSheet(secondary_text_style_sheet())
        ai_tools_layout.addWidget(self._ai_tools_summary_label)

        # 工具选择下拉框
        selector_row = QHBoxLayout()
        selector_row.addWidget(BodyLabel("选择工具:", self._ai_tools_card))
        self._ai_tool_selector = ComboBox(self._ai_tools_card)
        self._ai_tool_selector.setMinimumWidth(300)
        self._ai_tool_selector.currentIndexChanged.connect(self._on_ai_tool_selected)
        selector_row.addWidget(self._ai_tool_selector, 1)
        ai_tools_layout.addLayout(selector_row)

        # 工具详情卡片
        self._ai_tool_detail_card = CardWidget(self._ai_tools_card)
        detail_layout = QVBoxLayout(self._ai_tool_detail_card)
        detail_layout.setSpacing(6)
        detail_layout.setContentsMargins(12, 10, 12, 10)

        detail_name_row = QHBoxLayout()
        detail_name_row.addWidget(BodyLabel("名称:", self._ai_tool_detail_card))
        self._ai_tool_detail_name = BodyLabel("—", self._ai_tool_detail_card)
        self._ai_tool_detail_name.setStyleSheet(f"{body_text_style_sheet()} font-weight: bold;")
        detail_name_row.addWidget(self._ai_tool_detail_name, 1)
        detail_layout.addLayout(detail_name_row)

        detail_type_row = QHBoxLayout()
        detail_type_row.addWidget(BodyLabel("类型:", self._ai_tool_detail_card))
        self._ai_tool_detail_type = BodyLabel("—", self._ai_tool_detail_card)
        self._ai_tool_detail_type.setStyleSheet(secondary_text_style_sheet())
        detail_type_row.addWidget(self._ai_tool_detail_type, 1)
        detail_layout.addLayout(detail_type_row)

        detail_desc_row = QHBoxLayout()
        detail_desc_row.addWidget(BodyLabel("描述:", self._ai_tool_detail_card))
        self._ai_tool_detail_desc = BodyLabel("—", self._ai_tool_detail_card)
        self._ai_tool_detail_desc.setWordWrap(True)
        detail_desc_row.addWidget(self._ai_tool_detail_desc, 1)
        detail_layout.addLayout(detail_desc_row)

        detail_action_row = QHBoxLayout()
        self._ai_tool_edit_btn = PushButton("编辑", self._ai_tool_detail_card)
        self._ai_tool_edit_btn.setEnabled(False)
        self._ai_tool_edit_btn.clicked.connect(self._on_edit_selected_ai_tool)
        self._ai_tool_delete_btn = PushButton("删除", self._ai_tool_detail_card)
        self._ai_tool_delete_btn.setEnabled(False)
        self._ai_tool_delete_btn.clicked.connect(self._on_delete_selected_ai_tool)
        detail_action_row.addWidget(self._ai_tool_edit_btn)
        detail_action_row.addWidget(self._ai_tool_delete_btn)
        detail_action_row.addStretch()
        detail_layout.addLayout(detail_action_row)

        ai_tools_layout.addWidget(self._ai_tool_detail_card)

        # 创建按钮行
        ai_tools_btn_row = QHBoxLayout()
        new_prompt_btn = PushButton("新建 Prompt", self._ai_tools_card)
        new_prompt_btn.clicked.connect(lambda: self._open_ai_tool_dialog("prompt"))
        new_skill_btn = PushButton("新建 Skill", self._ai_tools_card)
        new_skill_btn.clicked.connect(lambda: self._open_ai_tool_dialog("skill"))
        new_agent_btn = PushButton("新建 Agent", self._ai_tools_card)
        new_agent_btn.clicked.connect(lambda: self._open_ai_tool_dialog("agent"))
        refresh_ai_tools_btn = PushButton("刷新", self._ai_tools_card)
        refresh_ai_tools_btn.clicked.connect(self._refresh_ai_tools_panel)
        ai_tools_btn_row.addWidget(new_prompt_btn)
        ai_tools_btn_row.addWidget(new_skill_btn)
        ai_tools_btn_row.addWidget(new_agent_btn)
        ai_tools_btn_row.addWidget(refresh_ai_tools_btn)
        ai_tools_btn_row.addStretch()
        ai_tools_layout.addLayout(ai_tools_btn_row)

        layout.addWidget(self._ai_tools_card)

        # 兼容字段（隐藏）
        from qfluentwidgets import ListWidget as _ListWidget
        self._tmpl_card = CardWidget(content)
        self._tmpl_card.hide()
        self._tmpl_list = _ListWidget(self._tmpl_card)

        layout.addStretch()
        return outer

    def _on_apply_shortcuts(self):
        """保存用户修改的快捷键"""
        mapping = {}
        for action, edit in self._shortcut_edits.items():
            mapping[action] = edit.keySequence().toString()
        shortcut_manager.apply_all(mapping)
        self.shortcuts_changed.emit()

    def _filter_shortcut_rows(self, text: str) -> None:
        query = text.strip().lower()
        for definition in shortcut_manager.list_definitions():
            action = definition.action
            label = definition.label
            tags = " ".join(shortcut_manager.search_tags(action))
            visible = not query or query in action.lower() or query in label.lower() or query in tags.lower()
            row_prefix = f"[{definition.category}] {label}"
            row_label = next((item for item in self._shortcut_labels if item.text().startswith(row_prefix)), None)
            edit_col = self._shortcut_rows.get(action)
            if row_label is not None:
                row_label.setVisible(visible)
            if edit_col is not None:
                edit_col.setVisible(visible)

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
            conflict_names = " / ".join(str(sm.LABELS.get(a, a) or a) for a in conflicts)
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
        if self._appearance_title is not None:
            self._appearance_title.setStyleSheet(card_title_style_sheet(font_size=18))
        if self._theme_label is not None:
            self._theme_label.setStyleSheet(body_text_style_sheet())
        if self._tree_display_mode_label is not None:
            self._tree_display_mode_label.setStyleSheet(body_text_style_sheet())
        if self._onboarding_label is not None:
            self._onboarding_label.setStyleSheet(body_text_style_sheet())
        if self._onboarding_hint is not None:
            self._onboarding_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if self._extension_title is not None:
            self._extension_title.setStyleSheet(card_title_style_sheet(font_size=18))
        if self._extension_hint is not None:
            self._extension_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if self._external_extensions_dir_label is not None:
            self._external_extensions_dir_label.setStyleSheet(body_text_style_sheet())
        if self._builtin_extension_list_label is not None:
            self._builtin_extension_list_label.setStyleSheet(body_text_style_sheet())
        if self._builtin_extension_empty_hint is not None:
            self._builtin_extension_empty_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if self._lang_title is not None:
            self._lang_title.setStyleSheet(card_title_style_sheet(font_size=18))
        if self._lang_placeholder is not None:
            self._lang_placeholder.setStyleSheet(placeholder_text_style_sheet(font_size=12, italic=True))
        if self._shortcuts_title:
            self._shortcuts_title.setStyleSheet(card_title_style_sheet(font_size=18))
        self._apply_shortcut_filter_style()
        # 快捷键行标签
        for lbl in self._shortcut_labels:
            lbl.setStyleSheet(body_text_style_sheet())
        for lbl in self._conflict_labels.values():
            lbl.setStyleSheet(error_text_style_sheet(font_size=10))
        # QKeySequenceEdit 样式
        for edit in self._shortcut_edits.values():
            self._apply_shortcut_edit_style(edit, focused=edit.hasFocus())
        # hint label（找到快捷键卡片下方的说明标签）
        if self._shortcuts_card is not None:
            for lbl in self._shortcuts_card.findChildren(BodyLabel):
                ss = lbl.styleSheet()
                if 'font-size: 11px' in ss:
                    lbl.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if hasattr(self, "_ai_provider_hint") and self._ai_provider_hint is not None:
            self._ai_provider_hint.setStyleSheet(placeholder_text_style_sheet(font_size=11))
        if hasattr(self, "_ai_tools_project_label") and self._ai_tools_project_label is not None:
            self._ai_tools_project_label.setStyleSheet(body_text_style_sheet())
        if hasattr(self, "_ai_tools_summary_label") and self._ai_tools_summary_label is not None:
            self._ai_tools_summary_label.setStyleSheet(secondary_text_style_sheet())
        if hasattr(self, "_ai_tool_detail_name") and self._ai_tool_detail_name is not None:
            self._ai_tool_detail_name.setStyleSheet(f"{body_text_style_sheet()} font-weight: bold;")
        if hasattr(self, "_ai_tool_detail_type") and self._ai_tool_detail_type is not None:
            self._ai_tool_detail_type.setStyleSheet(secondary_text_style_sheet())

    def _current_tree_display_mode(self) -> TreeNameDisplayMode:
        if self._tree_display_mode_combo is None:
            return "wrap"
        idx = self._tree_display_mode_combo.currentIndex()
        if 0 <= idx < len(self._tree_display_mode_keys):
            return "elide" if self._tree_display_mode_keys[idx] == "elide" else "wrap"
        return "wrap"

    def _on_tree_display_mode_changed(self, _index: int) -> None:
        mode = set_tree_name_display_mode(self._current_tree_display_mode())
        self.tree_display_mode_changed.emit(mode)

    def _clear_builtin_extension_options(self) -> None:
        self._builtin_extension_checkboxes.clear()
        if self._builtin_extension_options_layout is None:
            return
        while self._builtin_extension_options_layout.count() > 0:
            item = self._builtin_extension_options_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_builtin_extension_options(self, specs: list[dict], disabled_extension_ids: list[str]) -> None:
        self._clear_builtin_extension_options()
        if self._builtin_extension_empty_hint is not None:
            self._builtin_extension_empty_hint.setVisible(not specs)
        if self._builtin_extension_options_layout is None:
            return

        disabled_markers = {str(item).strip() for item in disabled_extension_ids}
        load_builtin = bool(
            self._builtin_extensions_enabled_checkbox is not None
            and self._builtin_extensions_enabled_checkbox.isChecked()
        )
        for spec in specs:
            spec_id = str(spec.get("id") or "").strip()
            if not spec_id:
                continue
            category_labels = [str(item).strip() for item in spec.get("category_labels", []) if str(item).strip()]
            checkbox_name = str(spec.get("name") or spec_id)
            category_prefix = " / ".join(category_labels) if category_labels else "扩展"
            checkbox_label = f"{category_prefix}·{checkbox_name}"
            checkbox = CheckBox(checkbox_label, self._builtin_extension_options_widget)
            checkbox.setChecked(spec_id not in disabled_markers)
            checkbox.setEnabled(load_builtin)
            tooltip_lines = [str(spec.get("file_name") or "")]
            type_ids = [str(item).strip() for item in spec.get("type_ids", []) if str(item).strip()]
            if type_ids:
                tooltip_lines.append(f"类型: {', '.join(type_ids)}")
            load_error = str(spec.get("load_error") or "").strip()
            if load_error:
                tooltip_lines.append(f"探测失败: {load_error}")
            checkbox.setToolTip("\n".join(line for line in tooltip_lines if line))
            install_fluent_tooltip(checkbox, delay=400)
            self._builtin_extension_checkboxes[spec_id] = checkbox
            self._builtin_extension_options_layout.addWidget(checkbox)

    def _on_builtin_extensions_enabled_changed(self) -> None:
        enabled = bool(
            self._builtin_extensions_enabled_checkbox is not None
            and self._builtin_extensions_enabled_checkbox.isChecked()
        )
        for checkbox in self._builtin_extension_checkboxes.values():
            checkbox.setEnabled(enabled)

    def _load_extension_settings(self) -> None:
        from core.extension_api import list_builtin_extension_specs
        from core.extension_settings import get_builtin_extension_settings, get_external_extensions_directory

        load_builtin, disabled_extension_ids = get_builtin_extension_settings()
        if self._builtin_extensions_enabled_checkbox is not None:
            self._builtin_extensions_enabled_checkbox.blockSignals(True)
            self._builtin_extensions_enabled_checkbox.setChecked(load_builtin)
            self._builtin_extensions_enabled_checkbox.blockSignals(False)
        if self._external_extensions_dir_edit is not None:
            self._external_extensions_dir_edit.setText(str(get_external_extensions_directory()))
        self._rebuild_builtin_extension_options(list_builtin_extension_specs(), disabled_extension_ids)
        self._on_builtin_extensions_enabled_changed()

    def _choose_external_extensions_directory(self) -> None:
        current_path = self._external_extensions_dir_edit.text().strip() if self._external_extensions_dir_edit is not None else ""
        chosen = QFileDialog.getExistingDirectory(self, "选择外部扩展目录", current_path or "")
        if chosen and self._external_extensions_dir_edit is not None:
            self._external_extensions_dir_edit.setText(chosen)

    def _save_extension_settings(self) -> None:
        from core.extension_api import reload_configured_extensions
        from core.extension_settings import set_builtin_extension_settings, set_external_extensions_directory

        load_builtin = bool(
            self._builtin_extensions_enabled_checkbox is not None
            and self._builtin_extensions_enabled_checkbox.isChecked()
        )
        disabled_extension_ids = [
            spec_id for spec_id, checkbox in self._builtin_extension_checkboxes.items()
            if not checkbox.isChecked()
        ]

        external_dir = self._external_extensions_dir_edit.text().strip() if self._external_extensions_dir_edit is not None else ""
        try:
            set_external_extensions_directory(external_dir)
        except ValueError as exc:
            InfoBar.error("扩展设置保存失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        set_builtin_extension_settings(load_builtin, disabled_extension_ids)
        report = reload_configured_extensions()
        self._load_extension_settings()
        self.extensions_reloaded.emit()
        if report.get("errors"):
            InfoBar.warning(
                "扩展设置已保存",
                f"已加载 {len(report.get('loaded', []))} 个扩展，{len(report.get('errors', []))} 个失败",
                parent=self._notification_parent(),
                position=InfoBarPosition.TOP,
            )
            return
        InfoBar.success(
            "扩展设置已保存",
            f"已重新加载 {len(report.get('loaded', []))} 个扩展",
            parent=self._notification_parent(),
            position=InfoBarPosition.TOP,
        )

    # ── AI 配置方法 ──────────────────────────────────────────

    def _current_provider_key(self) -> str:
        idx = self._ai_provider_combo.currentIndex()
        if 0 <= idx < len(self._provider_keys):
            return self._provider_keys[idx]
        return self._active_provider_key

    def _populate_model_presets(self, models: list[str], preferred: str = "") -> None:
        current = preferred or self._ai_model_edit.text().strip()
        self._ai_model_preset_combo.blockSignals(True)
        self._ai_model_preset_combo.clear()
        for model in models:
            self._ai_model_preset_combo.addItem(model)
        if models:
            if current and current in models:
                self._ai_model_preset_combo.setCurrentText(current)
            else:
                self._ai_model_preset_combo.setCurrentIndex(0)
        self._ai_model_preset_combo.blockSignals(False)

    def _on_model_preset_changed(self, idx: int) -> None:
        if idx < 0:
            return
        model_name = self._ai_model_preset_combo.currentText().strip()
        if model_name:
            self._ai_model_edit.setText(model_name)

    def _parse_int(self, text: str, fallback: int, minimum: int | None = None) -> int:
        try:
            value = int(text or str(fallback))
        except ValueError:
            value = fallback
        if minimum is not None:
            value = max(minimum, value)
        return value

    def _parse_float(self, text: str, fallback: float, minimum: float, maximum: float) -> float:
        try:
            value = float(text or str(fallback))
        except ValueError:
            value = fallback
        return max(minimum, min(maximum, value))

    def _collect_ai_config(self):
        from core.ai_client import AIConfig

        provider = self._current_provider_key()
        if provider not in {"openai_compatible", "ollama"}:
            provider = "openai_compatible"
        provider = cast(Literal["openai_compatible", "ollama"], provider)
        preset = get_provider_preset(provider)
        return AIConfig(
            provider=provider,
            base_url=self._ai_url_edit.text().strip() or preset["default_url"],
            api_key=self._ai_key_edit.text().strip(),
            model=self._ai_model_edit.text().strip() or preset["default_model"],
            timeout=self._parse_int(self._ai_timeout_edit.text(), 60, minimum=1),
            temperature=self._parse_float(self._ai_temperature_edit.text(), 0.7, 0.0, 2.0),
            top_p=self._parse_float(self._ai_top_p_edit.text(), 1.0, 0.0, 1.0),
            max_tokens=self._parse_int(self._ai_max_tokens_edit.text(), 2048, minimum=1),
            show_assistant=self._ai_show_panel_cb.isChecked(),
            system_prompt=self._ai_system_prompt_edit.toPlainText().strip(),
            ollama_keep_alive=self._ai_ollama_keep_alive_edit.text().strip() or "5m",
            ollama_num_ctx=self._parse_int(self._ai_ollama_num_ctx_edit.text(), 4096, minimum=1),
        )

    def _load_ai_config(self) -> None:
        from core.ai_client import AIConfig
        cfg = AIConfig.load()
        idx = self._provider_keys.index(cfg.provider) if cfg.provider in self._provider_keys else 0
        self._ai_provider_combo.setCurrentIndex(idx)
        self._ai_url_edit.setText(cfg.base_url)
        self._ai_key_edit.setText(cfg.api_key)
        self._ai_model_edit.setText(cfg.model)
        self._ai_timeout_edit.setText(str(cfg.timeout))
        self._ai_temperature_edit.setText(str(cfg.temperature))
        self._ai_top_p_edit.setText(str(cfg.top_p))
        self._ai_max_tokens_edit.setText(str(cfg.max_tokens))
        self._ai_system_prompt_edit.setPlainText(cfg.system_prompt)
        self._ai_ollama_keep_alive_edit.setText(cfg.ollama_keep_alive)
        self._ai_ollama_num_ctx_edit.setText(str(cfg.ollama_num_ctx))
        self._ai_show_panel_cb.setChecked(bool(cfg.show_assistant))
        self._on_ai_provider_changed(idx)

    def _on_ai_provider_changed(self, idx: int) -> None:
        provider = self._provider_keys[idx] if 0 <= idx < len(self._provider_keys) else "openai_compatible"
        previous_preset = get_provider_preset(self._active_provider_key)
        preset = get_provider_preset(provider)

        current_url = self._ai_url_edit.text().strip()
        if not current_url or current_url == previous_preset["default_url"]:
            self._ai_url_edit.setText(preset["default_url"])
        self._ai_url_edit.setPlaceholderText(preset["default_url"])

        current_model = self._ai_model_edit.text().strip()
        if not current_model or current_model == previous_preset["default_model"]:
            self._ai_model_edit.setText(preset["default_model"])
        self._ai_model_edit.setPlaceholderText(preset["model_placeholder"])
        self._populate_model_presets(list_builtin_models(provider), preferred=self._ai_model_edit.text().strip())

        requires_key = bool(preset.get("api_key_required", True))
        self._ai_key_edit.setEnabled(True)
        if not requires_key:
            self._ai_key_edit.setPlaceholderText("可选：服务端 Ollama 可填写 API Key，本地可留空")
        else:
            self._ai_key_edit.setPlaceholderText("sk-...（必填）")

        is_ollama = provider == "ollama"
        self._ai_refresh_models_btn.setVisible(bool(preset.get("supports_model_discovery")))
        self._ai_ollama_keep_alive_edit.setEnabled(is_ollama)
        self._ai_ollama_num_ctx_edit.setEnabled(is_ollama)
        self._ai_provider_hint.setText(preset.get("help_text", ""))
        self._active_provider_key = provider

    def _save_ai_config(self) -> None:
        cfg = self._collect_ai_config()
        cfg.save()
        self.ai_panel_visibility_changed.emit(cfg.show_assistant)
        InfoBar.success("已保存", "AI 配置已保存", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _refresh_available_models(self) -> None:
        from core.ai_client import AIClient

        provider = self._current_provider_key()
        if provider != "ollama":
            self._populate_model_presets(list_builtin_models(provider))
            return

        try:
            models = AIClient(self._collect_ai_config()).list_available_models_sync()
        except Exception as exc:
            InfoBar.error("探测失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return

        self._populate_model_presets(models, preferred=self._ai_model_edit.text().strip())
        if models and not self._ai_model_edit.text().strip():
            self._ai_model_edit.setText(models[0])
        InfoBar.success("模型已刷新", f"发现 {len(models)} 个可用模型", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _test_ai_connection(self) -> None:
        self._save_ai_config()
        InfoBar.info("测试中", "正在测试 AI 连接…", parent=self._notification_parent(), position=InfoBarPosition.TOP)
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
            InfoBar.success("连接成功", msg, parent=self._notification_parent(), position=InfoBarPosition.TOP)
        else:
            InfoBar.error("连接失败", msg, parent=self._notification_parent(), position=InfoBarPosition.TOP)

    # ── 报告模板方法 ──────────────────────────────────────────

    def refresh_templates(self) -> None:
        """报告模板已迁入分析页；保留空实现以兼容旧调用。"""
        self._tmpl_list.clear()
        self._refresh_ai_tools_panel()

    def _refresh_ai_tools_panel(self) -> None:
        from ai.command_layer import COMMANDS
        from core.global_assets import global_assets

        self._ai_tool_items = []
        for name, cmd in COMMANDS.items():
            self._ai_tool_items.append({
                "source": "builtin",
                "type": "内置命令",
                "name": name,
                "desc": cmd.desc,
                "item": None,
            })

        prompts = global_assets.list_ai_prompts()
        skills = global_assets.list_ai_skills()
        agents = global_assets.list_ai_agents()
        self._ai_tools_project_label.setText(f"全局资源: {global_assets.asset_path}")
        self._ai_tools_summary_label.setText(
            f"内置 {len(COMMANDS)} · Prompt {len(prompts)} · Skill {len(skills)} · Agent {len(agents)}"
        )
        for item in prompts:
            self._ai_tool_items.append({
                "source": "global", "type": "Prompt",
                "name": item.name, "desc": getattr(item, "description", ""), "item": item,
            })
        for item in skills:
            self._ai_tool_items.append({
                "source": "global", "type": "Skill",
                "name": item.name, "desc": getattr(item, "description", ""), "item": item,
            })
        for item in agents:
            self._ai_tool_items.append({
                "source": "global", "type": "Agent",
                "name": item.name, "desc": getattr(item, "description", ""), "item": item,
            })

        self._ai_tool_selector.blockSignals(True)
        self._ai_tool_selector.clear()
        for t in self._ai_tool_items:
            prefix = "【内置】" if t["source"] == "builtin" else f"【{t['type']}】"
            self._ai_tool_selector.addItem(f"{prefix} {t['name']}")
        self._ai_tool_selector.blockSignals(False)

        if self._ai_tool_items:
            self._ai_tool_selector.setCurrentIndex(0)
            self._on_ai_tool_selected(0)
        else:
            self._clear_ai_tool_detail()

    def _clear_ai_tool_detail(self) -> None:
        self._ai_tool_detail_name.setText("—")
        self._ai_tool_detail_type.setText("—")
        self._ai_tool_detail_desc.setText("—")
        self._ai_tool_edit_btn.setEnabled(False)
        self._ai_tool_delete_btn.setEnabled(False)

    def _on_ai_tool_selected(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._ai_tool_items):
            self._clear_ai_tool_detail()
            return
        t = self._ai_tool_items[idx]
        self._ai_tool_detail_name.setText(t["name"])
        self._ai_tool_detail_type.setText(t["type"])
        self._ai_tool_detail_desc.setText(t["desc"] or "（无描述）")
        is_global = t["source"] == "global"
        self._ai_tool_edit_btn.setEnabled(is_global)
        self._ai_tool_delete_btn.setEnabled(is_global)

    def _on_edit_selected_ai_tool(self) -> None:
        idx = self._ai_tool_selector.currentIndex()
        if idx < 0 or idx >= len(self._ai_tool_items):
            return
        t = self._ai_tool_items[idx]
        if t["source"] != "global" or t["item"] is None:
            return
        from ui.dialogs.ai_tool_dialog import AIToolDialog
        dlg = AIToolDialog(self, tool_type=t["type"].lower(), tool_id=t["item"].id)
        if dlg.exec():
            self._refresh_ai_tools_panel()
            self.assets_modified.emit()
            InfoBar.success("已更新", "AI 工具已修改", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _on_delete_selected_ai_tool(self) -> None:
        idx = self._ai_tool_selector.currentIndex()
        if idx < 0 or idx >= len(self._ai_tool_items):
            return
        t = self._ai_tool_items[idx]
        if t["source"] != "global" or t["item"] is None:
            return
        from core.global_assets import global_assets
        tool_type = t["type"].lower()
        if tool_type == "prompt":
            ok = global_assets.delete_ai_prompt(t["item"].id)
        elif tool_type == "skill":
            ok = global_assets.delete_ai_skill(t["item"].id)
        elif tool_type == "agent":
            ok = global_assets.delete_ai_agent(t["item"].id)
        else:
            ok = False
        if not ok:
            return
        self._refresh_ai_tools_panel()
        self.assets_modified.emit()
        tool_label = f'{t["type"]} "{t["name"]}"'
        InfoBar.success("已删除", f"已删除 {tool_label}", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _open_ai_tool_dialog(self, tool_type: Literal["prompt", "skill", "agent"]) -> None:
        from ui.dialogs.ai_tool_dialog import AIToolDialog

        dlg = AIToolDialog(self, tool_type=tool_type)
        if dlg.exec():
            self._refresh_ai_tools_panel()
            self.assets_modified.emit()
            InfoBar.success("已保存", "AI 工具已保存到全局资源", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _on_new_template(self):
        from core.global_assets import global_assets
        from models.schemas import ReportTemplate

        name, ok = TextInputDialog.get_text(self, "新建报告模板", "模板名称:", placeholder="输入模板名称")
        if not ok or not name.strip():
            return
        global_assets.add_report_template(ReportTemplate(name=name.strip(), content="# 报告\n\n**日期：** {{date}}\n"))
        self.refresh_templates()
        self.assets_modified.emit()

    def _on_edit_template(self):
        from core.global_assets import global_assets
        from core.project_manager import project_manager

        idx = self._tmpl_list.currentRow()
        templates = global_assets.list_report_templates()
        if idx < 0 or idx >= len(templates):
            return
        tmpl = templates[idx]
        if tmpl.is_builtin:
            InfoBar.warning("提示", "内置模板不可编辑，请先复制", parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        from ui.dialogs.report_template_dialog import ReportTemplateDialog
        dlg = ReportTemplateDialog(self, template_id=tmpl.id)
        if dlg.exec():
            project_manager.update_report_template(tmpl.id, content=dlg._editor.toPlainText())
            self.assets_modified.emit()

    def _on_delete_template(self):
        from core.global_assets import global_assets
        from core.project_manager import project_manager

        idx = self._tmpl_list.currentRow()
        templates = global_assets.list_report_templates()
        if idx < 0 or idx >= len(templates):
            return
        tmpl = templates[idx]
        if tmpl.is_builtin:
            InfoBar.warning("提示", "内置模板不可删除", parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        project_manager.delete_report_template(tmpl.id)
        self.refresh_templates()
        self.assets_modified.emit()