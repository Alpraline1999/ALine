"""ALine — 入口文件"""
from __future__ import annotations

import os
import sys

# Linux Wayland 兼容
if sys.platform.startswith("linux"):
    os.environ.setdefault("XDG_SESSION_TYPE", "x11")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from qfluentwidgets import Theme, setTheme

# PyInstaller 路径兼容
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS  # type: ignore
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, BASE_DIR)


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
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
