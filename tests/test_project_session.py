from __future__ import annotations

import unittest

from core.project_session import ProjectSession


class TestProjectSession(unittest.TestCase):
    def test_project_session_proxies_runtime_state(self) -> None:
        calls: list[object] = []
        project = type("Project", (), {"id": "p1", "is_modified": False})()
        session = ProjectSession(
            list_projects=lambda: [project],
            get_current_project=lambda: project,
            get_current_project_id=lambda: "p1",
            set_current_project_id=lambda project_id: calls.append(("set_current", project_id)),
            create_project=lambda name, parent_dir, create_structure: {"name": name, "parent_dir": parent_dir, "create_structure": create_structure},
            open_project=lambda path: {"opened": path},
            save_project=lambda path=None: path or "saved.aline",
            close_current_project_cb=lambda: calls.append("close_current"),
            close_project_cb=lambda project_id: calls.append(("close", project_id)),
        )

        self.assertEqual([project], session.projects)
        self.assertIs(project, session.current_project)
        self.assertEqual("p1", session.current_project_id)
        self.assertEqual({"name": "Demo", "parent_dir": None, "create_structure": False}, session.create_new("Demo"))
        self.assertEqual({"opened": "demo.aline"}, session.open("demo.aline"))
        self.assertEqual("saved.aline", session.save())

        session.set_current_project("p2")
        session.close_project("p1")
        session.close_current_project()
        session.mark_current_project_modified()

        self.assertTrue(project.is_modified)
        self.assertEqual([("set_current", "p2"), ("close", "p1"), "close_current"], calls)


if __name__ == "__main__":
    unittest.main()
