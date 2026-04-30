from __future__ import annotations

"""共享数值参数解析工具。"""

from typing import Any, Callable, Optional


def coerce_float(
    value: Any,
    default: Any,
    *,
    named_resolver: Optional[Callable[[Any], Optional[float]]] = None,
) -> Optional[float]:
    if named_resolver is not None:
        named_value = named_resolver(value)
        if named_value is not None:
            return float(named_value)
    try:
        return float(value)
    except (TypeError, ValueError):
        if named_resolver is not None:
            named_default = named_resolver(default)
            if named_default is not None:
                return float(named_default)
        if default is None:
            return None
        return float(default)
