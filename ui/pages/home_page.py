from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QFrame
from PySide6.QtCore import Qt, Signal
from qfluentwidgets import (PrimaryPushButton, PushButton, FluentIcon as FIF,
    BodyLabel, LargeTitleLabel, SubtitleLabel, SmoothScrollArea,
    InfoBar, TeachingTipTailPosition)

from core.extension_api import get_extension_load_status
from core.ui_preferences import is_home_onboarding_completed, set_home_onboarding_completed
from ui.theme import (
    accent_color,
    make_empty_state_label,
    make_hint_label,
    make_section_label,
    placeholder_color,
    secondary_color,
    text_color,
)
from ui.dialogs.fluent_dialogs import TextInputDialog
from core.project_manager import project_manager
from core.recent_projects import load_recent, remove_recent
from ui.widgets.extension_panel import show_extension_load_report_dialog
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController


class HomePage(QWidget):
    """首页 - 项目列表/新建/打开"""

    project_created = Signal(str)  # 项目创建/打开后信号
    project_opened = Signal(str)  # 项目打开后信号
    quick_start_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title = None
        self._subtitle = None
        self._recent_label = None
        self._no_recent = None
        self._new_btn = None
        self._open_btn = None
        self._guide_toggle_btn = None
        self._guide_row = None
        self._welcome_card = None
        self._quick_start_card = None
        self._welcome_intro = None
        self._welcome_steps = None
        self._quick_start_intro = None
        self._extension_status_label = None
        self._extension_detail_btn = None
        self._quick_start_step_labels = []
        self._goto_data_btn = None
        self._goto_process_btn = None
        self._goto_analysis_btn = None
        self._recent_scroll = None
        self._recent_items_widget = None
        self._recent_items_layout = None
        self.setup_ui()
        self._onboarding_controller = PageOnboardingController(
            self,
            "home",
            self._home_onboarding_steps,
            is_completed=is_home_onboarding_completed,
            mark_completed=set_home_onboarding_completed,
        )

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        # 左侧边距需要足够大，避免被导航栏遮挡
        layout.setContentsMargins(40, 40, 40, 40)

        # 标题
        self._title = LargeTitleLabel("ALine", self)
        layout.addWidget(self._title, alignment=Qt.AlignCenter)

        # 副标题
        self._subtitle = SubtitleLabel("科研数据管理工具", self)
        layout.addWidget(self._subtitle, alignment=Qt.AlignCenter)

        layout.addSpacing(24)

        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)

        self._new_btn = PrimaryPushButton("新建项目", self)
        self._new_btn.setFixedWidth(150)
        self._new_btn.clicked.connect(self.on_new_project)
        btn_layout.addWidget(self._new_btn)

        self._open_btn = PrimaryPushButton("打开项目", self)
        self._open_btn.setFixedWidth(150)
        self._open_btn.clicked.connect(self.on_open_project)
        btn_layout.addWidget(self._open_btn)

        layout.addLayout(btn_layout)
        btn_layout.setAlignment(Qt.AlignCenter)

        self._build_guide_cards(layout)

        # 最近项目
        layout.addSpacing(12)
        recent_header = QHBoxLayout()
        self._recent_label = BodyLabel("最近项目", self)
        recent_header.addWidget(self._recent_label)
        recent_header.addStretch()
        layout.addLayout(recent_header)

        # 无最近项目占位
        self._no_recent = make_empty_state_label("暂无最近项目", self)
        layout.addWidget(self._no_recent, alignment=Qt.AlignLeft)

        # 最近项目scroll区域
        self._recent_scroll = SmoothScrollArea(self)
        self._recent_scroll.setWidgetResizable(True)
        self._recent_scroll.setFrameShape(QFrame.NoFrame)
        self._recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._recent_scroll.setMaximumHeight(280)
        self._recent_scroll.hide()

        self._recent_items_widget = QWidget()
        self._recent_items_layout = QVBoxLayout(self._recent_items_widget)
        self._recent_items_layout.setSpacing(4)
        self._recent_items_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_items_layout.addStretch()
        self._recent_scroll.setWidget(self._recent_items_widget)
        self._recent_scroll.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")
        self._recent_items_widget.setStyleSheet("background: transparent;")
        layout.addWidget(self._recent_scroll)

        layout.addStretch()

        # 初始应用主题颜色 & 加载最近项目
        self._apply_theme_colors()
        self._refresh_extension_summary()
        self.refresh_recent()

    def showEvent(self, event):
        """页面显示时刷新最近项目"""
        super().showEvent(event)
        self._refresh_extension_summary()
        self.refresh_recent()
        self._onboarding_controller.schedule_auto_start()

    def _build_guide_cards(self, layout: QVBoxLayout) -> None:
        self._guide_row = QWidget(self)
        guide_layout = QHBoxLayout(self._guide_row)
        guide_layout.setContentsMargins(0, 0, 0, 0)
        guide_layout.setSpacing(28)

        self._welcome_card = QWidget(self._guide_row)
        welcome_layout = QVBoxLayout(self._welcome_card)
        welcome_layout.setContentsMargins(0, 0, 0, 0)
        welcome_layout.setSpacing(8)
        welcome_layout.addWidget(make_section_label("ALine工作台", self._welcome_card))
        self._welcome_intro = BodyLabel("把项目、数据、处理、绘图和分析放在同一条工作流里，减少工具切换和文件散落。", self._welcome_card)
        self._welcome_intro.setWordWrap(True)
        welcome_layout.addWidget(self._welcome_intro)
        self._welcome_steps = BodyLabel(
            "建议先建立项目上下文，再进入数据管理导入原始数据；后续处理、可视化和分析页面会沿用同一份项目资产继续工作。",
            self._welcome_card,
        )
        self._welcome_steps.setWordWrap(True)
        welcome_layout.addWidget(self._welcome_steps)
        welcome_layout.addStretch(1)

        self._quick_start_card = QWidget(self._guide_row)
        quick_layout = QVBoxLayout(self._quick_start_card)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        quick_layout.setSpacing(8)
        quick_layout.addWidget(make_section_label("工作流入口", self._quick_start_card))
        self._quick_start_intro = make_hint_label("常用路径可以直接从这里进入；如果你是第一次打开，功能页会在首次进入时给出简短提示。", self._quick_start_card)
        quick_layout.addWidget(self._quick_start_intro)

        for index, text in enumerate([
            "先创建或打开项目，把数据、图表和结果放进同一个上下文。",
            "去数据管理导入、预览和整理原始数据，再按需进入处理页。",
            "需要成图或输出摘要时，再切到可视化和分析页面继续。",
        ], start=1):
            step_label = BodyLabel(f"{index}. {text}", self._quick_start_card)
            step_label.setWordWrap(True)
            quick_layout.addWidget(step_label)
            self._quick_start_step_labels.append(step_label)

        quick_actions = QHBoxLayout()
        quick_actions.setSpacing(10)
        self._goto_data_btn = PushButton("数据管理", self._quick_start_card)
        self._goto_data_btn.clicked.connect(lambda: self._request_quick_start("data"))
        quick_actions.addWidget(self._goto_data_btn)
        self._goto_process_btn = PushButton("数据处理", self._quick_start_card)
        self._goto_process_btn.clicked.connect(lambda: self._request_quick_start("process"))
        quick_actions.addWidget(self._goto_process_btn)
        self._goto_analysis_btn = PushButton("数据分析", self._quick_start_card)
        self._goto_analysis_btn.clicked.connect(lambda: self._request_quick_start("analysis"))
        quick_actions.addWidget(self._goto_analysis_btn)
        quick_layout.addLayout(quick_actions)

        status_row = QHBoxLayout()
        self._extension_status_label = make_hint_label("", self._quick_start_card)
        status_row.addWidget(self._extension_status_label, 1)
        self._extension_detail_btn = PushButton("查看详情", self._quick_start_card)
        self._extension_detail_btn.clicked.connect(self._show_extension_details)
        status_row.addWidget(self._extension_detail_btn)
        quick_layout.addLayout(status_row)
        quick_layout.addStretch(1)

        guide_layout.addWidget(self._welcome_card, 1)
        guide_layout.addWidget(self._quick_start_card, 1)
        layout.addWidget(self._guide_row)

    def _apply_theme_colors(self):
        """应用当前主题颜色"""
        tc = text_color()
        sc = secondary_color()
        pc = placeholder_color()
        self._title.setStyleSheet(f"font-size: 48px; font-weight: 700; color: {tc};")
        self._subtitle.setStyleSheet(f"font-size: 18px; color: {sc};")
        self._recent_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {tc};")
        self._no_recent.setStyleSheet(f"color: {pc}; font-size: 12px;")
        if self._welcome_card is not None:
            self._welcome_card.setStyleSheet("background: transparent; border: none;")
        if self._quick_start_card is not None:
            self._quick_start_card.setStyleSheet("background: transparent; border: none;")
        if self._welcome_intro is not None:
            self._welcome_intro.setStyleSheet(f"color: {tc}; font-size: 14px; font-weight: 600;")
        if self._welcome_steps is not None:
            self._welcome_steps.setStyleSheet(f"color: {sc}; font-size: 12px;")
        if self._quick_start_intro is not None:
            self._quick_start_intro.setStyleSheet(f"color: {pc}; font-size: 11px;")
        for step_label in self._quick_start_step_labels:
            step_label.setStyleSheet(f"color: {tc}; font-size: 13px;")

    def refresh_recent(self):
        """刷新最近项目列表"""
        recents = load_recent()

        if not recents:
            self._no_recent.show()
            self._recent_scroll.hide()
            return

        self._no_recent.hide()
        self._recent_scroll.show()

        # 清除旧条目（保留 stretch）
        while self._recent_items_layout.count() > 1:
            item = self._recent_items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tc = text_color()
        sc = secondary_color()
        pc = placeholder_color()

        for entry in recents:
            path = entry.get("path", "")
            name = entry.get("name", "未知项目")
            opened_at = entry.get("opened_at", "")[:10]

            row = QWidget()
            row.setFixedHeight(54)
            row.setStyleSheet(
                f"QWidget {{border-radius: 6px; background: transparent;}}"
                f"QWidget:hover {{background: rgba(128,128,128,0.12);}}"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(8, 4, 8, 4)
            row_layout.setSpacing(12)

            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            name_lbl = BodyLabel(name)
            name_lbl.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {tc};")
            path_lbl = BodyLabel(path)
            path_lbl.setStyleSheet(f"font-size: 11px; color: {pc};")
            path_lbl.setToolTip(path)
            info_col.addWidget(name_lbl)
            info_col.addWidget(path_lbl)
            row_layout.addLayout(info_col, 1)

            date_lbl = BodyLabel(opened_at)
            date_lbl.setStyleSheet(f"font-size: 11px; color: {sc};")
            date_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(date_lbl)

            remove_btn = PushButton("", row)
            remove_btn.setFixedSize(24, 24)
            remove_btn.setIcon(FIF.CLOSE.icon())
            remove_btn.setStyleSheet("border: none; background: transparent;")
            remove_btn.setToolTip("从列表移除")
            remove_btn.clicked.connect(lambda _, p=path: self._on_remove_recent(p))
            row_layout.addWidget(remove_btn)

            # 点击行打开项目（排除删除按钮区域）
            row.mousePressEvent = lambda e, p=path: self._on_open_recent(p)
            row.setCursor(Qt.PointingHandCursor)

            self._recent_items_layout.insertWidget(
                self._recent_items_layout.count() - 1, row
            )

    def _refresh_extension_summary(self) -> None:
        if self._extension_status_label is None:
            return
        status = get_extension_load_status()
        registered_count = status["registered_count"]
        error_count = status["error_count"]
        if error_count:
            self._extension_status_label.setText(f"扩展状态：已注册 {registered_count} 项，本轮扫描有 {error_count} 个失败文件")
            self._extension_status_label.setStyleSheet("color: #D83B01; font-size: 12px;")
        elif registered_count:
            self._extension_status_label.setText(f"扩展状态：已注册 {registered_count} 项，最近一次扫描未发现加载错误")
            self._extension_status_label.setStyleSheet(f"color: {accent_color()}; font-size: 12px;")
        else:
            self._extension_status_label.setText("扩展状态：当前没有已注册扩展")
            self._extension_status_label.setStyleSheet(f"color: {placeholder_color()}; font-size: 12px;")
        if self._extension_detail_btn is not None:
            details = status["details"]
            self._extension_detail_btn.setEnabled(bool(details.get("loaded") or details.get("errors")))

    def _show_extension_details(self) -> None:
        show_extension_load_report_dialog(self, "扩展加载详情")

    def start_onboarding(self, force: bool = False) -> None:
        self._onboarding_controller.start(force=force)

    def _home_onboarding_steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                lambda: self._new_btn,
                TeachingTipTailPosition.BOTTOM,
                "先建立项目上下文",
                "ALine 的数据、图表、处理结果都会挂在项目里；先新建项目，后面的操作就不会散。",
            ),
            OnboardingStep(
                lambda: self._open_btn,
                TeachingTipTailPosition.BOTTOM,
                "也可以直接接着做",
                "如果已经有 .aline 项目，从这里恢复上次工作状态，项目树和页面上下文会一起回来。",
            ),
            OnboardingStep(
                lambda: self._recent_label,
                TeachingTipTailPosition.BOTTOM,
                "最近项目帮你回到现场",
                "常做的项目会保留在这里，适合快速回到上一次工作点，不需要重新定位文件。",
            ),
            OnboardingStep(
                lambda: self._goto_data_btn,
                TeachingTipTailPosition.BOTTOM,
                "先从数据入口推进",
                "导入原始数据、检查预览、整理节点，一般都从数据管理页开始；后续页面会复用同一份项目资产。",
            ),
            OnboardingStep(
                lambda: self._goto_process_btn,
                TeachingTipTailPosition.BOTTOM,
                "处理、可视化和分析按需切换",
                "需要平滑、裁剪或重采样时去处理页；需要成图或输出摘要时，再切到可视化和分析页。",
            ),
            OnboardingStep(
                lambda: self._extension_detail_btn,
                TeachingTipTailPosition.LEFT_BOTTOM,
                "最后确认扩展状态",
                "首页会汇总最近一次扩展扫描结果；点“查看详情”可以看到成功和失败文件，以及推断分类。",
            ),
        ]

    def _request_quick_start(self, destination: str) -> None:
        if project_manager.current_project is None:
            InfoBar.warning(title="提示", content="请先新建项目或打开现有项目", parent=self, duration=3000)
            return
        self.quick_start_requested.emit(destination)

    def _on_open_recent(self, path: str):
        """打开最近项目"""
        import os
        if not os.path.exists(path):
            InfoBar.warning(title="文件不存在", content=f"项目文件已移动或删除:\n{path}", parent=self, duration=5000)
            remove_recent(path)
            self.refresh_recent()
            return
        try:
            project_manager.open(path)
            self.project_opened.emit(path)
        except Exception as e:
            InfoBar.error(title="错误", content=f"无法打开项目:\n{str(e)}", parent=self, duration=5000)

    def _on_remove_recent(self, path: str):
        """从最近列表移除"""
        remove_recent(path)
        self.refresh_recent()

    def update_theme(self):
        """更新主题颜色（供外部调用）"""
        self._apply_theme_colors()
        self._refresh_extension_summary()
        self.refresh_recent()

    def on_new_project(self):
        """新建项目"""
        name, ok = TextInputDialog.get_text(self, "新建项目", placeholder="请输入项目名称")
        if not ok:
            return
        name = name.strip()
        if name:
            base_dir = QFileDialog.getExistingDirectory(self, "选择项目保存目录", "")
            if not base_dir:
                return
            try:
                project_manager.create_new(name, parent_dir=base_dir, create_structure=True)
                self.project_created.emit(name)
            except Exception as e:
                InfoBar.error(title="错误", content=f"创建项目失败:\n{str(e)}", parent=self, duration=5000)

    def on_open_project(self):
        """打开项目"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "打开项目",
            "",
            "ALine 项目 (*.aline *.pyline);;所有文件 (*)"
        )
        if file_path:
            try:
                project_manager.open(file_path)
                self.project_opened.emit(file_path)
            except Exception as e:
                InfoBar.error(title="错误", content=f"无法打开项目:\n{str(e)}", parent=self, duration=5000)
