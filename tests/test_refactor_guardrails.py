from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

MAIN_FLOW_SAMPLES = [
    "打开项目",
    "共享树选择",
    "数据导入",
    "加入绘图",
    "加入处理",
    "运行分析",
    "数字化导出",
    "保存项目",
]

PHASE0_TASK_PATH = REPO_ROOT / "docs" / "refactor" / "tasks" / "phase0_task1.md"
MAIN_WINDOW_PATH = REPO_ROOT / "ui" / "main_window.py"

ALLOWED_UI_DIRECT_IMPORTS = {
    "ui/dialogs/ai_tool_dialog.py": {("core.global_assets", "global_assets")},
    "ui/dialogs/export_flow.py": {("core.project_manager", "project_manager")},
    "ui/dialogs/import_dialog.py": {("core.project_manager", "project_manager")},
    "ui/dialogs/report_template_dialog.py": {("core.global_assets", "global_assets")},
    "ui/main_window.py": {
        ("core.extension_api", "extension_registry"),
        ("core.global_assets", "global_assets"),
        ("core.project_manager", "project_manager"),
    },
    "ui/pages/analysis_page.py": {
        ("core.extension_api", "extension_registry"),
        ("core.global_assets", "global_assets"),
        ("core.project_manager", "project_manager"),
    },
    "ui/pages/chart_page.py": {
        ("core.extension_api", "extension_registry"),
        ("core.global_assets", "global_assets"),
        ("core.project_manager", "project_manager"),
    },
    "ui/pages/data_page.py": {
        ("core.extension_api", "extension_registry"),
        ("core.global_assets", "global_assets"),
        ("core.project_manager", "project_manager"),
    },
    "ui/pages/digitize_page.py": {
        ("core.extension_api", "extension_registry"),
        ("core.project_manager", "project_manager"),
    },
    "ui/pages/home_page.py": {("core.project_manager", "project_manager")},
    "ui/pages/process_page.py": {
        ("core.global_assets", "global_assets"),
        ("core.extension_api", "extension_registry"),
        ("core.project_manager", "project_manager"),
    },
    "ui/pages/settings_page.py": {
        ("core.global_assets", "global_assets"),
        ("core.project_manager", "project_manager"),
    },
    "ui/widgets/extension_options_form.py": {("core.global_assets", "global_assets")},
    "ui/widgets/extension_panel.py": {("core.global_assets", "global_assets")},
    "ui/widgets/project_tree.py": {
        ("core.extension_api", "extension_registry"),
        ("core.global_assets", "global_assets"),
        ("core.project_manager", "project_manager"),
    },
}

ALLOWED_CORE_EXTENSION_IMPORTS = {
    "core/analysis_engine.py": {"extensions.processing.extension_tools"},
    "core/extension_api.py": {"extensions.processing.extension_tools"},
}

ALLOWED_MAIN_WINDOW_PRIVATE_PAGE_ACCESSES = set()


def _parse_python(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _iter_python_files(relative_root: str) -> list[Path]:
    root = REPO_ROOT / relative_root
    return sorted(path for path in root.rglob("*.py") if path.is_file())


class _ImportVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.direct_imports: set[tuple[str, str]] = set()
        self.core_extension_imports: set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if module in {"core.project_manager", "core.global_assets", "core.extension_api"}:
            for alias in node.names:
                if alias.name in {"project_manager", "global_assets", "extension_registry"}:
                    self.direct_imports.add((module, alias.name))
        if module.startswith("extensions."):
            self.core_extension_imports.add(module)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name
            if name.startswith("extensions."):
                self.core_extension_imports.add(name)
        self.generic_visit(node)


class _MainWindowVisitor(ast.NodeVisitor):
    PAGE_ATTRS = {
        "home_page",
        "data_page",
        "chart_page",
        "process_page",
        "analysis_page",
        "digitize_page",
        "settings_page",
    }

    def __init__(self) -> None:
        self.private_page_accesses: set[str] = set()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if not node.attr.startswith("_"):
            self.generic_visit(node)
            return
        owner = node.value
        if (
            isinstance(owner, ast.Attribute)
            and owner.attr in self.PAGE_ATTRS
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "self"
        ):
            self.private_page_accesses.add(f"{owner.attr}.{node.attr}")
        self.generic_visit(node)


class TestPhase0TaskPlan(unittest.TestCase):
    def test_phase0_task_file_exists(self) -> None:
        self.assertTrue(PHASE0_TASK_PATH.exists(), "缺少 Phase 0 任务文件")

    def test_phase0_task_contains_main_flow_samples(self) -> None:
        content = PHASE0_TASK_PATH.read_text(encoding="utf-8")
        for sample in MAIN_FLOW_SAMPLES:
            self.assertIn(sample, content)


class TestArchitectureGuardrails(unittest.TestCase):
    def test_ui_direct_runtime_imports_are_frozen(self) -> None:
        actual: dict[str, set[tuple[str, str]]] = {}
        for path in _iter_python_files("ui"):
            visitor = _ImportVisitor()
            visitor.visit(_parse_python(path))
            if visitor.direct_imports:
                actual[path.relative_to(REPO_ROOT).as_posix()] = visitor.direct_imports
        self.assertEqual(ALLOWED_UI_DIRECT_IMPORTS, actual)

    def test_core_extensions_imports_are_frozen(self) -> None:
        actual: dict[str, set[str]] = {}
        for path in _iter_python_files("core"):
            visitor = _ImportVisitor()
            visitor.visit(_parse_python(path))
            if visitor.core_extension_imports:
                actual[path.relative_to(REPO_ROOT).as_posix()] = visitor.core_extension_imports
        self.assertEqual(ALLOWED_CORE_EXTENSION_IMPORTS, actual)

    def test_main_window_private_page_accesses_are_frozen(self) -> None:
        visitor = _MainWindowVisitor()
        visitor.visit(_parse_python(MAIN_WINDOW_PATH))
        self.assertEqual(ALLOWED_MAIN_WINDOW_PRIVATE_PAGE_ACCESSES, visitor.private_page_accesses)


if __name__ == "__main__":
    unittest.main()
