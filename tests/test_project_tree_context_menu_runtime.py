from __future__ import annotations

import unittest
from unittest import mock
from pathlib import Path
import tempfile

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

    def test_empty_managed_child_folder_remains_visible_under_filter(self) -> None:
        root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(root)
        child = self.pm.add_folder("Empty Child", parent_id=root.id, group_type="datasets")
        self.assertIsNotNone(child)

        self.widget.set_filter_kinds(["data_file"])
        self.widget.refresh()

        self.assertIsNotNone(self.widget._find_item(child.id))

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

    def test_folder_context_menu_remark_delete_and_rename_execute(self) -> None:
        root = self.pm._find_folder_by_group_type("datasets")
        self.assertIsNotNone(root)
        folder = self.pm.add_folder("Folder A", parent_id=root.id, group_type="datasets")
        self.assertIsNotNone(folder)
        self.widget.refresh()

        with mock.patch("app.project_tree_command_service.NodeRemarkDialog.get_remark", return_value=("右键文件夹备注", True)):
            self._open_context_menu(folder.id)["设置备注"].trigger()
        self.assertEqual(getattr(self.pm.get_node_by_id(folder.id), "remark", ""), "右键文件夹备注")

        with mock.patch("ui.widgets.project_tree.TextInputDialog.get_text", return_value=("Folder Renamed", True)):
            self._open_context_menu(folder.id)["重命名"].trigger()
        self.assertEqual(self.pm.get_node_by_id(folder.id).name, "Folder Renamed")

        with mock.patch("qfluentwidgets.MessageBox.exec", return_value=True):
            self._open_context_menu(folder.id)["删除"].trigger()
        self.assertIsNone(self.pm.get_node_by_id(folder.id))

    def test_managed_root_folder_import_actions_execute(self) -> None:
        class _FakeImportDialog:
            def __init__(self, file_path: str):
                self._file_path = file_path

            def exec(self) -> bool:
                return True

            def get_results(self) -> list[object]:
                from models.schemas import DataSeries

                return [DataSeries(name="Imported Series", x=[1.0, 2.0], y=[3.0, 4.0])]

            def get_file_name(self) -> str:
                return Path(self._file_path).name

            def get_source_path(self) -> str:
                return self._file_path

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_file = tmp_path / "source.txt"
            source_file.write_text("abc", encoding="utf-8")
            image_file = tmp_path / "image.png"
            image_file.write_bytes(b"png")
            data_file = tmp_path / "data.csv"
            data_file.write_text("x,y\n1,2\n", encoding="utf-8")

            source_root = self.pm._find_folder_by_group_type("source_files")
            datasets_root = self.pm._find_folder_by_group_type("datasets")
            images_root = self.pm._find_folder_by_group_type("images")
            self.assertIsNotNone(source_root)
            self.assertIsNotNone(datasets_root)
            self.assertIsNotNone(images_root)

            with mock.patch.object(self.widget._command_service, "choose_files", return_value=[str(source_file)]):
                self._open_context_menu(source_root.id)["批量导入源文件..."].trigger()
            self.assertIsNotNone(next((node for node in self.pm.current_project.tree.nodes if node.kind == "source_file" and node.name == "source.txt"), None))

            with mock.patch.object(self.widget._command_service, "choose_file", return_value=str(data_file)), \
                 mock.patch.object(self.widget._command_service, "create_source_file_import_dialog", side_effect=lambda path: _FakeImportDialog(path)):
                self._open_context_menu(datasets_root.id)["导入数据文件..."].trigger()
            self.assertIsNotNone(next((node for node in self.pm.current_project.tree.nodes if node.kind == "data_file" and node.name == "data.csv"), None))

            with mock.patch.object(self.widget._command_service, "choose_files", return_value=[str(image_file)]):
                self._open_context_menu(images_root.id)["导入图片..."].trigger()
            self.assertIsNotNone(next((node for node in self.pm.current_project.tree.nodes if node.kind == "image_work" and node.name == "image.png"), None))

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

    def test_context_menu_actions_use_anchor_project_when_selection_points_to_another_project(self) -> None:
        from models.schemas import DataFile, DataSeries

        other_project = self.pm.create_new("tree_ctx_runtime_other")
        other_df = DataFile(name="other_project.csv", series=[DataSeries(name="other_project", x=[1.0, 2.0], y=[2.0, 3.0])])
        other_node = self.pm.add_data_file(other_df)
        self.widget.refresh()

        first_project_node = next(
            node
            for node in self.project.tree.nodes
            if node.kind == "data_file" and node.data_file_id == self.df.id
        )
        self.widget.select_node(first_project_node.id)

        with mock.patch("app.project_tree_command_service.NodeRemarkDialog.get_remark", return_value=("跨项目备注", True)):
            self._open_context_menu(other_node.id)["设置备注"].trigger()

        self.assertEqual(self.pm.get_node_by_id(other_node.id).remark, "跨项目备注")
        self.assertEqual(self.pm.current_project_id, other_project.id)


if __name__ == "__main__":
    unittest.main()
