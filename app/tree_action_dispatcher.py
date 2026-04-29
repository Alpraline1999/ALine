from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .messages import AppCommand, AppCommandType, NodeRef, TreeCommand, TreeCommandType


@dataclass(slots=True)
class ProjectTreeActionDispatcher:
    command_handler: Callable[[AppCommand], None]
    project_id_getter: Callable[[], str | None]

    def dispatch_selected(self, kind: str, node_id: str) -> AppCommand:
        command = self._build_command(TreeCommandType.SELECT, kind, node_id)
        self.command_handler(command)
        return command

    def dispatch_activated(self, kind: str, node_id: str) -> AppCommand:
        command = self._build_command(TreeCommandType.ACTIVATE, kind, node_id)
        self.command_handler(command)
        return command

    def _build_command(self, command_type: TreeCommandType, kind: str, node_id: str) -> AppCommand:
        node = NodeRef(
            kind=kind,
            node_id=node_id,
            project_id=self.project_id_getter(),
            synthetic=kind.startswith("global_"),
        )
        return AppCommand(
            command_type=AppCommandType.TREE,
            tree_command=TreeCommand(command_type=command_type, node=node),
        )
