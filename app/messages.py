from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


@dataclass(frozen=True)
class NodeRef:
    kind: str
    node_id: str
    project_id: str | None = None
    synthetic: bool = False


class TreeCommandType(str, Enum):
    SELECT = "select"
    ACTIVATE = "activate"
    CONTEXT_ACTION = "context_action"
    DROP = "drop"


@dataclass(frozen=True)
class TreeCommand:
    command_type: TreeCommandType
    node: NodeRef
    action: str | None = None
    target: NodeRef | None = None


class AppCommandType(str, Enum):
    NEW_PROJECT = "new_project"
    OPEN_PROJECT = "open_project"
    SAVE_PROJECT = "save_project"
    CLOSE_PROJECT = "close_project"
    NAVIGATE = "navigate"
    TREE = "tree"


@dataclass(frozen=True)
class AppCommand:
    command_type: AppCommandType
    tree_command: TreeCommand | None = None
    destination: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


class SessionEventType(str, Enum):
    PROJECT_CREATED = "project_created"
    PROJECT_OPENED = "project_opened"
    PROJECT_CLOSED = "project_closed"
    PROJECT_MODIFIED = "project_modified"
    PROJECT_SAVED = "project_saved"
    ASSETS_RELOADED = "assets_reloaded"
    TREE_REFRESH_REQUESTED = "tree_refresh_requested"


@dataclass(frozen=True)
class SessionEvent:
    event_type: SessionEventType
    project_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)
