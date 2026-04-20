from qfluentwidgets import isDarkTheme


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


def surface_color():
    """浅层面板背景"""
    return "#2a2a2a" if isDarkTheme() else "#fafafa"


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
    lbl.setStyleSheet(f"color: {text_color()}; font-weight: 700; font-size: 13px;")
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
    lbl.setStyleSheet(f"color: {text_color()}; font-weight: 700; font-size: 16px;")
    return lbl


def make_card_caption(text: str = "", parent=None):
    """创建卡片说明标签。"""
    from qfluentwidgets import CaptionLabel

    lbl = CaptionLabel(text, parent)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {secondary_color()}; font-size: 12px;")
    return lbl


def make_empty_state_label(text: str = "", parent=None):
    """创建统一空状态/占位说明。"""
    from qfluentwidgets import BodyLabel

    lbl = BodyLabel(text, parent)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {placeholder_color()}; font-size: 12px;")
    return lbl


def make_hint_label(text: str = "", parent=None):
    """创建统一的说明/提示标签。"""
    from qfluentwidgets import BodyLabel

    lbl = BodyLabel(text, parent)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {placeholder_color()}; font-size: 11px;")
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
