from __future__ import annotations

import importlib.util
import unittest
from unittest.mock import Mock


def _load_builder_module():
    spec = importlib.util.spec_from_file_location(
        "test_project_tree_builder_module",
        "/home/alpraline/Projects/Python/ALine/ui/widgets/project_tree_builder.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


ProjectTreeBuilder = _load_builder_module().ProjectTreeBuilder


class _FakeViewport:
    def __init__(self) -> None:
        self.updated = False

    def update(self) -> None:
        self.updated = True


class _FakeTree:
    def __init__(self) -> None:
        self.block_calls: list[bool] = []
        self.cleared = False
        self.viewport_obj = _FakeViewport()
        self.geometry_updated = False

    def blockSignals(self, value: bool) -> None:
        self.block_calls.append(value)

    def clear(self) -> None:
        self.cleared = True

    def addTopLevelItem(self, _item) -> None:
        pass

    def viewport(self) -> _FakeViewport:
        return self.viewport_obj

    def updateGeometry(self) -> None:
        self.geometry_updated = True


class _FakeOwner:
    def __init__(self) -> None:
        self._focus_root_group_types: list[str] = []
        self._name_display_mode = "elide"
        self._projects: list[object] = []
        self._tree = _FakeTree()
        self._capture_expansion_state = Mock(return_value={"a": True})
        self._current_item_key = Mock(return_value="node-1")
        self._build_children = Mock()
        self._build_global_assets_root = Mock()
        self._restore_expansion_state = Mock()
        self._apply_focus_view = Mock(return_value="node-1")
        self._restore_selection = Mock()
        self._apply_name_display_mode = Mock()
        self._schedule_wrapped_item_size_hint_update = Mock()
        self.refreshed_emit = Mock()
        self._tree_node_sort_key = Mock(return_value=(0, "a"))
        self._canonical_group_type = Mock(return_value="datasets")
        self._make_item = Mock(return_value="item")
        self._make_project_item = Mock(return_value=_FakeProjectItem())


class _FakeProjectItem:
    def __init__(self) -> None:
        self.expanded = False

    def setExpanded(self, value: bool) -> None:
        self.expanded = value


class TestProjectTreeBuilder(unittest.TestCase):
    def test_build_without_projects_only_builds_global_assets(self) -> None:
        owner = _FakeOwner()
        ProjectTreeBuilder().build(owner)

        self.assertEqual([True, False], owner._tree.block_calls)
        self.assertTrue(owner._tree.cleared)
        owner._build_global_assets_root.assert_called_once()
        owner.refreshed_emit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
