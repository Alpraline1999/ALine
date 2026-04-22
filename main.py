"""ALine — 入口文件"""
from __future__ import annotations

import os
import sys
from collections.abc import MutableMapping

def _infer_linux_input_method(env: MutableMapping[str, str]) -> str | None:
    qt_im = env.get("QT_IM_MODULE", "").strip()
    if qt_im:
        return None

    gtk_im = env.get("GTK_IM_MODULE", "").strip().lower()
    if gtk_im.startswith("fcitx"):
        return "fcitx"
    if gtk_im == "ibus":
        return "ibus"

    xmodifiers = env.get("XMODIFIERS", "")
    marker = "@im="
    if marker in xmodifiers:
        im_name = xmodifiers.split(marker, 1)[1].strip().lower()
        if im_name.startswith("fcitx"):
            return "fcitx"
        if im_name == "ibus":
            return "ibus"
    return None


def _configure_linux_environment(env: MutableMapping[str, str] | None = None) -> None:
    target_env = os.environ if env is None else env
    if not sys.platform.startswith("linux"):
        return
    inferred = _infer_linux_input_method(target_env)
    if inferred and not target_env.get("QT_IM_MODULE"):
        target_env["QT_IM_MODULE"] = inferred


_configure_linux_environment()

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from qfluentwidgets import Theme, setTheme

# PyInstaller 路径兼容
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS  # type: ignore
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)

from core.extension_api import load_configured_extensions

_EXTENSION_LOAD_REPORT = load_configured_extensions(os.path.join(BASE_DIR, "extensions"))
for _extension_error in _EXTENSION_LOAD_REPORT.get("errors", []):
    print(f"[ALine] 扩展加载失败: {_extension_error}", file=sys.stderr)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ALine")
    app.setApplicationVersion("0.1.0")

    icon_path = os.path.join(BASE_DIR, "assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    setTheme(Theme.AUTO)

    from ui.main_window import MainWindow
    window = MainWindow()
    minWidth, minHeight = 1600, 900
    window.setMinimumSize(minWidth, minHeight)
    window.resize(minWidth, minHeight)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
