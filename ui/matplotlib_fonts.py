"""matplotlib 中文字体配置。"""

from __future__ import annotations

from functools import lru_cache
import os
import platform
from typing import Any, List, Optional, Tuple


def _candidate_font_names() -> List[str]:
    system_name = platform.system().lower()
    if system_name == "windows":
        return ["Microsoft YaHei", "SimHei", "SimSun", "Arial Unicode MS"]
    return ["Noto Sans CJK JP", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "SimHei"]


def _candidate_font_files() -> List[str]:
    system_name = platform.system().lower()
    if system_name == "windows":
        return [
            r"C:\\Windows\\Fonts\\msyh.ttc",
            r"C:\\Windows\\Fonts\\msyhbd.ttc",
            r"C:\\Windows\\Fonts\\simhei.ttf",
            r"C:\\Windows\\Fonts\\simsun.ttc",
        ]
    return [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]


@lru_cache(maxsize=1)
def list_matplotlib_font_families() -> List[str]:
    """返回 matplotlib 当前可用的字体族名称。"""
    try:
        from matplotlib import font_manager
    except Exception:
        return []

    seen = set()
    all_names = []
    for font in font_manager.fontManager.ttflist:
        name = (font.name or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        all_names.append(name)

    ordered = []
    for name in _candidate_font_names():
        if name in seen and name not in ordered:
            ordered.append(name)
    for name in sorted(all_names, key=str.casefold):
        if name not in ordered:
            ordered.append(name)
    return ordered


def configure_matplotlib_cjk(matplotlib_module) -> Optional[str]:
    """为 matplotlib 配置可用的中文字体，并关闭负号乱码。"""
    try:
        from matplotlib import font_manager
    except Exception:
        return None

    candidate_font_files = _candidate_font_files()
    candidate_names = _candidate_font_names()

    selected_font = None
    for font_path in candidate_font_files:
        if not os.path.exists(font_path):
            continue
        try:
            font_manager.fontManager.addfont(font_path)
            font_prop = font_manager.FontProperties(fname=font_path)
            font_name = font_prop.get_name()
            if font_name:
                selected_font = font_name
                break
        except Exception:
            continue

    if selected_font is None:
        available_names = {font.name for font in font_manager.fontManager.ttflist if font.name}
        selected_font = next((name for name in candidate_names if name in available_names), None)

    if selected_font:
        matplotlib_module.rcParams["font.family"] = [selected_font, "sans-serif"]
    else:
        matplotlib_module.rcParams["font.family"] = ["sans-serif"]

    sans_fonts = []
    for name in [selected_font, *candidate_names, "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "WenQuanYi Micro Hei", "DejaVu Sans"]:
        if name and name not in sans_fonts:
            sans_fonts.append(name)
    matplotlib_module.rcParams["font.sans-serif"] = sans_fonts
    matplotlib_module.rcParams["font.size"] = max(1, float(matplotlib_module.rcParams.get("font.size", 10) or 10))
    matplotlib_module.rcParams["axes.unicode_minus"] = False
    return selected_font


def bootstrap_matplotlib_qtagg() -> Tuple[Any, Any, Any, str]:
    """统一初始化 matplotlib QtAgg 宿主与中文字体配置。"""
    try:
        import matplotlib

        matplotlib.use("QtAgg")
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
        from matplotlib.figure import Figure

        configure_matplotlib_cjk(matplotlib)
        return matplotlib, FigureCanvas, Figure, ""
    except Exception as exc:
        return None, None, None, f"{type(exc).__name__}: {exc}"
