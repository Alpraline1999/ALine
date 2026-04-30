from __future__ import annotations

from typing import Any

from core.builtin_extensions import register_core_builtin_extensions
from core.extension_api import extension_registry


def ensure_builtin_extensions_loaded(registry: Any = extension_registry) -> None:
    register_core_builtin_extensions(registry)
