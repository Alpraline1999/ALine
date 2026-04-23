from qfluentwidgets import ToolTipFilter, ToolTipPosition, isDarkTheme


def text_color():
    """主文字颜色"""
    return "#ffffff" if isDarkTheme() else "#000000"


def secondary_color():
    """次要文字颜色"""
    return "#a0a0a0" if isDarkTheme() else "#808080"


def placeholder_color():
    """占位符颜色"""
    return "#808080" if isDarkTheme() else "#a0a0a0"


def background_color():
    """背景颜色"""
    return "#202020" if isDarkTheme() else "#f5f5f5"


def card_background_color():
    """卡片背景颜色"""
    return "#2d2d2d" if isDarkTheme() else "#ffffff"


def border_color():
    """边框颜色"""
    return "#404040" if isDarkTheme() else "#e0e0e0"


def accent_color():
    """强调色（Fluent 蓝）"""
    return "#0078D4"


def warning_color():
    """警示文字颜色。"""
    return "#D83B01"


def error_color():
    """错误/冲突文字颜色。"""
    return "#e81123"


def flat_status_button_style(color: str, font_size: int = 12) -> str:
    """统一扁平状态按钮样式。"""
    return (
        "background: transparent; border: none; padding: 0; text-align: left;"
        f"color: {color}; font-size: {font_size}px;"
    )


def body_text_style_sheet() -> str:
    """统一正文标签样式。"""
    return f"color: {text_color()};"


def secondary_text_style_sheet(font_size: int = 12) -> str:
    """统一次级说明文字样式。"""
    return f"color: {secondary_color()}; font-size: {font_size}px;"


def placeholder_text_style_sheet(font_size: int = 11, *, italic: bool = False) -> str:
    """统一占位/提示文字样式。"""
    style = f"color: {placeholder_color()}; font-size: {font_size}px;"
    if italic:
        style += " font-style: italic;"
    return style


def card_title_style_sheet(font_size: int = 16) -> str:
    """统一卡片标题样式。"""
    return f"color: {text_color()}; font-weight: 700; font-size: {font_size}px;"


def section_label_style_sheet() -> str:
    """统一节标题样式。"""
    return f"color: {text_color()}; font-weight: 700; font-size: 13px;"


def error_text_style_sheet(font_size: int = 12) -> str:
    """统一错误文字样式。"""
    return f"color: {error_color()}; font-size: {font_size}px;"


def notification_parent(widget):
    """优先返回顶层窗口，供嵌入式页面/面板显示通知。"""
    from PySide6.QtWidgets import QWidget

    if widget is None:
        return None
    window = widget.window() if hasattr(widget, "window") else None
    return window if isinstance(window, QWidget) else widget


def install_fluent_tooltip(widget, delay: int = 400, position=ToolTipPosition.TOP) -> None:
    """为已有 tooltip 的 widget 安装 Fluent tooltip 过滤器。"""
    from PySide6.QtWidgets import QWidget

    if not isinstance(widget, QWidget):
        return
    if not widget.toolTip():
        widget.setProperty("_alineFluentTooltip", False)
        return
    if bool(widget.property("_alineFluentTooltip")):
        return
    widget.installEventFilter(ToolTipFilter(widget, delay, position))
    widget.setProperty("_alineFluentTooltip", True)


def surface_color():
    """浅层面板背景"""
    return "#2a2a2a" if isDarkTheme() else "#fafafa"


def preview_canvas_background_color(dark=None):
    """matplotlib/预览宿主背景"""
    dark = isDarkTheme() if dark is None else bool(dark)
    return "#1e1e1e" if dark else "#ffffff"


def preview_canvas_foreground_color(dark=None):
    """matplotlib/预览宿主前景文字"""
    dark = isDarkTheme() if dark is None else bool(dark)
    return "#cccccc" if dark else "#222222"


def preview_canvas_grid_color(dark=None):
    """matplotlib/预览宿主网格线颜色"""
    dark = isDarkTheme() if dark is None else bool(dark)
    return "#444444" if dark else "#dddddd"


def hover_color():
    """悬停高亮颜色"""
    return "#383838" if isDarkTheme() else "#e8f0fe"


WORKBENCH_TOOL_PANEL_WIDTH = 340
WORKBENCH_BUTTON_HEIGHT = 32
WORKBENCH_BUTTON_MIN_WIDTH = 112
WORKBENCH_INLINE_LABEL_WIDTH = 68
WORKBENCH_WIDE_LABEL_WIDTH = 84


def card_style_sheet():
    """统一卡片样式。"""
    return (
        "QFrame#alineCardFrame {"
        f"background: {card_background_color()};"
        f"border: 1px solid {border_color()};"
        "border-radius: 14px;"
        "}"
    )


# ── 通用 UI 工厂函数（避免各页面重复定义）──────────────────────────────

def make_section_label(text: str, parent=None):
    """创建节标题标签。"""
    from qfluentwidgets import BodyLabel
    lbl = BodyLabel(text, parent)
    lbl.setStyleSheet(section_label_style_sheet())
    return lbl


def make_card_frame(parent=None):
    """创建统一卡片容器。"""
    from PySide6.QtWidgets import QFrame

    frame = QFrame(parent)
    frame.setObjectName("alineCardFrame")
    frame.setStyleSheet(card_style_sheet())
    return frame


def make_card_title(text: str, parent=None):
    """创建卡片标题标签。"""
    from qfluentwidgets import BodyLabel

    lbl = BodyLabel(text, parent)
    lbl.setStyleSheet(card_title_style_sheet())
    return lbl


def make_card_caption(text: str = "", parent=None):
    """创建卡片说明标签。"""
    from qfluentwidgets import CaptionLabel

    lbl = CaptionLabel(text, parent)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(secondary_text_style_sheet(font_size=12))
    return lbl


def make_empty_state_label(text: str = "", parent=None):
    """创建统一空状态/占位说明。"""
    from qfluentwidgets import BodyLabel

    lbl = BodyLabel(text, parent)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(placeholder_text_style_sheet(font_size=12))
    return lbl


def make_hint_label(text: str = "", parent=None):
    """创建统一的说明/提示标签。"""
    from qfluentwidgets import BodyLabel

    lbl = BodyLabel(text, parent)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(placeholder_text_style_sheet(font_size=11))
    return lbl


def make_inline_label(text: str, parent=None, width: int = WORKBENCH_INLINE_LABEL_WIDTH):
    """创建统一宽度的行内标签，便于表单对齐。"""
    from PySide6.QtCore import Qt
    from qfluentwidgets import BodyLabel

    lbl = BodyLabel(text, parent)
    lbl.setFixedWidth(width)
    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return lbl


def apply_button_metrics(*buttons, min_width: int = 0, height: int = WORKBENCH_BUTTON_HEIGHT) -> None:
    """统一按钮高度和最小宽度。"""
    for button in buttons:
        if button is None:
            continue
        if min_width > 0:
            button.setMinimumWidth(min_width)
        button.setFixedHeight(height)


def make_hsep(parent=None):
    """创建水平分隔线"""
    from PySide6.QtWidgets import QFrame
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet(f"color: {border_color()};")
    return line


def make_vsep(parent=None):
    """创建垂直分隔线（1px 宽）"""
    from PySide6.QtWidgets import QFrame
    line = QFrame(parent)
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedWidth(1)
    line.setStyleSheet(f"color: {border_color()};")
    return line
