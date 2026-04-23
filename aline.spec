# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — ALine
支持 Linux / Windows 双平台打包
使用方式：
    python build.py           # 自动检测平台
    pyinstaller aline.spec    # 直接调用 spec

说明：
    - onedir 模式（不用 onefile，避免解压延迟）
    - 排除 test 目录及调试工具
    - openai 包可选：有则打包，无则跳过
"""
import os
import sys
from pathlib import Path

_root = os.path.dirname(os.path.abspath(SPEC))
_binaries = []


# ─── 隐式导入 ─────────────────────────────────────────────────────
_hidden = [
    # PySide6 / Qt
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",
    "PySide6.QtNetwork",
    # qfluentwidgets
    "qfluentwidgets",
    # 科学计算
    "numpy",
    "numpy.core._multiarray_umath",
    "scipy",
    "scipy.signal",
    "scipy.stats",
    "scipy.integrate",
    "scipy.optimize",
    "scipy.linalg",
    "scipy.interpolate",
    "matplotlib",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_agg",
    "scienceplots",
    # 数据处理
    "openpyxl",
    "csv",
    "json",
    # 图像处理
    "cv2",
]

# openai 可选
try:
    import openai  # noqa: F401
    _hidden += ["openai", "openai.types"]
except ImportError:
    pass


# ─── 数据文件 ─────────────────────────────────────────────────────
_datas = []
# qfluentwidgets 资源
try:
    import qfluentwidgets
    _qfw_dir = os.path.dirname(qfluentwidgets.__file__)
    _datas.append((_qfw_dir, "qfluentwidgets"))
except ImportError:
    pass

# matplotlib 字体/数据资源
try:
    import matplotlib
    _mpl_dir = os.path.dirname(matplotlib.__file__)
    _datas.append((os.path.join(_mpl_dir, "mpl-data"), "matplotlib/mpl-data"))
except ImportError:
    pass

# PySide6 输入法插件（Linux/Wayland/fcitx/ibus）
try:
    import PySide6

    _pyside_dir = os.path.dirname(PySide6.__file__)
    _im_plugin_dir = os.path.join(_pyside_dir, "Qt", "plugins", "platforminputcontexts")
    if os.path.isdir(_im_plugin_dir):
        for _name in os.listdir(_im_plugin_dir):
            _plugin_path = os.path.join(_im_plugin_dir, _name)
            if os.path.isfile(_plugin_path):
                _binaries.append((_plugin_path, os.path.join("PySide6", "Qt", "plugins", "platforminputcontexts")))
except ImportError:
    pass

# 应用图标 (可选)
_icon_dir = os.path.join(_root, "assets")
if os.path.isdir(_icon_dir):
    _datas.append((_icon_dir, "assets"))

_extensions_dir = os.path.join(_root, "extensions")
if os.path.isdir(_extensions_dir):
    _datas.append((_extensions_dir, "extensions"))


# ─── 排除不需要打包的模块 ─────────────────────────────────────────
_excludes = [
    "pytest",
    "unittest",
    "IPython",
    "jupyter",
    "tkinter",
    "PyQt5",
    "wx",
    "gi",
]


# ─── 平台图标 ──────────────────────────────────────────────────────
if sys.platform == "win32":
    _icon = os.path.join(_icon_dir, "icon.ico") if os.path.isdir(_icon_dir) else None
else:
    _icon = os.path.join(_icon_dir, "icon.png") if os.path.isdir(_icon_dir) else None


# ─── Analysis ─────────────────────────────────────────────────────
a = Analysis(
    [os.path.join(_root, "main.py")],
    pathex=[_root],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ALine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ALine",
)
