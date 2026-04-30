from __future__ import annotations

from dataclasses import dataclass, field

from .event_bus import EventBus


def _default_project_session() -> object:
    from core.project_manager import project_manager

    return project_manager.project_session


def _default_asset_catalog() -> object:
    from core.global_assets import global_assets

    return global_assets


def _default_extension_runtime() -> object:
    from core.extension_api import extension_registry

    return extension_registry


@dataclass(slots=True)
class AppContext:
    project_session: object = field(default_factory=_default_project_session)
    asset_catalog: object = field(default_factory=_default_asset_catalog)
    extension_runtime: object = field(default_factory=_default_extension_runtime)
    event_bus: EventBus = field(default_factory=EventBus)
