"""ALine — 入口文件"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterable, MutableMapping
from importlib.util import find_spec
from pathlib import Path

from aline_metadata import APP_NAME, APP_VERSION


def _normalize_linux_input_method_name(name: str | None) -> str | None:
    value = str(name or "").strip().lower()
    if not value:
        return None
    if value.startswith("fcitx"):
        return "fcitx"
    if value == "ibus":
        return "ibus"
    if value == "compose":
        return "compose"
    return value


def _candidate_qt_plugin_roots() -> list[Path]:
    roots: list[Path] = []
    spec = find_spec("PySide6")
    if spec is not None and spec.origin:
        roots.append(Path(spec.origin).resolve().parent / "Qt" / "plugins")

    for raw_path in (
        "/usr/lib/x86_64-linux-gnu/qt6/plugins",
        "/usr/lib/qt6/plugins",
        "/usr/local/lib/qt6/plugins",
        "/usr/lib/x86_64-linux-gnu/qt5/plugins",
        "/usr/lib/qt5/plugins",
        "/usr/local/lib/qt5/plugins",
    ):
        roots.append(Path(raw_path))

    resolved: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        marker = str(root.expanduser().resolve(strict=False))
        if marker in seen:
            continue
        seen.add(marker)
        resolved.append(Path(marker))
    return resolved


def _platforminputcontext_modules(plugin_roots: Iterable[Path]) -> set[str]:
    modules: set[str] = set()
    for root in plugin_roots:
        plugin_dir = Path(root) / "platforminputcontexts"
        if not plugin_dir.is_dir():
            continue
        for plugin_path in plugin_dir.iterdir():
            name = plugin_path.name.lower()
            if "platforminputcontextplugin" not in name:
                continue
            if "fcitx" in name:
                modules.update({"fcitx", "fcitx5"})
            elif "ibus" in name:
                modules.add("ibus")
            elif "compose" in name:
                modules.add("compose")
    return modules


def _merge_qt_plugin_paths(env: MutableMapping[str, str], plugin_roots: Iterable[Path]) -> None:
    existing_paths = [path for path in str(env.get("QT_PLUGIN_PATH", "")).split(os.pathsep) if path]
    merged = list(existing_paths)
    seen = set(existing_paths)
    for root in plugin_roots:
        normalized = str(Path(root).expanduser().resolve(strict=False))
        if normalized in seen:
            continue
        seen.add(normalized)
        merged.append(normalized)
    if merged:
        env["QT_PLUGIN_PATH"] = os.pathsep.join(merged)


def _select_linux_input_method(env: MutableMapping[str, str], available_modules: set[str]) -> str | None:
    preferred = _normalize_linux_input_method_name(env.get("QT_IM_MODULE"))
    inferred = _normalize_linux_input_method_name(_infer_linux_input_method(env))

    for candidate in (preferred, inferred, "fcitx", "ibus", "compose"):
        if candidate and candidate in available_modules:
            return "fcitx" if candidate == "fcitx5" else candidate
    return preferred or inferred

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

    plugin_roots = [root for root in _candidate_qt_plugin_roots() if (root / "platforminputcontexts").is_dir()]
    available_modules = _platforminputcontext_modules(plugin_roots)
    if plugin_roots:
        _merge_qt_plugin_paths(target_env, plugin_roots)

    selected = _select_linux_input_method(target_env, available_modules)
    if selected:
        target_env["QT_IM_MODULE"] = selected


_configure_linux_environment()


def _resolve_base_dir() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from qfluentwidgets import Theme, setTheme

BASE_DIR = str(_resolve_base_dir())

sys.path.insert(0, BASE_DIR)

from core.app_context import AppContext, set_app_context
from core.extension_api import load_configured_extensions
from core.i18n import reload_translations
from core.ui_preferences import get_ui_font_family
from ui.theme import apply_application_font_preference, apply_platform_visual_overrides

_EXTENSION_LOAD_REPORT = load_configured_extensions(os.path.join(BASE_DIR, "extensions"))
for _extension_error in _EXTENSION_LOAD_REPORT.get("errors", []):
    print(f"[ALine] 扩展加载失败: {_extension_error}", file=sys.stderr)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    reload_translations()

    icon_path = os.path.join(BASE_DIR, "assets", "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    setTheme(Theme.AUTO)
    apply_platform_visual_overrides()
    apply_application_font_preference(get_ui_font_family())

    # 初始化 AppContext（核心服务依赖容器）
    # 重要: 必须复用模块级 project_manager 单例, 不能新建实例,
    # 否则 _PMProxy (menu builder) 和 app/project_tree_command_service 等
    # 通过 from core.project_manager import project_manager 引用的是不同实例,
    # 导致 set_current_project 对 command service 不生效。
    from core.project_manager import project_manager as pm
    from core.tree_manager import TreeManager
    from core.data_file_manager import DataFileManager
    from core.analysis_manager import AnalysisManager
    from core.extension_registry import extension_registry
    from core.global_assets import global_assets
    from core.shortcut_manager import shortcut_manager

    ctx = AppContext(
        project_manager=pm,
        tree_manager=TreeManager(),
        data_file_manager=DataFileManager(pm),
        analysis_manager=AnalysisManager(pm),
        extension_registry=extension_registry,
        global_assets=global_assets,
        shortcut_manager=shortcut_manager,
    )
    set_app_context(ctx)

    from ui.main_window import MainWindow
    window = MainWindow()
    minWidth, minHeight = 1600, 1000
    window.setMinimumSize(minWidth, minHeight)
    window.resize(minWidth, minHeight)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
