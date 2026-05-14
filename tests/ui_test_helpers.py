"""
test_ui.py 共享测试夹具和辅助函数。

使用时 from tests.ui_test_helpers import *
"""
from __future__ import annotations

import gc
import os
import sys
import tempfile
import warnings
from pathlib import Path
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
warnings.filterwarnings(
    "ignore",
    message=r".*QMouseEvent\.globalPos\(\) const.*deprecated.*",
    category=DeprecationWarning,
)

# 项目根路径
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest

_app: QApplication | None = None


def setUpModule():
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv)
    else:
        _app = cast(QApplication | None, QApplication.instance())


def tearDownModule():
    global _app
    app = cast(QApplication | None, QApplication.instance())
    if app is None:
        return
    for widget in list(app.topLevelWidgets()):
        try:
            widget.close()
            widget.deleteLater()
        except RuntimeError:
            continue
    app.processEvents()
    try:
        import shiboken6
        shiboken6.delete(app)
    except Exception:
        pass
    _app = None
    gc.collect()


def make_project(name="ui_test"):
    """创建带迁移的测试项目（使用独立 ProjectManager）"""
    from core.project_manager import ProjectManager
    from models.schemas import DataFile, DataSeries
    pm = ProjectManager()
    p = pm.create_new(name)
    s = DataSeries(name="s1", x=[1.0, 2.0, 3.0, 4.0, 5.0],
                   y=[2.0, 4.0, 6.0, 8.0, 10.0])
    df = DataFile(name="test.csv", series=[s])
    pm.add_data_file(df)
    return pm, p, df, s


_PM_MODULES = [
    "core.project_manager",
    "ai.command_layer",
    "ui.dialogs.export_flow",
    "ui.dialogs.import_dialog",
    "ui.pages.data_page",
    "ui.pages.chart_page",
    "ui.pages.process_page",
    "ui.pages.analysis_page",
    "ui.pages.digitize_page",
    "ui.widgets.project_tree",
    "ui.main_window",
]


def patch_pm(pm):
    """Patch project_manager in all relevant modules and return restorer."""
    import importlib
    saved = {}
    for mod_name in _PM_MODULES:
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "project_manager"):
                saved[mod_name] = mod.project_manager
                mod.project_manager = pm
        except ImportError:
            pass

    def restore():
        for mod_name, orig in saved.items():
            try:
                mod = importlib.import_module(mod_name)
                mod.project_manager = orig
            except ImportError:
                pass

    return restore


def patch_global_assets():
    from core.global_assets import GlobalAssets, global_assets

    temp_dir = tempfile.TemporaryDirectory()
    old_path = global_assets._asset_path
    old_cache = global_assets._cache
    global_assets._asset_path = Path(temp_dir.name) / "global_assets.json"
    global_assets._cache = GlobalAssets()
    global_assets.save()

    def restore():
        global_assets._asset_path = old_path
        global_assets._cache = old_cache
        temp_dir.cleanup()

    return restore


def analysis_result_save_plans(pm, *result_names, parent_id=None):
    from ui.dialogs.export_flow import AnalysisResultSavePlan

    target_parent_id = parent_id
    if target_parent_id is None:
        analysis_root = pm._find_folder_by_group_type("analysis_result_group")
        if analysis_root is None:
            raise AssertionError("analysis_result_group root not found")
        target_parent_id = analysis_root.id

    return [
        AnalysisResultSavePlan(result_name=result_name, target_parent_id=target_parent_id)
        for result_name in result_names
    ]
