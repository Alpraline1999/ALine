from __future__ import annotations

import numpy as np

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, baseline_correction, line_from_xy, line_xy, primary_line


def _handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    if len(xs) < 2 or len(ys) < 2:
        return line_from_xy(list(xs), list(ys))
    options = dict(params or {})
    method = str(options.get("method", "linear") or "linear").strip().lower()
    x_array = np.asarray(list(xs), dtype=float)
    y_array = np.asarray(list(ys), dtype=float)
    if method == "percentile":
        percentile = max(0.0, min(100.0, float(options.get("percentile", 5.0) or 5.0)))
        baseline = float(np.percentile(y_array, percentile))
        corrected = y_array - baseline
    else:
        corrected = baseline_correction(x_array, y_array, method)
    return line_from_xy(list(xs), corrected.tolist())


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="baseline_correction",
            name="基线校正",
            handler=_handler,
            description="对曲线做常量、线性或百分位基线校正。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="method", label="校正方式", field_type="selective", default="linear", choices=("constant", "linear", "percentile")),
                ExtensionConfigField(key="percentile", label="百分位基线", field_type="number", default=5.0, min_value=0.0, max_value=100.0, step=0.5),
            ],
        )
    )
