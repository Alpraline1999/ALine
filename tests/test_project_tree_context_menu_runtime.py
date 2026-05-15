from __future__ import annotations

import unittest
from unittest import mock

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from tests.ui_test_helpers import patch_global_assets, patch_pm, make_project


_app: QApplication | None = None


def setUpModule() -> None:
    global _app
    _app = QApplication.instance() or QApplication(sys.argv)


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


class TestProjectTreeContextMenuRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self._restore_assets = patch_global_assets()
        self.pm, self.project, self.df, self.series = make_project("tree_ctx_runtime")
        self._restore_pm = patch_pm(self.pm)
        import app.project_tree_command_service as project_tree_command_service

        self._original_command_service_pm = project_tree_command_service.project_manager
        project_tree_command_service.project_manager = self.pm
        from ui.widgets.project_tree import ProjectTreeWidget

        self.widget = ProjectTreeWidget()
        self.widget.refresh()

    def tearDown(self) -> None:
        import app.project_tree_command_service as project_tree_command_service

        self.widget.deleteLater()
        project_tree_command_service.project_manager = self._original_command_service_pm
        self._restore_pm()
        self._restore_assets()

    def _open_context_menu(self, node_id: str):
        item = self.widget._find_item(node_id)
        self.assertIsNotNone(item)
        menus = []
        pos = self.widget._tree.visualItemRect(item).center()
        with mock.patch("qfluentwidgets.RoundMenu.exec", lambda menu, *_args, **_kwargs: menus.append(menu)):
            self.widget._on_context_menu(pos)
        self.assertTrue(menus)
        menu = menus[-1]
        return {action.text(): action for action in menu.actions()}

    def test_managed_root_folder_menu_shows_new_child_folder(self) -> None:
        for group_type in ("datasets", "source_files", "images", "pictures", "analysis_result_group"):
            root = self.pm._find_folder_by_group_type(group_type)
            self.assertIsNotNone(root)
            actions = self._open_context_menu(root.id)
            self.assertIn("新建子文件夹", actions, group_type)

    def test_data_file_context_menu_remark_delete_and_rename_execute(self) -> None:
        data_node = next(node for node in self.project.tree.nodes if node.kind == "data_file" and node.data_file_id == self.df.id)

        with mock.patch("app.project_tree_command_service.NodeRemarkDialog.get_remark", return_value=("右键备注", True)):
            self._open_context_menu(data_node.id)["设置备注"].trigger()
        self.assertEqual(getattr(self.pm.get_node_by_id(data_node.id), "remark", ""), "右键备注")

        with mock.patch("ui.widgets.project_tree.TextInputDialog.get_text", return_value=("renamed.csv", True)):
            self._open_context_menu(data_node.id)["重命名"].trigger()
        self.assertEqual(self.pm.get_node_by_id(data_node.id).name, "renamed.csv")

        with mock.patch("qfluentwidgets.MessageBox.exec", return_value=True):
            self._open_context_menu(data_node.id)["删除"].trigger()
        self.assertIsNone(self.pm.get_node_by_id(data_node.id))

    def test_context_menu_actions_target_anchor_item_instead_of_previous_selection(self) -> None:
        from models.schemas import DataFile, DataSeries

        other = DataFile(name="other.csv", series=[DataSeries(name="other", x=[0.0, 1.0], y=[1.0, 2.0])])
        other_node = self.pm.add_data_file(other)
        self.widget.refresh()

        first_node = next(node for node in self.project.tree.nodes if node.kind == "data_file" and node.data_file_id == self.df.id)
        self.widget.select_node(first_node.id)

        with mock.patch("ui.widgets.project_tree.TextInputDialog.get_text", return_value=("other-renamed.csv", True)):
            self._open_context_menu(other_node.id)["重命名"].trigger()

        self.assertEqual(self.pm.get_node_by_id(other_node.id).name, "other-renamed.csv")
        self.assertEqual(self.pm.get_node_by_id(first_node.id).name, self.df.name)


if __name__ == "__main__":
    unittest.main()
