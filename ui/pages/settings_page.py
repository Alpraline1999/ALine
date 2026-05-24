from typing import Callable, Literal, cast

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QFileDialog,
                               QFrame, QFormLayout, QKeySequenceEdit)
from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from qfluentwidgets import (ComboBox, setTheme, Theme, CardWidget, PushButton,
    BodyLabel, SubtitleLabel, TitleLabel, SmoothScrollArea,
    LineEdit, PrimaryPushButton, InfoBar, InfoBarPosition, PlainTextEdit,
    CheckBox, SettingCard, SettingCardGroup, ExpandGroupSettingCard,
    Slider, SwitchButton, SwitchSettingCard, ToolButton,
    FluentIcon as FIF)

from ui.theme import (
    accent_color,
    apply_application_font_preference,
    apply_platform_visual_overrides,
    body_text_style_sheet,
    border_color,
    card_background_color,
    card_title_style_sheet,
    error_text_style_sheet,
    flat_status_button_style,
    install_fluent_tooltip,
    notification_parent,
    placeholder_color,
    placeholder_text_style_sheet,
    secondary_text_style_sheet,
    text_color,
    warning_color,
)
from ui.widgets.extension_panel import show_extension_load_report_dialog
from core.extension_api import get_extension_load_status, reload_configured_extensions
from ui.dialogs.fluent_dialogs import TextInputDialog
from ui.widgets.focus_commit import install_click_away_focus_commit
from ui.widgets.navigation_stack import PivotStackWidget, SegmentedStackWidget
from ui.page_view_state import SettingsPageViewState
from core.shortcut_manager import shortcut_manager
from core.app_context import get_app_context
from core.ui_preferences import (
    TreeNameDisplayMode,
    get_tree_name_display_mode,
    is_page_tree_focus_mode_enabled,
    set_ui_font_family,
    get_ui_language,
    set_ui_language,
    set_page_tree_focus_mode_enabled,
    set_tree_name_display_mode,
    get_auto_save_enabled,
    set_auto_save_enabled,
    get_auto_save_interval_seconds,
    set_auto_save_interval_seconds,
)
from core.i18n import _, reload_translations
from core.ai.providers import (
    get_provider_preset,
    list_builtin_models,
    list_provider_keys,
)
from ui.pages.settings_page_support import (
    MutableFolderListSettingCard,
    build_ai_tab,
    build_extensions_tab,
    build_general_tab,
    build_shortcuts_tab,
)


