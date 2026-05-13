"""国际化支持 — gettext 初始化。"""
from __future__ import annotations
import gettext
import sys
from pathlib import Path


def _get_locale_dir() -> str:
    """获取 locale 目录路径（支持 PyInstaller 打包后）。"""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent
    return str(Path(base) / "locale")


_locale_dir = _get_locale_dir()
_translations = gettext.translation(
    "aline",
    localedir=_locale_dir,
    languages=["zh_CN"],  # 默认中文
    fallback=True,
)

_ = _translations.gettext
