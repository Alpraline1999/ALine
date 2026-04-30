from __future__ import annotations

import importlib.util
import sys
import types
import unittest


def _load_command_service_module():
    fake_models = types.ModuleType("models.schemas")

    class DataFile:
        def __init__(self, name: str, source_path: str = "", series: list[object] | None = None):
            self.name = name
            self.source_path = source_path
            self.series = list(series or [])

    fake_models.DataFile = DataFile
    sys.modules["models.schemas"] = fake_models

    fake_global_assets_module = types.ModuleType("core.global_assets")

    class _FakeGlobalAssets:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str | None]] = []
            self.report_templates = {"report-1": types.SimpleNamespace(is_builtin=False)}
            self.curve_style_templates = {"curve-1": types.SimpleNamespace(is_builtin=False)}
            self.figure_templates = {"fig-1": types.SimpleNamespace(id="fig-1")}
            self.plot_themes = {"theme-1": types.SimpleNamespace(is_builtin=False)}
            self.extension_configs = {"cfg-1": types.SimpleNamespace(is_default=False)}

        def reset(self) -> None:
            self.calls.clear()

        def get_report_template(self, node_id: str):
            return self.report_templates.get(node_id)

        def get_curve_style_template(self, node_id: str):
            return self.curve_style_templates.get(node_id)

        def get_figure_template(self, node_id: str):
            return self.figure_templates.get(node_id)

        def get_plot_theme(self, node_id: str):
            return self.plot_themes.get(node_id)

        def get_extension_config(self, node_id: str):
            return self.extension_configs.get(node_id)

        def update_saved_pipeline(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_saved_pipeline", node_id, name))
            return True

        def update_report_template(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_report_template", node_id, name))
            return True

        def update_curve_style_template(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_curve_style_template", node_id, name))
            return True

        def update_figure_template(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_figure_template", node_id, name))
            return True

        def update_plot_theme(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_plot_theme", node_id, name))
            return True

        def update_extension_config(self, node_id: str, *, name: str):
            self.calls.append(("update_extension_config", node_id, name))
            return object()

        def update_ai_prompt(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_ai_prompt", node_id, name))
            return True

        def update_ai_skill(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_ai_skill", node_id, name))
            return True

        def update_ai_agent(self, node_id: str, *, name: str) -> bool:
            self.calls.append(("update_ai_agent", node_id, name))
            return True

        def delete_saved_pipeline(self, node_id: str) -> bool:
            self.calls.append(("delete_saved_pipeline", node_id, None))
            return True

        def delete_report_template(self, node_id: str) -> bool:
            self.calls.append(("delete_report_template", node_id, None))
            return True

        def delete_curve_style_template(self, node_id: str) -> bool:
            self.calls.append(("delete_curve_style_template", node_id, None))
            return True

        def delete_figure_template(self, node_id: str) -> bool:
            self.calls.append(("delete_figure_template", node_id, None))
            return True

        def delete_plot_theme(self, node_id: str) -> bool:
            self.calls.append(("delete_plot_theme", node_id, None))
            return True

        def delete_extension_config(self, node_id: str) -> bool:
            self.calls.append(("delete_extension_config", node_id, None))
            return True

        def delete_ai_prompt(self, node_id: str) -> bool:
            self.calls.append(("delete_ai_prompt", node_id, None))
            return True

        def delete_ai_skill(self, node_id: str) -> bool:
            self.calls.append(("delete_ai_skill", node_id, None))
            return True

        def delete_ai_agent(self, node_id: str) -> bool:
            self.calls.append(("delete_ai_agent", node_id, None))
            return True

    def parse_plot_style_asset_key(node_id: str) -> tuple[str, str]:
        if ":" not in node_id:
            return "theme", node_id
        return tuple(node_id.split(":", 1))  # type: ignore[return-value]

    fake_global_assets_module.global_assets = _FakeGlobalAssets()
    fake_global_assets_module.parse_plot_style_asset_key = parse_plot_style_asset_key
    sys.modules["core.global_assets"] = fake_global_assets_module

    fake_pm_module = types.ModuleType("core.project_manager")

    class _FakeProjectManager:
        def __init__(self) -> None:
            self.deleted: list[str] = []
            self.added: list[tuple[str, str | None, str, int, bool]] = []
            self.renamed_series: list[tuple[str, str]] = []
            self.removed_empty_folder_args: list[str | None] = []
            self.deleted_series: list[str] = []
            self.deleted_curves: list[str] = []
            self.source_file_batches: list[tuple[list[str], str | None, bool]] = []
            self.added_images: list[tuple[str, str, str | None]] = []
            self.added_series: list[tuple[str, object]] = []
            self.return_node = types.SimpleNamespace(id="node-1")
            self.data_files = {"df-1": types.SimpleNamespace(name="Data A")}

        def reset(self) -> None:
            self.deleted.clear()
            self.added.clear()
            self.renamed_series.clear()
            self.removed_empty_folder_args.clear()
            self.deleted_series.clear()
            self.deleted_curves.clear()
            self.source_file_batches.clear()
            self.added_images.clear()
            self.added_series.clear()
            self.return_node = types.SimpleNamespace(id="node-1")
            self.data_files = {"df-1": types.SimpleNamespace(name="Data A")}

        def delete_node(self, node_id: str) -> None:
            self.deleted.append(node_id)

        def add_data_file(self, data_file, parent_id: str | None = None, auto_rename_on_conflict: bool = False):
            self.added.append(
                (
                    data_file.name,
                    parent_id,
                    getattr(data_file, "source_path", ""),
                    len(getattr(data_file, "series", [])),
                    auto_rename_on_conflict,
                )
            )
            return self.return_node

        def rename_series(self, node_id: str, name: str) -> bool:
            self.renamed_series.append((node_id, name))
            return True

        def rename_curve(self, node_id: str, name: str) -> bool:
            return True

        def remove_empty_folders(self, root_id: str | None = None):
            self.removed_empty_folder_args.append(root_id)
            return ["f1", "f2"]

        def delete_series(self, node_id: str) -> bool:
            self.deleted_series.append(node_id)
            return True

        def delete_curve(self, node_id: str) -> bool:
            self.deleted_curves.append(node_id)
            return True

        def add_source_files(self, paths: list[str], parent_id: str | None = None, auto_rename_on_conflict: bool = False):
            self.source_file_batches.append((list(paths), parent_id, auto_rename_on_conflict))
            return [types.SimpleNamespace(id="src-node-1"), types.SimpleNamespace(id="src-node-2")]

        def add_image(self, path: str, name: str, parent_id: str | None = None):
            self.added_images.append((path, name, parent_id))
            return types.SimpleNamespace(id=f"image-{len(self.added_images)}")

        def get_data_file(self, data_file_id: str):
            return self.data_files.get(data_file_id)

        def add_series_to_data_file(self, data_file_id: str, series: object) -> bool:
            self.added_series.append((data_file_id, series))
            return True

    fake_pm_module.project_manager = _FakeProjectManager()
    sys.modules["core.project_manager"] = fake_pm_module

    spec = importlib.util.spec_from_file_location(
        "test_project_tree_command_service_module",
        "/home/alpraline/Projects/Python/ALine/app/project_tree_command_service.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


module = _load_command_service_module()
ProjectTreeCommandService = module.ProjectTreeCommandService
project_manager = module.project_manager
global_assets = module.global_assets


class _FakeImportDialog:
    def __init__(
        self,
        *,
        accepted: bool = True,
        file_name: str = "Imported",
        source_path: str = "sample.csv",
        series_list: list[object] | None = None,
    ) -> None:
        self.accepted = accepted
        self.file_name = file_name
        self.source_path = source_path
        self.series_list = list(series_list or [{"id": "s1"}, {"id": "s2"}])

    def exec(self) -> bool:
        return self.accepted

    def get_results(self) -> list[object]:
        return list(self.series_list)

    def get_file_name(self) -> str:
        return self.file_name

    def get_source_path(self) -> str:
        return self.source_path


class TestProjectTreeCommandService(unittest.TestCase):
    def setUp(self) -> None:
        project_manager.reset()
        global_assets.reset()

    def _make_service(self, **overrides):
        state = {"calls": [], "warnings": [], "successes": [], "last_error": ""}

        defaults = dict(
            confirm_delete=lambda *_args: True,
            confirm_batch_delete=lambda *_args: True,
            choose_file=lambda *_args: "",
            choose_files=lambda *_args: [],
            prompt_text=lambda *_args: ("", False),
            prompt_existing_text=lambda *_args: ("", False),
            choose_item=lambda *_args: ("", False),
            create_child_folder=lambda *_args: None,
            create_source_file_import_dialog=lambda *_args: _FakeImportDialog(),
            configure_source_file_import_target=lambda dialog, target_id: state["calls"].append(
                ("configure_import_target", target_id)
            ),
            move_node_to_target=lambda *_args: False,
            supports_data_file_import=lambda *_args: False,
            supports_digitize_import=lambda *_args: False,
            linked_tree_node_id=lambda *_args: None,
            notify_warning=lambda title, content: state["warnings"].append((title, content)),
            notify_success=lambda title, content: state["successes"].append((title, content)),
            refresh=lambda: state["calls"].append("refresh"),
            select_node=lambda node_id: state["calls"].append(f"select:{node_id}"),
            project_modified=lambda: state["calls"].append("modified"),
            last_error_message=lambda: state["last_error"],
        )
        defaults.update(overrides)
        return ProjectTreeCommandService(**defaults), state

    def test_delete_node_confirms_then_refreshes(self) -> None:
        service, state = self._make_service()

        service.delete_node("n1", "Node 1")

        self.assertEqual(["n1"], project_manager.deleted)
        self.assertEqual(["refresh", "modified"], state["calls"])

    def test_add_dataset_node_creates_and_selects(self) -> None:
        service, state = self._make_service(prompt_text=lambda *_args: ("dataset-a", True))

        service.add_dataset_node("parent-1")

        self.assertEqual([("dataset-a", "parent-1", "", 0, False)], project_manager.added)
        self.assertEqual(["refresh", "select:node-1", "modified"], state["calls"])

    def test_rename_virtual_series_renames_then_refreshes(self) -> None:
        service, state = self._make_service(prompt_existing_text=lambda *_args: ("series-b", True))

        service.rename_virtual("series", "s1", "old")

        self.assertEqual([("s1", "series-b")], project_manager.renamed_series)
        self.assertEqual(["refresh", "modified"], state["calls"])

    def test_prune_empty_folders_reports_success(self) -> None:
        service, state = self._make_service()

        service.prune_empty_folders("root-1", scope_label="测试树")

        self.assertEqual(["root-1"], project_manager.removed_empty_folder_args)
        self.assertEqual(["refresh", "modified"], state["calls"])
        self.assertEqual([("清理完成", "已移除 2 个空文件夹")], state["successes"])

    def test_delete_virtual_series_deletes_then_refreshes(self) -> None:
        service, state = self._make_service()

        service.delete_virtual("series", "s99", "Series 99")

        self.assertEqual(["s99"], project_manager.deleted_series)
        self.assertEqual(["refresh", "modified"], state["calls"])

    def test_delete_batch_deletes_all_payloads(self) -> None:
        service, state = self._make_service()

        service.delete_batch([
            {"kind": "series", "node_id": "s1", "name": "S1"},
            {"kind": "curve", "node_id": "c1", "name": "C1"},
            {"kind": "data_file", "node_id": "d1", "name": "D1"},
        ])

        self.assertEqual(["s1"], project_manager.deleted_series)
        self.assertEqual(["c1"], project_manager.deleted_curves)
        self.assertEqual(["d1"], project_manager.deleted)
        self.assertEqual(["refresh", "modified"], state["calls"])

    def test_move_batch_uses_target_selection_and_warns_on_failures(self) -> None:
        service, state = self._make_service(
            choose_item=lambda *_args: ("目标A", True),
            move_node_to_target=lambda _kind, node_id, _target_id: node_id == "ok1",
        )

        service.move_batch(
            [{"kind": "series", "node_id": "ok1", "name": "OK"}, {"kind": "curve", "node_id": "bad1", "name": "BAD"}],
            [("目标A", "target-a"), ("目标B", "target-b")],
        )

        self.assertEqual(["refresh", "modified"], state["calls"])
        self.assertEqual([("批量移动未完成", "有 1 项移动失败")], state["warnings"])

    def test_move_virtual_moves_then_refreshes(self) -> None:
        service, state = self._make_service(
            choose_item=lambda *_args: ("目标A", True),
            move_node_to_target=lambda kind, node_id, target_id: (kind, node_id, target_id) == ("series", "ok2", "target-a"),
        )

        service.move_virtual("series", "ok2", [("目标A", "target-a"), ("目标B", "target-b")])

        self.assertEqual(["refresh", "modified"], state["calls"])

    def test_rename_global_pipeline_refreshes(self) -> None:
        service, state = self._make_service(prompt_existing_text=lambda *_args: ("Pipeline B", True))

        service.rename_global("global_pipeline", "pipeline-1", "Pipeline A")

        self.assertEqual([("update_saved_pipeline", "pipeline-1", "Pipeline B")], global_assets.calls)
        self.assertEqual(["refresh", "modified"], state["calls"])

    def test_delete_global_report_template_refreshes(self) -> None:
        service, state = self._make_service()

        service.delete_global("global_report_template", "report-1", "Report A")

        self.assertEqual([("delete_report_template", "report-1", None)], global_assets.calls)
        self.assertEqual(["refresh", "modified"], state["calls"])

    def test_import_source_files_refreshes_and_selects_last_node(self) -> None:
        service, state = self._make_service(choose_files=lambda *_args: ["a.csv", "b.csv"])

        service.import_source_files("parent-s")

        self.assertEqual([(["a.csv", "b.csv"], "parent-s", True)], project_manager.source_file_batches)
        self.assertEqual(["refresh", "select:src-node-2", "modified"], state["calls"])

    def test_import_digitize_images_reports_success_and_partial_failures(self) -> None:
        linked_map = {"image-1": "img-node-1", "image-2": "img-node-2"}
        service, state = self._make_service(
            choose_files=lambda *_args: ["ok1.png", "bad.txt", "ok2.jpg"],
            supports_digitize_import=lambda path: path.endswith((".png", ".jpg")),
            linked_tree_node_id=lambda _kind, _attr, value: linked_map.get(value),
        )

        service.import_digitize_images("parent-i")

        self.assertEqual(
            [("ok1.png", "ok1.png", "parent-i"), ("ok2.jpg", "ok2.jpg", "parent-i")],
            project_manager.added_images,
        )
        self.assertEqual(["refresh", "select:img-node-2", "modified"], state["calls"])
        self.assertEqual([("导入完成", "已导入 2 张图片到数字化")], state["successes"])
        self.assertEqual([("部分导入失败", "以下图片未能导入: bad.txt")], state["warnings"])

    def test_import_data_file_creates_dataset_and_selects_node(self) -> None:
        dialog = _FakeImportDialog(file_name="Imported CSV", source_path="import.csv", series_list=[{"id": "s1"}])
        service, state = self._make_service(
            choose_file=lambda *_args: "import.csv",
            supports_data_file_import=lambda *_args: True,
            create_source_file_import_dialog=lambda *_args: dialog,
        )

        service.import_data_file("folder-1")

        self.assertEqual([("Imported CSV", "folder-1", "import.csv", 1, True)], project_manager.added)
        self.assertEqual([("导入成功", "已导入 1 条数据系列到数据文件 Imported CSV")], state["successes"])
        self.assertEqual([("configure_import_target", None), "refresh", "select:node-1", "modified"], state["calls"])

    def test_import_source_file_as_dataset_appends_to_existing_data_file(self) -> None:
        dialog = _FakeImportDialog(file_name="Ignored", source_path="drop.csv", series_list=[{"id": "s1"}, {"id": "s2"}])
        service, state = self._make_service(
            supports_data_file_import=lambda *_args: True,
            create_source_file_import_dialog=lambda *_args: dialog,
            linked_tree_node_id=lambda kind, attr, value: "tree-node-9" if (kind, attr, value) == ("data_file", "data_file_id", "df-1") else None,
        )

        selected = service.import_source_file_as_dataset("drop.csv", target_data_file_id="df-1")

        self.assertEqual("tree-node-9", selected)
        self.assertEqual([("configure_import_target", "df-1")], state["calls"])
        self.assertEqual([("df-1", {"id": "s1"}), ("df-1", {"id": "s2"})], project_manager.added_series)
        self.assertEqual([("导入成功", "已导入 2 条数据系列到数据文件 Data A")], state["successes"])


if __name__ == "__main__":
    unittest.main()
