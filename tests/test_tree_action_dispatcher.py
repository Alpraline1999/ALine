from __future__ import annotations

import unittest

from app.messages import AppCommandType, TreeCommandType
from app.tree_action_dispatcher import ProjectTreeActionDispatcher


class TestProjectTreeActionDispatcher(unittest.TestCase):
    def test_dispatch_selected_builds_tree_select_command(self) -> None:
        commands = []
        dispatcher = ProjectTreeActionDispatcher(
            command_handler=commands.append,
            project_id_getter=lambda: "p1",
        )

        command = dispatcher.dispatch_selected("data_file", "n1")

        self.assertEqual(AppCommandType.TREE, command.command_type)
        self.assertIs(command, commands[0])
        self.assertEqual(TreeCommandType.SELECT, command.tree_command.command_type)
        self.assertEqual("data_file", command.tree_command.node.kind)
        self.assertEqual("n1", command.tree_command.node.node_id)
        self.assertEqual("p1", command.tree_command.node.project_id)
        self.assertFalse(command.tree_command.node.synthetic)

    def test_dispatch_activated_marks_global_nodes_as_synthetic(self) -> None:
        commands = []
        dispatcher = ProjectTreeActionDispatcher(
            command_handler=commands.append,
            project_id_getter=lambda: None,
        )

        command = dispatcher.dispatch_activated("global_report_template", "g1")

        self.assertEqual(TreeCommandType.ACTIVATE, command.tree_command.command_type)
        self.assertTrue(command.tree_command.node.synthetic)
        self.assertIsNone(command.tree_command.node.project_id)
