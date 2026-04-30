from __future__ import annotations

import math
from dataclasses import dataclass, field

from ui.matplotlib_fonts import configure_matplotlib_cjk

try:
    import matplotlib

    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    configure_matplotlib_cjk(matplotlib)
    HAS_MATPLOTLIB = True
    _MATPLOTLIB_ERROR = ""
except Exception as exc:
    HAS_MATPLOTLIB = False
    _MATPLOTLIB_ERROR = f"{type(exc).__name__}: {exc}"


# ── 树节点类型常量 ────────────────────────────────────────────
_TYPE_ROOT    = "root"
_TYPE_IMAGE   = "image"
_TYPE_CURVE   = "curve"
_TYPE_DATASET = "dataset"
_TYPE_SERIES  = "series"
_TYPE_ANALYSIS_ROOT = "analysis_root"
_TYPE_ANALYSIS = "analysis"
_SOURCE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
_TEXT_PREVIEW_SUFFIXES = {".csv", ".txt", ".dat", ".tsv", ".json", ".md", ".log", ".py", ".yaml", ".yml", ".ini"}
_TABULAR_PREVIEW_SUFFIXES = {".xlsx", ".xls", ".npy", ".npz"}
_EXTENSION_FIELD_HELP_COMPACT_HEIGHT = 202
_EXTENSION_FIELD_HELP_EXPANDED_HEIGHT = math.ceil(_EXTENSION_FIELD_HELP_COMPACT_HEIGHT * 1.6)
_FOLDER_GROUP_LABELS = {
    "source_files": "源文件",
    "datasets": "数据集",
    "images": "数字化",
    "pictures": "图片集",
    "tools": "工具",
    "pipeline_group": "Pipelines",
    "figure_template_group": "绘图模板",
    "report_template_group": "报告模板",
    "analysis_result_group": "分析结果",
    "ai_group": "AI 工具",
    "prompt_group": "Prompts",
    "skill_group": "Skills",
    "agent_group": "Agents",
}


@dataclass
class _NodePreviewState:
    source_preview_mode: str = "解析"
    plot_type: str = "折线"
    row_limit: int = 80
    skip_rows: int = 0
    row_offset: int = 0
    selected_sheet: str = ""
    external_browser_dir: str = ""
    last_source_path: str = ""


@dataclass
class _PendingImportQueueState:
    paths: list[str] = field(default_factory=list)
    names: dict[str, str] = field(default_factory=dict)
