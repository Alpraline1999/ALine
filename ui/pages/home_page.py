from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QFrame, QSizePolicy, QLabel
from qfluentwidgets import (PrimaryPushButton, PushButton, FluentIcon as FIF,
    BodyLabel, LargeTitleLabel, SubtitleLabel, SmoothScrollArea,
    InfoBar, TeachingTipTailPosition, isDarkTheme, IconWidget, SingleDirectionScrollArea)

from core.extension_api import get_extension_load_status
from core.ui_preferences import is_home_onboarding_completed, set_home_onboarding_completed
from ui.theme import (
    accent_color,
    border_color,
    card_background_color,
    flat_status_button_style,
    install_fluent_tooltip,
    make_empty_state_label,
    make_hint_label,
    make_section_label,
    notification_parent,
    hover_color,
    placeholder_color,
    secondary_color,
    text_color,
    warning_color,
)
from ui.dialogs.fluent_dialogs import TextInputDialog
from core.project_manager import project_manager
from core.recent_projects import load_recent, remove_recent
from ui.widgets.extension_panel import show_extension_load_report_dialog
from ui.widgets.onboarding import OnboardingStep, PageOnboardingController


_HOME_CONTENT_MARGIN = 40
_HOME_BANNER_HEIGHT = 392
_HOME_LINK_CARD_WIDTH = 198
_HOME_LINK_CARD_HEIGHT = 220


