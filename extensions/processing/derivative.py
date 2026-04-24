from __future__ import annotations

from core.extension_api import ProcessingExtension
from extensions.processing.builtin_ops import VERSION, build_single_line_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="derivative",
            name="导数",
            handler=build_single_line_handler("derivative"),
            description="计算一阶导数，观察变化速率。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
        )
    )
