"""国际化支持 — gettext 初始化。"""
from __future__ import annotations
import gettext
import sys
from pathlib import Path

try:
    from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator
except Exception:  # pragma: no cover - Qt may be unavailable in some non-UI contexts
    QCoreApplication = None  # type: ignore[assignment]
    QLibraryInfo = None  # type: ignore[assignment]
    QLocale = None  # type: ignore[assignment]
    QTranslator = None  # type: ignore[assignment]


_MANUAL_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en_US": {
        "添加文件夹": "Add Folder",
        "选择文件夹": "Choose Folder",
    },
}

_qt_translators: list[QTranslator] = []


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
    translated = _translations.gettext(message)
    if translated != message:
        return translated
    return _MANUAL_TRANSLATIONS.get(_current_language(), {}).get(message, message)


def _reload_qt_translations() -> None:
    if QCoreApplication is None or QTranslator is None or QLibraryInfo is None or QLocale is None:
        return
    app = QCoreApplication.instance()
    if app is None:
        return

    for translator in _qt_translators:
        app.removeTranslator(translator)
    _qt_translators.clear()

    language = _current_language()
    if language == "en_US":
        return

    try:
        translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    except Exception:
        return

    locale = QLocale(language)
    for catalog in ("qtbase", "qt"):
        translator = QTranslator(app)
        if translator.load(locale, catalog, "_", translations_path):
            app.installTranslator(translator)
            _qt_translators.append(translator)


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
    _reload_qt_translations()
    return _translations


__all__ = ["_", "gettext_translate", "reload_translations"]
