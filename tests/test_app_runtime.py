from __future__ import annotations

import unittest

from app.context import AppContext
from app.event_bus import EventBus
from app.messages import (
    AppCommand,
    AppCommandType,
    NodeRef,
    SessionEvent,
    SessionEventType,
    TreeCommand,
    TreeCommandType,
)


class TestEventBus(unittest.TestCase):
    def test_publish_to_matching_subscribers(self) -> None:
        bus = EventBus()
        events: list[SessionEvent] = []
        bus.subscribe(SessionEvent, events.append)

        event = SessionEvent(SessionEventType.PROJECT_OPENED, project_id="p1")
        bus.publish(event)

        self.assertEqual([event], events)

    def test_unsubscribe_stops_delivery(self) -> None:
        bus = EventBus()
        events: list[SessionEvent] = []
        unsubscribe = bus.subscribe(SessionEvent, events.append)

        unsubscribe()
        bus.publish(SessionEvent(SessionEventType.PROJECT_SAVED, project_id="p1"))

        self.assertEqual([], events)


class TestAppContext(unittest.TestCase):
    def test_app_context_accepts_injected_runtime_dependencies(self) -> None:
        project_session = object()
        asset_catalog = object()
        extension_runtime = object()
        context = AppContext(
            project_session=project_session,
            asset_catalog=asset_catalog,
            extension_runtime=extension_runtime,
        )

        self.assertIs(project_session, context.project_session)
        self.assertIs(asset_catalog, context.asset_catalog)
        self.assertIs(extension_runtime, context.extension_runtime)
        self.assertIsInstance(context.event_bus, EventBus)


class TestMessageModels(unittest.TestCase):
    def test_tree_command_embeds_node_ref(self) -> None:
        node = NodeRef(kind="data_file", node_id="n1", project_id="p1")
        command = TreeCommand(TreeCommandType.ACTIVATE, node=node, action="open")

        self.assertEqual(TreeCommandType.ACTIVATE, command.command_type)
        self.assertEqual("data_file", command.node.kind)
        self.assertEqual("open", command.action)

    def test_app_command_can_wrap_tree_command(self) -> None:
        node = NodeRef(kind="series", node_id="s1")
        tree_command = TreeCommand(TreeCommandType.SELECT, node=node)
        command = AppCommand(AppCommandType.TREE, tree_command=tree_command)

        self.assertEqual(AppCommandType.TREE, command.command_type)
        self.assertIs(tree_command, command.tree_command)
