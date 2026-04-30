from __future__ import annotations

"""正式对外的处理扩展工具。

仅 __all__ 中列出的名称视为稳定的扩展工具接口。
扩展实现优先使用 line_from_xy、line_xy、primary_line、align_lines_to_common_x
这组基础工具；单扩展专用算法逻辑应保留在各自扩展文件内。
"""

from core.line_tools import (
    Line,
    Point,
    XY,
    align_lines_to_common_x,
    line_from_xy,
    line_xy,
    normalize_line,
    normalize_lines,
    primary_line,
    resolve_sample_rate,
    series_payload_to_line,
    series_payloads_to_lines,
)


BUILTIN_EXTENSION_VERSION = "0.1.0"

__all__ = [
    "BUILTIN_EXTENSION_VERSION",
    "Point",
    "Line",
    "XY",
    "normalize_line",
    "normalize_lines",
    "line_from_xy",
    "line_xy",
    "primary_line",
    "series_payload_to_line",
    "series_payloads_to_lines",
    "align_lines_to_common_x",
    "resolve_sample_rate",
]
