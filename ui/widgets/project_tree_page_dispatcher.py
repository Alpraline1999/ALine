from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


class TreeSignalLike(Protocol):
    def emit(self, kind: str, node_id: str) -> None: ...


@dataclass(slots=True)
class ProjectTreePageDispatcher:
    node_selected_signal: TreeSignalLike
    node_activated_signal: TreeSignalLike

    def emit_selected(self, kind: str, node_id: str) -> None:
        self.node_selected_signal.emit(kind, node_id)

    def emit_activated(self, kind: str, node_id: str) -> None:
        self.node_activated_signal.emit(kind, node_id)

    def make_activation_callback(self, kind: str, node_id: str) -> Callable[[], None]:
        return lambda: self.emit_activated(kind, node_id)