class SettingsPage(QWidget):
    """设置页面 - 主题切换、快捷键自定义等配置"""

    shortcuts_changed = Signal()  # 快捷键保存后发出
    tree_display_mode_changed = Signal(str)
    page_tree_focus_mode_changed = Signal(bool)
    language_changed = Signal(str)
    ui_font_changed = Signal(str)
    extensions_reloaded = Signal()
    project_modified = Signal()
    assets_modified = Signal()
    replay_onboarding_requested = Signal()
    auto_save_settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._extension_height_watch_targets: list[QWidget] = []
        self._theme_style_actions: list[Callable[[], None]] = []
        self._view_state = SettingsPageViewState()
        self._title_label = None
        self._theme_label = None
        self._tree_display_mode_label = None
        self._tree_display_mode_combo = None
        self._tree_display_mode_keys = ["wrap", "elide"]
        self._page_tree_focus_mode_label = None
        self._page_tree_focus_mode_card = None
        self._page_tree_focus_mode_checkbox = None
        self._page_tree_focus_mode_hint = None
        self._language_title = None
        self._language_combo = None
        self._language_keys = ["zh_CN", "en_US"]
        self._appearance_title = None
        self._ui_font_title = None
        self._ui_font_combo = None
        self._ui_font_keys = [""]
        self._zoom_card = None
        self._zoom_combo = None
        self._zoom_keys = [1.0, 1.25, 1.5, 1.75, 2.0, 0.0]
        self._extension_card = None
        self._builtin_extension_card = None
        self._external_extension_card = None
        self._extension_other_settings_card = None
        self._builtin_extension_management_card = None
        self._external_extension_management_card = None
        self._extension_tabs = None
        self._external_extension_tabs = None
        self._extension_status_card = None
        self._extension_actions_card = None
        self._extension_title = None
        self._extension_hint = None
        self._builtin_section_hint = None
        self._external_section_hint = None
        self._external_extensions_dirs_card = None
        self._external_extensions_dir_label = None
        self._external_extensions_dir_edit = None
        self._browse_external_extensions_dir_btn = None
        self._external_extensions_enabled_checkbox = None
        self._external_extensions_sandbox_checkbox = None
        self._external_extension_number_decimals_card = None
        self._external_extension_number_decimals_slider = None
        self._external_extension_number_decimals_value_label = None
        self._refresh_external_extensions_btn = None
        self._builtin_extensions_enabled_checkbox = None
        self._extension_empty_hints: dict[str, BodyLabel] = {}
        self._extension_option_layouts: dict[str, QVBoxLayout] = {}
        self._external_extension_empty_hints: dict[str, BodyLabel] = {}
        self._external_extension_option_layouts: dict[str, QVBoxLayout] = {}
        self._builtin_extension_checkboxes: dict[str, CheckBox] = {}
        self._builtin_extension_checkbox_groups: dict[str, list[CheckBox]] = {}
        self._external_extension_checkboxes: dict[str, CheckBox] = {}
        self._external_extension_checkbox_groups: dict[str, list[CheckBox]] = {}
        self._extension_specs_by_source: dict[str, list[dict]] = {"builtin": [], "external": []}
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
        self._shortcuts_editor_card = None
        self._tmpl_card = None
        self._tmpl_list = None
        self.theme_combo = None
        self._shortcut_filter_edit = None
        self._auto_save_group = None
        self._auto_save_group_title = None
        self._auto_save_enable_card = None
        self._auto_save_interval_card = None
        self._auto_save_interval_spin = None
        self._auto_save_interval_unit = None
        self._auto_save_unit_factors = [1, 60, 3600]
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

    @staticmethod
    def _transparent_scroll_style() -> str:
        return "SmoothScrollArea { background: transparent; border: none; }"

    def _notification_parent(self) -> QWidget:
        parent = notification_parent(self)
        return parent if isinstance(parent, QWidget) else self

    def _register_theme_style_action(self, action: Callable[[], None]) -> None:
        self._theme_style_actions.append(action)
        action()

    def _bind_theme_label_style(self, label: QLabel | None, style_factory: Callable[[], str]) -> QLabel | None:
        if label is None:
            return None
        self._register_theme_style_action(
            lambda label=label, style_factory=style_factory: label.setStyleSheet(style_factory())
        )
        return label

    def _bind_setting_card_styles(
        self,
        card: QWidget | None,
        *,
        title_style: Callable[[], str] | None = None,
        content_style: Callable[[], str] | None = None,
    ) -> None:
        if card is None:
            return
        title_label = getattr(card, "titleLabel", None)
        content_label = getattr(card, "contentLabel", None)
        if title_style is not None and isinstance(title_label, QLabel):
            self._bind_theme_label_style(title_label, title_style)
        if content_style is not None and isinstance(content_label, QLabel):
            self._bind_theme_label_style(content_label, content_style)

    def _bind_theme_text_in_widget(
        self,
        widget: QWidget | None,
        text: str,
        style_factory: Callable[[], str],
        *,
        first_only: bool = False,
    ) -> None:
        if widget is None:
            return

        def _apply() -> None:
            matches = [label for label in widget.findChildren(QLabel) if label.text() == text]
            if first_only and matches:
                matches = matches[:1]
            for label in matches:
                label.setStyleSheet(style_factory())

        self._register_theme_style_action(_apply)

    def setup_ui(self):
        tabs = PivotStackWidget(self)
        self._tabs = tabs

        tabs.addTab(build_general_tab(self), "常规")
        tabs.addTab(build_extensions_tab(self), "扩展")
        tabs.addTab(build_ai_tab(self), "AI")
        tabs.addTab(build_shortcuts_tab(self), "快捷键")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(tabs)

        self._load_extension_settings()
        self._load_ai_config()
        self._schedule_extension_category_tab_heights_refresh()
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
        if any(watched is target for target in self._extension_height_watch_targets):
            if event.type() in {QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.LayoutRequest}:
                self._schedule_extension_category_tab_heights_refresh()
        return super().eventFilter(watched, event)

    def _register_extension_height_watch_target(self, widget: QWidget | None) -> None:
        if widget is None or any(widget is target for target in self._extension_height_watch_targets):
            return
        self._extension_height_watch_targets.append(widget)
        widget.installEventFilter(self)

    def _schedule_extension_category_tab_heights_refresh(self) -> None:
        if self._view_state.extension_height_refresh_pending:
            return
        self._view_state.extension_height_refresh_pending = True
        QTimer.singleShot(0, self._refresh_extension_category_tab_heights)

    def _refresh_extension_category_tab_heights(self) -> None:
        self._view_state.extension_height_refresh_pending = False
        if not self.isVisible() or not self.isWidgetType():
            return
        for tabs in (self._extension_tabs, self._external_extension_tabs):
            if tabs is None:
                continue
            try:
                tabs.adjustSize()
                tabs.updateGeometry()
            except RuntimeError:
                continue

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

    def _ai_config_controls_ready(self) -> bool:
        return all(
            hasattr(self, name) and getattr(self, name) is not None
            for name in (
                "_ai_provider_combo",
                "_ai_url_edit",
                "_ai_key_edit",
                "_ai_model_edit",
                "_ai_timeout_edit",
                "_ai_temperature_edit",
                "_ai_top_p_edit",
                "_ai_max_tokens_edit",
                "_ai_system_prompt_edit",
                "_ai_ollama_keep_alive_edit",
                "_ai_ollama_num_ctx_edit",
                "_ai_provider_hint",
                "_ai_refresh_models_btn",
                "_ai_model_preset_combo",
            )
        )

    def _ai_tools_controls_ready(self) -> bool:
        return all(
            hasattr(self, name) and getattr(self, name) is not None
            for name in (
                "_ai_tools_project_label",
                "_ai_tools_summary_label",
                "_ai_tool_selector",
                "_ai_tool_detail_name",
                "_ai_tool_detail_type",
                "_ai_tool_detail_desc",
                "_ai_tool_edit_btn",
                "_ai_tool_delete_btn",
            )
        )

    @staticmethod
    def _attach_setting_card_control(card: SettingCard, widget: QWidget, *, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight) -> None:
        card.hBoxLayout.addWidget(widget, 0, alignment | Qt.AlignmentFlag.AlignVCenter)
        card.hBoxLayout.addSpacing(16)

    @staticmethod
    def _build_setting_card_row(parent: QWidget, *widgets: QWidget) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for widget in widgets:
            layout.addWidget(widget)
        return row

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
        apply_platform_visual_overrides()
        QTimer.singleShot(50, self._update_colors)

    def _update_colors(self):
        """更新界面颜色以适应新主题"""
        for action in self._theme_style_actions:
            action()

        self._apply_shortcut_filter_style()
        # QKeySequenceEdit 样式
        for edit in self._shortcut_edits.values():
            self._apply_shortcut_edit_style(edit, focused=edit.hasFocus())

    def update_theme_colors(self) -> None:
        self._update_colors()

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

    def _on_page_tree_focus_mode_changed(self, _state: int) -> None:
        enabled = bool(self._page_tree_focus_mode_checkbox.isChecked()) if self._page_tree_focus_mode_checkbox is not None else False
        enabled = set_page_tree_focus_mode_enabled(enabled)
        self.page_tree_focus_mode_changed.emit(enabled)

    def _on_language_changed(self, _index: int) -> None:
        if self._language_combo is None:
            return
        idx = self._language_combo.currentIndex()
        if idx < 0 or idx >= len(self._language_keys):
            return
        language = set_ui_language(self._language_keys[idx])
        reload_translations()
        self.refresh_language_ui()
        self.language_changed.emit(language)

    def _on_ui_font_changed(self, _index: int) -> None:
        if self._ui_font_combo is None:
            return
        idx = self._ui_font_combo.currentIndex()
        family = self._ui_font_keys[idx] if 0 <= idx < len(self._ui_font_keys) else ""
        stored_family = set_ui_font_family(family)
        applied_family = apply_application_font_preference(stored_family)
        self.ui_font_changed.emit(applied_family or stored_family)
        from qfluentwidgets import InfoBar, InfoBarPosition
        display_name = applied_family or stored_family or "系统默认"
        InfoBar.info(
            "字体已应用",
            f"界面字体已切换为 {display_name}。",
            parent=self._notification_parent(),
            position=InfoBarPosition.TOP,
        )

    # ── 自动保存 ──────────────────────────────────────────────

    def _on_auto_save_enabled_changed(self, checked: bool) -> None:
        set_auto_save_enabled(bool(checked))
        self.auto_save_settings_changed.emit()

    def _on_auto_save_interval_changed(self, _value: int) -> None:
        self._persist_auto_save_interval()

    def _on_auto_save_interval_unit_changed(self, _index: int) -> None:
        if self._auto_save_interval_spin is None or self._auto_save_interval_unit is None:
            return
        current_seconds = self._auto_save_interval_spin.value() * self._get_auto_save_unit_factor()
        new_idx = self._auto_save_interval_unit.currentIndex()
        if 0 <= new_idx < len(self._auto_save_unit_factors):
            new_factor = self._auto_save_unit_factors[new_idx]
            new_value = max(1, round(current_seconds / new_factor))
            self._auto_save_interval_spin.blockSignals(True)
            self._auto_save_interval_spin.setValue(new_value)
            self._auto_save_interval_spin.blockSignals(False)
        self._persist_auto_save_interval()

    def _get_auto_save_unit_factor(self) -> int:
        if self._auto_save_interval_unit is None:
            return 60
        idx = self._auto_save_interval_unit.currentIndex()
        if 0 <= idx < len(self._auto_save_unit_factors):
            return self._auto_save_unit_factors[idx]
        return 60

    def _persist_auto_save_interval(self) -> None:
        if self._auto_save_interval_spin is None or self._auto_save_interval_unit is None:
            return
        interval_seconds = self._auto_save_interval_spin.value() * self._get_auto_save_unit_factor()
        set_auto_save_interval_seconds(interval_seconds)
        self.auto_save_settings_changed.emit()

    def refresh_language_ui(self) -> None:
        """重建设置页可见文案，确保当前页立即切换到新语言。"""
        layout = self.layout()
        if layout is None:
            return

        current_tab = self._tabs.currentIndex() if self._tabs is not None else 0
        if self._tabs is not None:
            layout.removeWidget(self._tabs)
            self._tabs.setParent(None)
            self._tabs.deleteLater()

        self._theme_style_actions.clear()
        self._extension_height_watch_targets.clear()
        self._shortcut_edits.clear()
        self._shortcut_rows.clear()
        self._shortcut_labels.clear()
        self._conflict_labels.clear()
        self._extension_empty_hints.clear()
        self._extension_option_layouts.clear()
        self._external_extension_empty_hints.clear()
        self._external_extension_option_layouts.clear()
        self._builtin_extension_checkboxes.clear()
        self._builtin_extension_checkbox_groups.clear()
        self._external_extension_checkboxes.clear()
        self._external_extension_checkbox_groups.clear()
        self._extension_specs_by_source = {"builtin": [], "external": []}
        self._title_label = None
        self._theme_label = None
        self._tree_display_mode_label = None
        self._tree_display_mode_combo = None
        self._page_tree_focus_mode_label = None
        self._page_tree_focus_mode_card = None
        self._page_tree_focus_mode_checkbox = None
        self._page_tree_focus_mode_hint = None
        self._language_title = None
        self._language_combo = None
        self._appearance_title = None
        self._ui_font_title = None
        self._ui_font_combo = None
        self._ui_font_keys = [""]
        self._zoom_card = None
        self._zoom_combo = None
        self._zoom_keys = [1.0, 1.25, 1.5, 1.75, 2.0, 0.0]
        self._extension_card = None
        self._builtin_extension_card = None
        self._external_extension_card = None
        self._extension_other_settings_card = None
        self._builtin_extension_management_card = None
        self._external_extension_management_card = None
        self._extension_tabs = None
        self._external_extension_tabs = None
        self._extension_status_card = None
        self._extension_actions_card = None
        self._extension_title = None
        self._extension_hint = None
        self._builtin_section_hint = None
        self._external_section_hint = None
        self._external_extensions_dirs_card = None
        self._external_extensions_dir_label = None
        self._external_extensions_dir_edit = None
        self._browse_external_extensions_dir_btn = None
        self._external_extensions_enabled_checkbox = None
        self._external_extensions_sandbox_checkbox = None
        self._external_extension_number_decimals_card = None
        self._external_extension_number_decimals_slider = None
        self._external_extension_number_decimals_value_label = None
        self._refresh_external_extensions_btn = None
        self._builtin_extensions_enabled_checkbox = None
        self._onboarding_label = None
        self._onboarding_hint = None
        self._replay_onboarding_btn = None
        self._lang_title = None
        self._lang_card = None
        self._lang_placeholder = None
        self._shortcuts_title = None
        self._shortcuts_editor_card = None
        self._tmpl_card = None
        self._tmpl_list = None
        self.theme_combo = None
        self._shortcut_filter_edit = None
        self._auto_save_group = None
        self._auto_save_group_title = None
        self._auto_save_enable_card = None
        self._auto_save_interval_card = None
        self._auto_save_interval_spin = None
        self._auto_save_interval_unit = None
        self._provider_keys = list_provider_keys()

        self.setup_ui()
        if self._tabs is not None and 0 <= current_tab < self._tabs.count():
            self._tabs.setCurrentIndex(current_tab)

    def _clear_builtin_extension_options(self) -> None:
        self._builtin_extension_checkboxes.clear()
        self._builtin_extension_checkbox_groups.clear()
        self._external_extension_checkboxes.clear()
        self._external_extension_checkbox_groups.clear()
        for list_widget in [*self._extension_option_layouts.values(), *self._external_extension_option_layouts.values()]:
            list_widget.clear()

    def _register_extension_checkbox(self, source: str, spec_id: str, checkbox: CheckBox) -> None:
        checkbox_map = self._builtin_extension_checkboxes if source == "builtin" else self._external_extension_checkboxes
        group_map = self._builtin_extension_checkbox_groups if source == "builtin" else self._external_extension_checkbox_groups
        if spec_id not in checkbox_map:
            checkbox_map[spec_id] = checkbox
        group_map.setdefault(spec_id, []).append(checkbox)
        checkbox.stateChanged.connect(lambda state, s=source, extension_id=spec_id: self._sync_extension_checkbox_group(s, extension_id, state))

    def _sync_extension_checkbox_group(self, source: str, spec_id: str, state: int) -> None:
        group_map = self._builtin_extension_checkbox_groups if source == "builtin" else self._external_extension_checkbox_groups
        for checkbox in group_map.get(spec_id, []):
            if checkbox.checkState() == state:
                continue
            checkbox.blockSignals(True)
            checkbox.setCheckState(Qt.CheckState(state))
            checkbox.blockSignals(False)

    @staticmethod
    def _extension_spec_display_name(spec: dict, category: str) -> str:
        category_names = [str(item).strip() for item in spec.get("names_by_category", {}).get(category, []) if str(item).strip()]
        if category_names:
            return " / ".join(category_names)
        return str(spec.get("name") or spec.get("id") or "扩展").strip()

    @staticmethod
    def _extension_spec_tooltip(spec: dict, category: str) -> str:
        tooltip_lines = [str(spec.get("file_name") or "")]
        type_ids = [str(item).strip() for item in spec.get("type_ids_by_category", {}).get(category, []) if str(item).strip()]
        if type_ids:
            tooltip_lines.append(f"类型: {', '.join(type_ids)}")
        load_error = str(spec.get("load_error") or "").strip()
        if load_error:
            tooltip_lines.append(f"探测失败: {load_error}")
        return "\n".join(line for line in tooltip_lines if line)

    def _rebuild_builtin_extension_options(
        self,
        builtin_specs: list[dict],
        external_specs: list[dict],
        disabled_builtin_ids: list[str],
        disabled_external_ids: list[str],
    ) -> None:
        self._clear_builtin_extension_options()
        self._extension_specs_by_source = {"builtin": list(builtin_specs), "external": list(external_specs)}

        disabled_markers = {
            "builtin": {str(item).strip() for item in disabled_builtin_ids},
            "external": {str(item).strip() for item in disabled_external_ids},
        }
        source_enabled = {
            "builtin": bool(self._builtin_extensions_enabled_checkbox is not None and self._builtin_extensions_enabled_checkbox.isChecked()),
            "external": bool(self._external_extensions_enabled_checkbox is not None and self._external_extensions_enabled_checkbox.isChecked()),
        }

        from PySide6.QtWidgets import QListWidgetItem
        from qfluentwidgets import CheckBox

        for category, list_widget in self._extension_option_layouts.items():
            category_specs = [spec for spec in builtin_specs if category in list(spec.get("categories") or [])]
            hint = self._extension_empty_hints.get(category)
            if hint is not None:
                hint.setVisible(not category_specs)
            for spec in category_specs:
                spec_id = str(spec.get("id") or "").strip()
                if not spec_id:
                    continue
                item = QListWidgetItem(list_widget)
                checkbox = CheckBox(self._extension_spec_display_name(spec, category))
                checkbox.setChecked(spec_id not in disabled_markers["builtin"])
                checkbox.setEnabled(source_enabled["builtin"])
                checkbox.setToolTip(self._extension_spec_tooltip(spec, category))
                install_fluent_tooltip(checkbox, delay=400)
                item.setSizeHint(checkbox.sizeHint())
                list_widget.addItem(item)
                list_widget.setItemWidget(item, checkbox)
                self._register_extension_checkbox("builtin", spec_id, checkbox)

        for category, list_widget in self._external_extension_option_layouts.items():
            category_specs = [spec for spec in external_specs if category in list(spec.get("categories") or [])]
            hint = self._external_extension_empty_hints.get(category)
            if hint is not None:
                hint.setVisible(not category_specs)
            for spec in category_specs:
                spec_id = str(spec.get("id") or "").strip()
                if not spec_id:
                    continue
                item = QListWidgetItem(list_widget)
                checkbox = CheckBox(self._extension_spec_display_name(spec, category))
                checkbox.setChecked(spec_id not in disabled_markers["external"])
                checkbox.setEnabled(source_enabled["external"])
                checkbox.setToolTip(self._extension_spec_tooltip(spec, category))
                install_fluent_tooltip(checkbox, delay=400)
                item.setSizeHint(checkbox.sizeHint())
                list_widget.addItem(item)
                list_widget.setItemWidget(item, checkbox)
                self._register_extension_checkbox("external", spec_id, checkbox)
        self._schedule_extension_category_tab_heights_refresh()

    def _on_open_extension_manager(self, source: str) -> None:
        from ui.pages.settings_page_support import ExtensionManageDialog
        dialog = ExtensionManageDialog(self, source=source, parent=self)
        dialog.exec()

    def _on_builtin_extensions_enabled_changed(self, *_args) -> None:
        enabled = bool(
            self._builtin_extensions_enabled_checkbox is not None
            and self._builtin_extensions_enabled_checkbox.isChecked()
        )
        for switch in self._builtin_extension_checkboxes.values():
            if isinstance(switch, SwitchButton):
                switch.setEnabled(enabled)

    def _on_external_extensions_enabled_changed(self, *_args) -> None:
        enabled = bool(
            self._external_extensions_enabled_checkbox is not None
            and self._external_extensions_enabled_checkbox.isChecked()
        )
        for switch in self._external_extension_checkboxes.values():
            if isinstance(switch, SwitchButton):
                switch.setEnabled(enabled)

    def _load_extension_settings(self) -> None:
        from core.extension_api import list_builtin_extension_specs, list_external_extension_specs
        from core.extension_settings import (
            get_builtin_extension_settings,
            get_external_extension_sandbox_enabled,
            get_extension_number_decimals,
            get_external_extension_settings,
            get_external_extensions_directories,
        )

        load_builtin, disabled_extension_ids = get_builtin_extension_settings()
        load_external, disabled_external_ids = get_external_extension_settings()
        sandbox_enabled = get_external_extension_sandbox_enabled()
        if self._builtin_extensions_enabled_checkbox is not None:
            self._builtin_extensions_enabled_checkbox.blockSignals(True)
            self._builtin_extensions_enabled_checkbox.setChecked(load_builtin)
            self._builtin_extensions_enabled_checkbox.blockSignals(False)
        if self._external_extensions_enabled_checkbox is not None:
            self._external_extensions_enabled_checkbox.blockSignals(True)
            self._external_extensions_enabled_checkbox.setChecked(load_external)
            self._external_extensions_enabled_checkbox.blockSignals(False)
        if self._external_extensions_sandbox_checkbox is not None:
            self._external_extensions_sandbox_checkbox.blockSignals(True)
            self._external_extensions_sandbox_checkbox.setChecked(sandbox_enabled)
            self._external_extensions_sandbox_checkbox.blockSignals(False)
        if self._external_extensions_dirs_card is not None:
            self._external_extensions_dirs_card.setFolders([str(path) for path in get_external_extensions_directories()])
        self._set_external_extension_number_decimals(get_extension_number_decimals())
        self._rebuild_builtin_extension_options(
            list_builtin_extension_specs(),
            list_external_extension_specs(),
            disabled_extension_ids,
            disabled_external_ids,
        )
        self._on_builtin_extensions_enabled_changed()
        self._on_external_extensions_enabled_changed()
        self._refresh_extension_status_summary()

    def _refresh_extension_status_summary(self) -> None:
        status = get_extension_load_status()
        registered_count = status["registered_count"]
        error_count = status["error_count"]
        source_summary = status.get("source_summary") or {}
        loaded_counts = dict(source_summary.get("loaded_extension_counts") or {})
        builtin_count = int(loaded_counts.get("builtin", 0) or 0)
        external_count = int(loaded_counts.get("external", 0) or 0)
        source_suffix = (
            f"（内置 {builtin_count} / 外部 {external_count}）"
            if builtin_count + external_count > 0
            else ""
        )
        if error_count:
            self._extension_status_summary_btn.setText(f"当前扩展状态：{registered_count} 项可用{source_suffix}，{error_count} 项失败")
            self._extension_status_summary_btn.setStyleSheet(flat_status_button_style(warning_color()))
        elif registered_count:
            self._extension_status_summary_btn.setText(f"当前扩展状态：{registered_count} 项可用{source_suffix}")
            self._extension_status_summary_btn.setStyleSheet(flat_status_button_style(accent_color()))
        else:
            self._extension_status_summary_btn.setText("当前扩展状态：未发现可用项")
            self._extension_status_summary_btn.setStyleSheet(flat_status_button_style(placeholder_color()))
        self._extension_status_summary_btn.setEnabled(bool(status["details"].get("loaded") or status["details"].get("errors")))

    def _show_extension_status_details(self) -> None:
        show_extension_load_report_dialog(self, "扩展加载详情")

    def _refresh_external_extension_specs(self) -> None:
        from core.extension_api import list_external_extension_specs

        disabled_builtin_ids = [spec_id for spec_id, sw in self._builtin_extension_checkboxes.items() if isinstance(sw, SwitchButton) and not sw.isChecked()]
        disabled_external_ids = [spec_id for spec_id, sw in self._external_extension_checkboxes.items() if isinstance(sw, SwitchButton) and not sw.isChecked()]
        external_dirs = self._current_external_extensions_directories()
        external_specs = list_external_extension_specs(external_dirs or None)
        self._rebuild_builtin_extension_options(
            self._extension_specs_by_source.get("builtin", []),
            external_specs,
            disabled_builtin_ids,
            disabled_external_ids,
        )
        self._on_builtin_extensions_enabled_changed()
        self._on_external_extensions_enabled_changed()
        InfoBar.success(
            "已刷新",
            f"检测到 {len(external_specs)} 个扩展文件",
            parent=self._notification_parent(),
            position=InfoBarPosition.TOP,
        )

    def _on_add_external_extension(self) -> None:
        from core.extension_settings import add_external_extension_file
        from pathlib import Path

        dialog = QFileDialog(self, _("选择扩展文件"), "", "Python 文件 (*.py)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)

        if dialog.exec() != int(QFileDialog.DialogCode.Accepted):
            return

        selected = dialog.selectedFiles()
        if not selected:
            return

        source_path = selected[0]
        try:
            target_path = add_external_extension_file(source_path)
        except (FileExistsError, ValueError, OSError) as exc:
            InfoBar.error(
                _("添加失败"),
                str(exc),
                parent=self._notification_parent(),
                position=InfoBarPosition.TOP,
            )
            return

        InfoBar.success(
            _("已添加"),
            str(target_path),
            parent=self._notification_parent(),
            position=InfoBarPosition.TOP,
        )
        self._refresh_external_extension_specs()

    def _on_edit_external_extension(self, spec_id: str) -> None:
        from core.extension_settings import resolve_external_extension_path
        import subprocess, sys

        file_path = resolve_external_extension_path(spec_id)
        if file_path is None:
            InfoBar.error(
                _("未找到文件"),
                _("无法定位外部扩展文件: ") + spec_id,
                parent=self._notification_parent(),
                position=InfoBarPosition.TOP,
            )
            return

        try:
            if sys.platform == "win32":
                subprocess.Popen(["notepad", str(file_path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(file_path)])
            else:
                subprocess.Popen(["xdg-open", str(file_path)])
        except OSError:
            InfoBar.error(
                _("无法打开"),
                _("请手动编辑文件: ") + str(file_path),
                parent=self._notification_parent(),
                position=InfoBarPosition.TOP,
            )

    def _on_delete_external_extension(self, spec_id: str) -> None:
        from core.extension_settings import delete_external_extension_file, resolve_external_extension_path

        file_path = resolve_external_extension_path(spec_id)
        if file_path is None:
            InfoBar.error(
                _("未找到文件"),
                _("无法定位外部扩展文件: ") + spec_id,
                parent=self._notification_parent(),
                position=InfoBarPosition.TOP,
            )
            return

        from qfluentwidgets import MessageBox

        title = _("确认删除")
        content = _("确定要删除外部扩展文件?\n") + str(file_path.name)
        msg = MessageBox(title, content, self)
        if msg.exec():
            try:
                delete_external_extension_file(file_path)
            except (PermissionError, FileNotFoundError, ValueError) as exc:
                InfoBar.error(
                    _("删除失败"),
                    str(exc),
                    parent=self._notification_parent(),
                    position=InfoBarPosition.TOP,
                )
                return

            InfoBar.success(
                _("已删除"),
                str(file_path.name),
                parent=self._notification_parent(),
                position=InfoBarPosition.TOP,
            )
            self._refresh_external_extension_specs()

    def _on_interface_scale_changed(self, index: int) -> None:
        keys = getattr(self, "_zoom_keys", [1.0, 1.25, 1.5, 1.75, 2.0, 0.0])
        # index: 0=100%, 1=125%, 2=150%, 3=175%, 4=200%, 5=跟随系统
        if index < 0 or index >= len(keys):
            return
        scale = keys[index]
        from core.ui_preferences import set_interface_scale
        set_interface_scale(scale)
        InfoBar.success(
            _("缩放已设置"),
            _("界面缩放将在重启后生效。"),
            parent=self._notification_parent(),
            position=InfoBarPosition.TOP,
            duration=3000,
        )

    def _current_external_extensions_directories(self) -> list[str]:
        if self._external_extensions_dirs_card is None:
            return []
        return [str(folder).strip() for folder in list(self._external_extensions_dirs_card.folders) if str(folder).strip()]

    def _set_external_extension_number_decimals(self, value: int) -> None:
        normalized = max(0, min(12, int(value)))
        if self._external_extension_number_decimals_slider is not None:
            self._external_extension_number_decimals_slider.blockSignals(True)
            self._external_extension_number_decimals_slider.setValue(normalized)
            self._external_extension_number_decimals_slider.blockSignals(False)
        if self._external_extension_number_decimals_value_label is not None:
            self._external_extension_number_decimals_value_label.setText(str(normalized))

    def _on_external_extension_number_decimals_changed(self, value: int) -> None:
        if self._external_extension_number_decimals_value_label is not None:
            self._external_extension_number_decimals_value_label.setText(str(int(value)))

    def _save_extension_settings(self) -> None:
        from core.extension_settings import (
            set_builtin_extension_settings,
            set_external_extension_sandbox_enabled,
            set_extension_number_decimals,
            set_external_extension_settings,
            set_external_extensions_directories,
        )

        load_builtin = bool(
            self._builtin_extensions_enabled_checkbox is not None
            and self._builtin_extensions_enabled_checkbox.isChecked()
        )
        load_external = bool(
            self._external_extensions_enabled_checkbox is not None
            and self._external_extensions_enabled_checkbox.isChecked()
        )
        disabled_extension_ids = [
            spec_id for spec_id, sw in self._builtin_extension_checkboxes.items()
            if isinstance(sw, SwitchButton) and not sw.isChecked()
        ]
        disabled_external_ids = [
            spec_id for spec_id, sw in self._external_extension_checkboxes.items()
            if isinstance(sw, SwitchButton) and not sw.isChecked()
        ]

        external_dirs = self._current_external_extensions_directories()
        try:
            set_external_extensions_directories(external_dirs)
        except ValueError as exc:
            InfoBar.error("扩展设置保存失败", str(exc), parent=self._notification_parent(), position=InfoBarPosition.TOP)
            return
        set_builtin_extension_settings(load_builtin, disabled_extension_ids)
        set_external_extension_settings(load_external, disabled_external_ids)
        if self._external_extensions_sandbox_checkbox is not None:
            set_external_extension_sandbox_enabled(self._external_extensions_sandbox_checkbox.isChecked())
        if self._external_extension_number_decimals_slider is not None:
            set_extension_number_decimals(self._external_extension_number_decimals_slider.value())
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
        if not self._ai_config_controls_ready():
            return self._active_provider_key
        idx = self._ai_provider_combo.currentIndex()
        if 0 <= idx < len(self._provider_keys):
            return self._provider_keys[idx]
        return self._active_provider_key

    def _populate_model_presets(self, models: list[str], preferred: str = "") -> None:
        if not self._ai_config_controls_ready():
            return
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
        if not self._ai_config_controls_ready():
            return
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

        if not self._ai_config_controls_ready():
            return AIConfig()

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
            max_tokens=self._parse_int(self._ai_max_tokens_edit.text(), 0, minimum=0),
            system_prompt=self._ai_system_prompt_edit.toPlainText().strip(),
            ollama_keep_alive=self._ai_ollama_keep_alive_edit.text().strip() or "5m",
            ollama_num_ctx=self._parse_int(self._ai_ollama_num_ctx_edit.text(), 4096, minimum=1),
        )

    def _load_ai_config(self) -> None:
        if not self._ai_config_controls_ready():
            return
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
        self._on_ai_provider_changed(idx)

    def _on_ai_provider_changed(self, idx: int) -> None:
        if not self._ai_config_controls_ready():
            return
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
        if not self._ai_config_controls_ready():
            return
        cfg = self._collect_ai_config()
        cfg.save()
        InfoBar.success("已保存", "AI 配置已保存", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _refresh_available_models(self) -> None:
        if not self._ai_config_controls_ready():
            return
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
        if not self._ai_config_controls_ready():
            return
        self._save_ai_config()
        if hasattr(self, "_ai_test_progress"):
            self._ai_test_progress.show()
        InfoBar.info("测试中", "正在测试 AI 连接…", parent=self._notification_parent(), position=InfoBarPosition.TOP)
        import asyncio
        from core.ai_client import AIClient
        client = AIClient()

        async def _test():
            return await client.test_connection()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _test())
                    ok, msg = future.result(timeout=30)
            else:
                ok, msg = loop.run_until_complete(_test())
        except Exception as e:
            ok, msg = False, str(e)

        if hasattr(self, "_ai_test_progress"):
            self._ai_test_progress.hide()
        if ok:
            InfoBar.success("连接成功", msg, parent=self._notification_parent(), position=InfoBarPosition.TOP)
        else:
            InfoBar.error("连接失败", msg, parent=self._notification_parent(), position=InfoBarPosition.TOP)

    # ── 报告模板方法 ──────────────────────────────────────────

    def refresh_templates(self) -> None:
        """报告模板已迁入分析页；保留兼容入口以承接旧刷新调用。"""
        tmpl_list = getattr(self, "_tmpl_list", None)
        if tmpl_list is not None:
            tmpl_list.clear()
        self._refresh_ai_tools_panel()

    def _refresh_ai_tools_panel(self) -> None:
        if not self._ai_tools_controls_ready():
            return
        from core.global_assets import global_assets

        self._ai_tool_items = []
        prompts = global_assets.list_ai_prompts()
        self._ai_tools_project_label.setText(f"全局资源: {global_assets.asset_path}")
        self._ai_tools_summary_label.setText(f"Prompt {len(prompts)}")
        for item in prompts:
            self._ai_tool_items.append({
                "source": "global", "type": "Prompt",
                "name": item.name, "desc": getattr(item, "description", ""), "item": item,
            })

        self._ai_tool_selector.blockSignals(True)
        self._ai_tool_selector.clear()
        for t in self._ai_tool_items:
            self._ai_tool_selector.addItem(f"【Prompt】 {t['name']}")
        self._ai_tool_selector.blockSignals(False)

        if self._ai_tool_items:
            self._ai_tool_selector.setCurrentIndex(0)
            self._on_ai_tool_selected(0)
        else:
            self._clear_ai_tool_detail()

    def _clear_ai_tool_detail(self) -> None:
        if not self._ai_tools_controls_ready():
            return
        self._ai_tool_detail_name.setText("—")
        self._ai_tool_detail_type.setText("—")
        self._ai_tool_detail_desc.setText("—")
        self._ai_tool_edit_btn.setEnabled(False)
        self._ai_tool_delete_btn.setEnabled(False)

    def _on_ai_tool_selected(self, idx: int) -> None:
        if not self._ai_tools_controls_ready():
            return
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
        dlg = AIToolDialog(self, tool_id=t["item"].id)
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
        ok = global_assets.delete_ai_prompt(t["item"].id)
        if not ok:
            return
        self._refresh_ai_tools_panel()
        self.assets_modified.emit()
        tool_label = f'{t["type"]} "{t["name"]}"'
        InfoBar.success("已删除", f"已删除 {tool_label}", parent=self._notification_parent(), position=InfoBarPosition.TOP)

    def _open_ai_tool_dialog(self) -> None:
        from ui.dialogs.ai_tool_dialog import AIToolDialog

        dlg = AIToolDialog(self)
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
        project_manager = get_app_context().project_manager

        tmpl_list = getattr(self, "_tmpl_list", None)
        if tmpl_list is None:
            return
        idx = tmpl_list.currentRow()
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
        project_manager = get_app_context().project_manager

        tmpl_list = getattr(self, "_tmpl_list", None)
        if tmpl_list is None:
            return
        idx = tmpl_list.currentRow()
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