class _HomeLinkCard(QFrame):
    def __init__(self, icon, title: str, content: str, url: str, parent=None):
        super().__init__(parent)
        self.url = QUrl(url)
        self.setObjectName("homeLinkCard")
        self.setFixedSize(_HOME_LINK_CARD_WIDTH, _HOME_LINK_CARD_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.iconWidget = IconWidget(icon, self)
        self.titleLabel = QLabel(title, self)
        self.contentLabel = QLabel(content, self)
        self.urlWidget = IconWidget(FIF.LINK, self)

        self.iconWidget.setFixedSize(54, 54)
        self.urlWidget.setFixedSize(16, 16)
        self.contentLabel.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(24, 24, 18, 16)
        layout.addWidget(self.iconWidget, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addSpacing(16)
        layout.addWidget(self.titleLabel, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(8)
        layout.addWidget(self.contentLabel, 1, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.urlWidget, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        self.update_theme()

    def update_theme(self) -> None:
        self.setStyleSheet(
            "QFrame#homeLinkCard {"
            f"background: {card_background_color()};"
            f"border: 1px solid {border_color()};"
            "border-radius: 8px;"
            "}"
            "QFrame#homeLinkCard:hover {"
            f"background: {hover_color()};"
            f"border: 1px solid {accent_color()};"
            "}"
        )
        self.titleLabel.setStyleSheet(
            f"color: {text_color()}; font-size: 15px; font-weight: 600; background: transparent;"
        )
        self.contentLabel.setStyleSheet(
            f"color: {secondary_color()}; font-size: 12px; background: transparent;"
        )

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(self.url)


class _HomeLinkCardView(SingleDirectionScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Orientation.Horizontal)
        self._cards = []
        self.view = QWidget(self)

        layout = QHBoxLayout(self.view)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._layout = layout
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(_HOME_LINK_CARD_HEIGHT)
        self.setStyleSheet(
            "SingleDirectionScrollArea { background: transparent; border: none; }"
            "QWidget { background: transparent; }"
        )

    def addCard(self, icon, title: str, content: str, url: str) -> _HomeLinkCard:
        card = _HomeLinkCard(icon, title, content, url, self.view)
        self._cards.append(card)
        self._layout.addWidget(card, 0, Qt.AlignmentFlag.AlignLeft)
        return card

    def update_theme(self) -> None:
        for card in self._cards:
            card.update_theme()


class _HomeBannerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(_HOME_BANNER_HEIGHT)
        self._background = QPixmap(str(Path(__file__).resolve().parents[2] / "assets" / "aline_home_background.png"))
        self._card_icon_path = str(Path(__file__).resolve().parents[2] / "assets" / "aline_icon.png")
        self._link_cards = []
        self._link_card_view = None
        self._hero_title = None
        self._hero_subtitle = None
        self._hero_hint = None

        layout = QVBoxLayout(self)
    layout.setContentsMargins(_HOME_CONTENT_MARGIN, 24, _HOME_CONTENT_MARGIN, 20)
        layout.setSpacing(6)
    layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._layout = layout

        self._hero_title = LargeTitleLabel("ALine", self)
    layout.addWidget(self._hero_title, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._hero_subtitle = SubtitleLabel("科研数据管理与可视化工作台", self)
    layout.addWidget(self._hero_subtitle, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self._hero_hint = BodyLabel("项目、数据、绘图和分析结果在同一工作台内流转。", self)
        self._hero_hint.setWordWrap(True)
        self._hero_hint.setMaximumWidth(760)
        self._hero_hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout.addWidget(self._hero_hint, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        layout.addStretch(1)

        self._link_card_view = _HomeLinkCardView(self)
        self._link_cards.append(
            self._link_card_view.addCard(
                self._card_icon_path,
                "软件主页",
                "预留软件主页入口，后续替换为正式介绍页面。",
                "https://example.com",
            )
        )
        self._link_cards.append(
            self._link_card_view.addCard(
                FIF.GITHUB,
                "GitHub 仓库",
                "预留代码仓库入口，后续替换为正式仓库地址。",
                "https://example.com",
            )
        )
        layout.addWidget(
            self._link_card_view,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
        )
        self.update_theme()
        self._update_hero_hint_height()

    def _update_hero_hint_height(self) -> None:
        if self._hero_hint is None:
            return

        margins = self._layout.contentsMargins()
        available_width = max(1, self.width() - margins.left() - margins.right())
        available_width = min(available_width, self._hero_hint.maximumWidth())
        text_rect = self._hero_hint.fontMetrics().boundingRect(
            0,
            0,
            available_width,
            0,
            Qt.TextFlag.TextWordWrap,
            self._hero_hint.text(),
        )
        self._hero_hint.setMinimumHeight(max(text_rect.height() + 4, self._hero_hint.minimumSizeHint().height()))
        self._hero_hint.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_hero_hint_height()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        painter.setPen(Qt.PenStyle.NoPen)

        path = QPainterPath()
        rect = QRectF(self.rect())
        path.addRect(rect)

        if not self._background.isNull():
            target_rect = self.rect()
            pixmap = self._background.scaledToWidth(
                max(1, target_rect.width()),
                Qt.TransformationMode.SmoothTransformation,
            )
            if pixmap.height() < target_rect.height():
                pixmap = self._background.scaled(
                    target_rect.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            draw_x = target_rect.x() + (target_rect.width() - pixmap.width()) // 2
            draw_y = target_rect.y() + target_rect.height() - pixmap.height()
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(draw_x, draw_y, pixmap)
            painter.restore()
        else:
            fallback = QColor(224, 232, 242) if not isDarkTheme() else QColor(24, 28, 34)
            painter.fillPath(path, fallback)

        gradient = QLinearGradient(0, 0, 0, self.height())
        if isDarkTheme():
            gradient.setColorAt(0.0, QColor(0, 0, 0, 196))
            gradient.setColorAt(0.58, QColor(0, 0, 0, 92))
            gradient.setColorAt(1.0, QColor(0, 0, 0, 42))
        else:
            gradient.setColorAt(0.0, QColor(255, 255, 255, 232))
            gradient.setColorAt(0.58, QColor(255, 255, 255, 150))
            gradient.setColorAt(1.0, QColor(255, 255, 255, 46))
        painter.fillPath(path, QBrush(gradient))

    def update_theme(self) -> None:
        if self._hero_title is not None:
            self._hero_title.setStyleSheet(f"font-size: 44px; font-weight: 700; color: {text_color()}; background: transparent;")
        if self._hero_subtitle is not None:
            self._hero_subtitle.setStyleSheet(f"font-size: 18px; color: {secondary_color()}; background: transparent;")
        if self._hero_hint is not None:
            self._hero_hint.setStyleSheet(f"font-size: 13px; color: {secondary_color()}; background: transparent;")
            self._update_hero_hint_height()
        if self._link_card_view is not None:
            self._link_card_view.update_theme()
        self.update()


class HomePage(QWidget):
    """首页 - 项目列表/新建/打开"""

    project_created = Signal(str)  # 项目创建/打开后信号
    project_opened = Signal(str)  # 项目打开后信号
    quick_start_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._banner = None
        self._title = None
        self._subtitle = None
        self._recent_label = None
        self._no_recent = None
        self._new_btn = None
        self._open_btn = None
        self._guide_toggle_btn = None
        self._status_bar = None
        self._extension_status_btn = None
        self._content_widget = None
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
        page_layout = QVBoxLayout(self)
        page_layout.setSpacing(0)
        page_layout.setContentsMargins(0, 0, 0, 0)

        self._banner = _HomeBannerWidget(self)
        page_layout.addWidget(self._banner)

        self._content_widget = QWidget(self)
        self._content_widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self._content_widget)
        layout.setSpacing(20)
        layout.setContentsMargins(_HOME_CONTENT_MARGIN, 20, _HOME_CONTENT_MARGIN, 40)
        page_layout.addWidget(self._content_widget, 1)

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
        btn_layout.addStretch(1)
        btn_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._action_button_layout = btn_layout

        layout.addLayout(btn_layout)

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
        self._recent_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._recent_scroll.hide()

        self._recent_items_widget = QWidget()
        self._recent_items_layout = QVBoxLayout(self._recent_items_widget)
        self._recent_items_layout.setSpacing(4)
        self._recent_items_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_items_layout.addStretch()
        self._recent_scroll.setWidget(self._recent_items_widget)
        self._recent_scroll.setStyleSheet("SmoothScrollArea { background: transparent; border: none; }")
        self._recent_items_widget.setStyleSheet("background: transparent;")
        layout.addWidget(self._recent_scroll, 1)

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

    def _build_bottom_status_bar(self, layout: QVBoxLayout) -> None:
        self._status_bar = QWidget(self)
        status_layout = QHBoxLayout(self._status_bar)
        status_layout.setContentsMargins(0, 8, 0, 0)
        status_layout.setSpacing(10)

        self._extension_status_btn = PushButton("", self._status_bar)
        self._extension_status_btn.clicked.connect(self._show_extension_details)
        self._extension_status_btn.setFlat(True)
        status_layout.addWidget(self._extension_status_btn, 0, Qt.AlignLeft)
        status_layout.addStretch(1)

        layout.addWidget(self._status_bar)

    def _notification_parent(self):
        return notification_parent(self)

    def _apply_theme_colors(self):
        """应用当前主题颜色"""
        tc = text_color()
        sc = secondary_color()
        pc = placeholder_color()
        self._recent_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {tc};")
        self._no_recent.setStyleSheet(f"color: {pc}; font-size: 12px;")
        if self._status_bar is not None:
            self._status_bar.setStyleSheet(f"background: transparent; border-top: 1px solid {border_color()};")
        if self._banner is not None:
            self._banner.update_theme()

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
                f"QWidget:hover {{background: {hover_color()};}}"
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
            install_fluent_tooltip(path_lbl)
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
            install_fluent_tooltip(remove_btn)
            remove_btn.clicked.connect(lambda _, p=path: self._on_remove_recent(p))
            row_layout.addWidget(remove_btn)

            # 点击行打开项目（排除删除按钮区域）
            row.mousePressEvent = lambda e, p=path: self._on_open_recent(p)
            row.setCursor(Qt.PointingHandCursor)

            self._recent_items_layout.insertWidget(
                self._recent_items_layout.count() - 1, row
            )

    def _refresh_extension_summary(self) -> None:
        if self._extension_status_btn is None:
            return
        status = get_extension_load_status()
        registered_count = status["registered_count"]
        error_count = status["error_count"]
        source_summary = status.get("source_summary") or {}
        loaded_counts = dict(source_summary.get("loaded_extension_counts") or {})
        error_file_counts = dict(source_summary.get("error_file_counts") or {})
        builtin_count = int(loaded_counts.get("builtin", 0) or 0)
        external_count = int(loaded_counts.get("external", 0) or 0)
        source_suffix = (
            f"（内置 {builtin_count} / 外部 {external_count}）"
            if builtin_count + external_count > 0
            else ""
        )
        if error_count:
            self._extension_status_btn.setText(f"扩展：{registered_count} 项可用{source_suffix}，{error_count} 项失败")
            self._extension_status_btn.setStyleSheet(flat_status_button_style(warning_color()))
        elif registered_count:
            self._extension_status_btn.setText(f"扩展：{registered_count} 项可用{source_suffix}")
            self._extension_status_btn.setStyleSheet(flat_status_button_style(accent_color()))
        else:
            self._extension_status_btn.setText("扩展：未发现可用项")
            self._extension_status_btn.setStyleSheet(flat_status_button_style(placeholder_color()))
        details = status["details"]
        tooltip_lines = []
        if builtin_count + external_count > 0:
            tooltip_lines.append(f"可用扩展：内置 {builtin_count}，外部 {external_count}")
        builtin_error_count = int(error_file_counts.get("builtin", 0) or 0)
        external_error_count = int(error_file_counts.get("external", 0) or 0)
        if builtin_error_count + external_error_count > 0:
            tooltip_lines.append(f"失败文件：内置 {builtin_error_count}，外部 {external_error_count}")
        self._extension_status_btn.setToolTip("\n".join(tooltip_lines))
        install_fluent_tooltip(self._extension_status_btn)
        self._extension_status_btn.setEnabled(bool(details.get("loaded") or details.get("errors")))

    def _show_extension_details(self) -> None:
        show_extension_load_report_dialog(self, "扩展加载详情")

    def start_onboarding(self, force: bool = False) -> None:
        self._onboarding_controller.start(force=force)

    def _home_onboarding_steps(self) -> list[OnboardingStep]:
        return [
            OnboardingStep(
                lambda: self._banner,
                TeachingTipTailPosition.BOTTOM,
                "主页入口留在这里",
                "顶部 Banner 预留了软件主页和 GitHub 仓库卡片，后续可直接补充链接和封面。",
            ),
            OnboardingStep(
                lambda: self._new_btn,
                TeachingTipTailPosition.BOTTOM,
                "先建项目",
                "数据、图表和结果都会落在同一项目里，先建项目最稳妥。",
            ),
            OnboardingStep(
                lambda: self._open_btn,
                TeachingTipTailPosition.BOTTOM,
                "也可以继续上次工作",
                "已有 .aline 项目时，从这里恢复项目树和页面状态。",
            ),
            OnboardingStep(
                lambda: self._recent_label,
                TeachingTipTailPosition.BOTTOM,
                "最近项目会留在这里",
                "常做的项目可以直接回到上次位置。",
            ),
        ]

    def _request_quick_start(self, destination: str) -> None:
        if project_manager.current_project is None:
            InfoBar.warning(title="提示", content="请先新建项目或打开现有项目", parent=self._notification_parent(), duration=3000)
            return
        self.quick_start_requested.emit(destination)

    def _on_open_recent(self, path: str):
        """打开最近项目"""
        import os
        if not os.path.exists(path):
            InfoBar.warning(title="文件不存在", content=f"项目文件已移动或删除:\n{path}", parent=self._notification_parent(), duration=5000)
            remove_recent(path)
            self.refresh_recent()
            return
        try:
            project_manager.open(path)
            self.project_opened.emit(path)
        except Exception as e:
            InfoBar.error(title="错误", content=f"无法打开项目:\n{str(e)}", parent=self._notification_parent(), duration=5000)

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
                InfoBar.error(title="错误", content=f"创建项目失败:\n{str(e)}", parent=self._notification_parent(), duration=5000)

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
                InfoBar.error(title="错误", content=f"无法打开项目:\n{str(e)}", parent=self._notification_parent(), duration=5000)
