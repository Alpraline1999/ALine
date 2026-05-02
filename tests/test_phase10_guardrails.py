from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    if QApplication.instance() is None:
        _app = QApplication(sys.argv)
    else:
        _app = QApplication.instance()


def tearDownModule() -> None:
    global _app
    app = QApplication.instance()
    if app is not None:
        for widget in list(app.topLevelWidgets()):
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                continue
        app.processEvents()
    _app = None


class _FakeViewport:
    def mapToGlobal(self, pos: QPoint) -> QPoint:
        return pos


class _FakeTree:
    def viewport(self) -> _FakeViewport:
        return _FakeViewport()


class _FakeMenu:
    def __init__(self) -> None:
        self.exec_pos: QPoint | None = None

    def actions(self) -> list[int]:
        return [1]

    def exec(self, pos: QPoint) -> None:
        self.exec_pos = pos


class _FakeItem:
    is_default = False

    def text(self, _column: int) -> str:
        return "示例配置"


class _FakeDispatcher:
    def make_activation_callback(self, _kind: str, _node_id: str):
        return lambda: None


class TestPhase10Guardrails(unittest.TestCase):
    def test_safe_filename_sanitizes_reserved_chars(self) -> None:
        from core.project_manager import project_manager

        self.assertEqual("a_b_c_d", project_manager._safe_filename("a:b*c?d"))

    def test_settings_page_constructs_external_extension_dir_card(self) -> None:
        from ui.pages.settings_page import SettingsPage
        from ui.pages.settings_page_support import MutableFolderListSettingCard

        page = SettingsPage()
        self.assertIsInstance(page._external_extensions_dirs_card, MutableFolderListSettingCard)

    def test_extension_config_export_and_default_roundtrip(self) -> None:
        from core.global_assets import GlobalAssetManager

        with tempfile.TemporaryDirectory() as temp_dir:
            manager = GlobalAssetManager(asset_path=Path(temp_dir) / "global_assets.json")
            saved = manager.add_extension_config(
                category="processing",
                extension_type="phase10_guardrail_probe",
                extension_name="Phase10 Probe",
                extension_version="1.0.0",
                name="方案A",
                options={"factor": 2.0},
            )
            duplicate = manager.duplicate_extension_config(saved.id, "方案B")
            self.assertIsNotNone(duplicate)

            payload = manager.export_extension_config_to_json(duplicate.id)
            self.assertIsNotNone(payload)
            self.assertEqual("方案B", payload["name"])

            marked = manager.set_extension_default_config(duplicate.id)
            self.assertIsNotNone(marked)
            self.assertTrue(manager.get_extension_config(duplicate.id).is_default)

    def test_project_tree_global_extension_menu_executes_with_position_and_callbacks(self) -> None:
        from ui.widgets.project_tree_menu_commands import ProjectTreeMenuBuilder

        calls: list[tuple[str, str]] = []

        builder = ProjectTreeMenuBuilder(
            tree_widget=object(),
            add_menu_action=lambda *args, **kwargs: None,
            append_menu_section=lambda *args, **kwargs: None,
            append_tree_scope_actions=lambda *args, **kwargs: None,
            batch_action_payloads=lambda *args, **kwargs: [],
            common_batch_move_choices=lambda *args, **kwargs: [],
            command_service=object(),
            page_dispatcher=_FakeDispatcher(),
            dialog_parent=lambda: None,
            refresh=lambda: None,
            select_node=lambda *args, **kwargs: None,
            project_modified=lambda: None,
            tree_view=_FakeTree(),
            selected_items_for_context_menu=lambda item: [item],
            move_target_choices=lambda *args, **kwargs: [],
            move_node_to_target=lambda *args, **kwargs: None,
            is_protected_folder=lambda *args, **kwargs: False,
            folder_collection_group=lambda *args, **kwargs: None,
            is_focus_active=lambda: False,
            focus_selected_item=lambda: None,
            clear_focus=lambda: None,
            rename_selected_item=lambda: None,
            can_edit_global_asset=lambda *args, **kwargs: False,
            _extension_config_sort_key=lambda obj: (0, 0, "", ""),
            _parse_extension_config_group_node_id=lambda node_id: node_id if node_id else None,
            _cmd_create_extension_config=lambda node_id: calls.append(("create", node_id)),
            _cmd_duplicate_extension_config=lambda node_id: calls.append(("duplicate", node_id)),
            _cmd_export_extension_config=lambda node_id: calls.append(("export", node_id)),
            _cmd_set_default_extension_config=lambda node_id: calls.append(("default", node_id)),
            _cmd_delete=lambda *args, **kwargs: None,
            _cmd_delete_batch=lambda *args, **kwargs: None,
            _cmd_delete_virtual=lambda *args, **kwargs: None,
            _cmd_delete_global=lambda *args, **kwargs: None,
            _cmd_add_child_folder=lambda *args, **kwargs: None,
            _cmd_add_dataset_node=lambda *args, **kwargs: None,
            _cmd_import_data_file=lambda *args, **kwargs: None,
            _cmd_import_source_files=lambda *args, **kwargs: None,
            _cmd_import_digitize_images=lambda *args, **kwargs: None,
            _cmd_rename_global=lambda *args, **kwargs: None,
            _cmd_prune_empty_folders=lambda *args, **kwargs: None,
            _cmd_move_batch=lambda *args, **kwargs: None,
            _cmd_move_virtual=lambda *args, **kwargs: None,
            _open_picture_folder=lambda *args, **kwargs: None,
            _open_source_file_folder=lambda *args, **kwargs: None,
            _SYNTHETIC_GLOBAL_KINDS=frozenset({"global_extension_config"}),
            _MANAGED_FOLDER_GROUP_TYPES=frozenset(),
            _PICTURE_GROUP_ICON=object(),
            _SOURCE_FOLDER_ICON=object(),
            _NEW_DATASET_ACTION_ICON=object(),
            _IMPORT_DATA_ACTION_ICON=object(),
            _OPEN_DIGITIZE_ACTION_ICON=object(),
            _PICTURE_GROUP_ICON_v2=object(),
        )
        menu = _FakeMenu()
        manage_entries: list[tuple[object, str, object]] = []

        builder._build_global_kind_menu(menu, QPoint(0, 0), "global_extension_config", "cfg-1", _FakeItem(), manage_entries)

        actions = {label: callback for _, label, callback in manage_entries}
        actions["导出"]()
        actions["设为默认"]()

        self.assertIn(("export", "cfg-1"), calls)
        self.assertIn(("default", "cfg-1"), calls)
        self.assertEqual(QPoint(0, 0), menu.exec_pos)
