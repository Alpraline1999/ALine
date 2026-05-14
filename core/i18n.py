"""国际化支持 — gettext 初始化。"""
from __future__ import annotations
import gettext
import sys
from pathlib import Path


def _current_language() -> str:
    try:
        from core.ui_preferences import get_ui_language

        language = get_ui_language()
    except Exception:
        language = "zh_CN"
    return language if language in {"zh_CN", "en_US"} else "zh_CN"


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
    languages=[_current_language()],
    fallback=True,
)

def _translate(message: str) -> str:
    return _translations.gettext(message)


_ = _translate
gettext_translate = _translate

def reload_translations() -> gettext.NullTranslations | gettext.GNUTranslations:
    global _translations
    _translations = gettext.translation(
        "aline",
        localedir=_locale_dir,
        languages=[_current_language()],
        fallback=True,
    )
    return _translations


__all__ = ["_", "gettext_translate", "reload_translations"]
