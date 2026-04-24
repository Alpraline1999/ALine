from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.extension_api import extension_lines_number, extension_registry


@dataclass(frozen=True)
class PipelineExtensionDefinition:
    name: str
    ops: List[Dict[str, Any]]
    lines_number: Tuple[int, int]
    multiline_index: Optional[int] = None
    multiline_type: str = ""


def build_pipeline_extension_definition(
    ops: List[Dict[str, Any]],
    *,
    name: str = "当前 Pipeline",
) -> PipelineExtensionDefinition:
    multiline_index: Optional[int] = None
    multiline_type = ""
    lines_number: Tuple[int, int] = (1, 1)

    for index, op in enumerate(ops or []):
        op_type = str(op.get("type", "") or "")
        extension = extension_registry.get_processing(op_type)
        if extension is None:
            continue
        current_lines_number = extension_lines_number(extension)
        if current_lines_number is None:
            continue
        _lower, upper = current_lines_number
        if upper != -1 and upper <= 1:
            continue
        if multiline_index is not None:
            raise ValueError("pipeline 中不应有超过一个双曲线处理工具或多曲线处理扩展")
        multiline_index = index
        multiline_type = op_type
        lines_number = current_lines_number

    return PipelineExtensionDefinition(
        name=name,
        ops=[dict(op) for op in (ops or [])],
        lines_number=lines_number,
        multiline_index=multiline_index,
        multiline_type=multiline_type,
    )
