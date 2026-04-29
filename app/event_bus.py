from __future__ import annotations

from collections import defaultdict
from typing import Callable, DefaultDict, Generic, TypeVar


EventT = TypeVar("EventT")


class EventBus:
    """Minimal typed event bus used by the staged AppShell refactor."""

    def __init__(self) -> None:
        self._subscribers: DefaultDict[type[object], list[Callable[[object], None]]] = defaultdict(list)

    def subscribe(self, event_type: type[EventT], handler: Callable[[EventT], None]) -> Callable[[], None]:
        bucket = self._subscribers[event_type]
        bucket.append(handler)

        def unsubscribe() -> None:
            if handler in bucket:
                bucket.remove(handler)
            if not bucket:
                self._subscribers.pop(event_type, None)

        return unsubscribe

    def publish(self, event: object) -> None:
        for handler in list(self._subscribers.get(type(event), [])):
            handler(event)
