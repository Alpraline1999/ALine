from __future__ import annotations

import importlib.util
import sys
import unittest


def _load_dispatcher_module():
    spec = importlib.util.spec_from_file_location(
        "test_project_tree_page_dispatcher_module",
        "/home/alpraline/Projects/Python/ALine/ui/widgets/project_tree_page_dispatcher.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ProjectTreePageDispatcher = _load_dispatcher_module().ProjectTreePageDispatcher


class _FakeSignal:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def emit(self, kind: str, node_id: str) -> None:
        self.calls.append((kind, node_id))


class TestProjectTreePageDispatcher(unittest.TestCase):
    def test_emit_selected_routes_to_selected_signal(self) -> None:
        selected = _FakeSignal()
        activated = _FakeSignal()
        dispatcher = ProjectTreePageDispatcher(selected, activated)

        dispatcher.emit_selected("data_file", "n1")

        self.assertEqual([("data_file", "n1")], selected.calls)
        self.assertEqual([], activated.calls)

    def test_activation_callback_routes_to_activated_signal(self) -> None:
        selected = _FakeSignal()
        activated = _FakeSignal()
        dispatcher = ProjectTreePageDispatcher(selected, activated)

        dispatcher.make_activation_callback("series_to_chart", "s1")()

        self.assertEqual([], selected.calls)
        self.assertEqual([("series_to_chart", "s1")], activated.calls)


if __name__ == "__main__":
    unittest.main()
