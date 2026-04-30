from __future__ import annotations

from math import ceil

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QTextDocument, QTextOption
from qfluentwidgets import FluentIcon as FIF


def _series_color_icon(color_str: str) -> QPixmap:
    """生成 16×16 折线图风格图标（用于 DataSeries 叶节点）。"""
    px = QPixmap(16, 16)
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    color = QColor(color_str if color_str else "#0078D4")
    painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    points = [QPoint(2, 11), QPoint(6, 8), QPoint(9, 10), QPoint(13, 4)]
    for left, right in zip(points, points[1:]):
        painter.drawLine(left, right)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    for point in points:
        painter.drawEllipse(point, 1.8, 1.8)
    painter.end()
    return px


def _wrap_text_height(font, text: str, width: int) -> int:
    document = QTextDocument()
    document.setDefaultFont(font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
    document.setDefaultTextOption(option)
    document.setPlainText(text)
    document.setTextWidth(max(1, width))
    return ceil(document.size().height())


_ROOT_GROUP_ORDER = {
    "source_files": 0,
    "datasets": 1,
    "dataset_set": 1,
    "pictures": 2,
    "picture_set": 2,
    "analysis_result_group": 3,
    "images": 4,
    "image_set": 4,
    "tools": 5,
    "tool_set": 5,
}

_ROOT_GROUP_LABELS = {
    "source_files": "源文件",
    "datasets": "数据集",
    "dataset_set": "数据集",
    "pictures": "图片集",
    "picture_set": "图片集",
    "analysis_result_group": "分析结果",
    "images": "数字化",
    "image_set": "数字化",
    "tools": "工具",
    "tool_set": "工具",
}


def _sort_name_bucket(text: str) -> int:
    clean = str(text or "").strip()
    if not clean:
        return 3
    first = clean[0]
    if first.isascii() and first.isalnum():
        return 0
    if first.isascii():
        return 1
    return 2


def _sort_text_key(text: str) -> tuple[int, str, str]:
    clean = str(text or "").strip()
    return (_sort_name_bucket(clean), clean.casefold(), clean)


def _extension_config_name_key(text: str) -> str:
    return str(text or "").strip().casefold()


def _global_asset_sort_key(asset) -> tuple[int, int, str, str]:
    builtin_rank = 0 if bool(getattr(asset, "is_builtin", False)) else 1
    name_key = _sort_text_key(getattr(asset, "name", "") or getattr(asset, "id", ""))
    return (builtin_rank, name_key[0], name_key[1], name_key[2])


_PROJECT_ICON = getattr(FIF, "ZIP_FOLDER", getattr(FIF, "LIBRARY", FIF.FOLDER))
_DATA_ICON = FIF.DICTIONARY
_SOURCE_FOLDER_ICON = getattr(FIF, "IOT", FIF.FOLDER)
_SOURCE_FILE_ICON = getattr(FIF, "DOCUMENT", FIF.FOLDER)
_DATASET_GROUP_ICON = getattr(FIF, "LIBRARY", FIF.FOLDER)
_DIGITIZE_GROUP_ICON = getattr(FIF, "LABEL", FIF.PHOTO)
_PICTURE_GROUP_ICON = getattr(FIF, "PHOTO", FIF.PHOTO)
_NEW_DATASET_ACTION_ICON = getattr(FIF, "DICTIONARY_ADD", FIF.ADD)
_IMPORT_DATA_ACTION_ICON = getattr(FIF, "DOWNLOAD", FIF.DOWNLOAD)
_OPEN_DIGITIZE_ACTION_ICON = getattr(FIF, "LABEL", FIF.EDIT)
_SOURCE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


# ── 每种 kind 的 (FluentIcon, 颜色hint) ──────────────────────────
_KIND_CONFIG = {
    "folder":          (FIF.FOLDER,          None),
    "data_file":       (_DATA_ICON,         None),
    "source_file":     (_SOURCE_FILE_ICON,  None),
    "image_work":      (FIF.PHOTO,          None),
    "picture":         (FIF.PHOTO,           None),
    "pipeline":        (FIF.DEVELOPER_TOOLS, "#0078D4"),
    "figure_template": (FIF.PIE_SINGLE,      "#107C10"),
    "report_template": (FIF.DOCUMENT,        "#8C6C00"),
    "analysis_result": (FIF.SEARCH,          "#D83B01"),
    "ai_tool":         (FIF.CHAT,            "#881798"),   # v0.2 compat
    "ai_prompt":       (FIF.CHAT,            "#881798"),
    "ai_skill":        (FIF.DEVELOPER_TOOLS, "#881798"),
    "ai_agent":        (FIF.ROBOT,           "#881798"),
    "global_pipeline": (FIF.DEVELOPER_TOOLS, "#0078D4"),
    "global_report_template": (FIF.DOCUMENT, "#8C6C00"),
    "global_curve_style_template": (FIF.PENCIL_INK, "#107C10"),
    "global_plot_style": (FIF.PIE_SINGLE,    "#8C6C00"),
    "global_plot_theme": (FIF.PIE_SINGLE,    "#8C6C00"),
        "global_extension_config": (getattr(FIF, "SETTING", FIF.DEVELOPER_TOOLS), "#0078D4"),
    "global_ai_prompt": (FIF.CHAT,           "#881798"),
    "global_ai_skill": (FIF.DEVELOPER_TOOLS, "#881798"),
    "global_ai_agent": (FIF.ROBOT,           "#881798"),
}

# group_type → FluentIcon（系统文件夹专用图标）
_GROUP_ICON = {
    "datasets":       _DATASET_GROUP_ICON,
    "dataset_set":    _DATASET_GROUP_ICON,
    "source_files":   _SOURCE_FOLDER_ICON,
    "images":         _DIGITIZE_GROUP_ICON,
    "image_set":      FIF.PHOTO,
    "pictures":       _PICTURE_GROUP_ICON,
    "picture_set":    _PICTURE_GROUP_ICON,
    "tools":          FIF.DEVELOPER_TOOLS,
    "tool_set":       FIF.DEVELOPER_TOOLS,
    "analysis_result_group": FIF.SEARCH,
    "pipeline_group": FIF.DEVELOPER_TOOLS,
    "template_group": FIF.PIE_SINGLE,
    "figure_template_group": FIF.PIE_SINGLE,
    "report_template_group": FIF.DOCUMENT,
    "ai_group":       FIF.ROBOT,
    "prompt_group":   FIF.CHAT,
    "skill_group":    FIF.DEVELOPER_TOOLS,
    "agent_group":    FIF.ROBOT,
}

# 系统文件夹不可重命名/删除
_PROTECTED_GROUP_TYPES = frozenset({
    "datasets", "dataset_set",
    "source_files",
    "images", "image_set",
    "pictures", "picture_set",
    "tools", "tool_set",
    "analysis_result_group",
    "pipeline_group", "template_group", "figure_template_group",
    "report_template_group", "ai_group",
})

_ROOT_GROUP_TYPES = frozenset({
    "datasets", "dataset_set",
    "source_files",
    "images", "image_set",
    "pictures", "picture_set",
    "tools", "tool_set",
})

_MANAGED_FOLDER_GROUP_TYPES = frozenset({
    "datasets",
    "source_files",
    "images",
    "pictures",
    "analysis_result_group",
})

# QTreeWidgetItem UserRole 存储 (kind, id)
_ROLE = Qt.ItemDataRole.UserRole
_PROJECT_ROLE = Qt.ItemDataRole.UserRole + 1
_SYNTHETIC_GLOBAL_KINDS = frozenset({
    "global_root", "global_group", "global_pipeline",
    "global_report_template", "global_curve_style_template", "global_plot_style", "global_plot_theme", "global_extension_config",
    "global_ai_prompt", "global_ai_skill", "global_ai_agent",
})

_EXTENSION_CONFIG_GROUPS = [
    ("plot", "绘图扩展", getattr(FIF, "PENCIL_INK", FIF.DEVELOPER_TOOLS)),
    ("processing", "处理扩展", FIF.DEVELOPER_TOOLS),
    ("analysis", "分析扩展", FIF.SEARCH),
    ("digitize", "数字化扩展", getattr(FIF, "LABEL", FIF.PHOTO)),
]
