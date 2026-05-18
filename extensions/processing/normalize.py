from __future__ import annotations

import numpy as np

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _normalize_handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    options = dict(params or {})
    mode = options.get("mode", "minmax")
    if not ys:
        return line_from_xy(list(xs), list(ys))
    ay = np.asarray(ys, dtype=float)
    if mode == "minmax":
        mn, mx = ay.min(), ay.max()
        normalized = ((ay - mn) / (mx - mn or 1.0)).tolist()
    elif mode == "zscore":
        std = ay.std() or 1.0
        normalized = ((ay - ay.mean()) / std).tolist()
    elif mode == "robust":
        p25, p75 = np.percentile(ay, [25, 75])
        iqr = p75 - p25 or 1.0
        normalized = ((ay - np.median(ay)) / iqr).tolist()
    elif mode == "unitlength":
        norm_val = np.linalg.norm(ay) or 1.0
        normalized = (ay / norm_val).tolist()
    elif mode == "mean":
        mean_val = ay.mean() or 1.0
        normalized = (ay / mean_val).tolist()
    else:
        normalized = ay.tolist()
    return line_from_xy(list(xs), normalized)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="normalize",
            name="归一化",
            handler=_normalize_handler,
            description="支持 min-max / z-score / robust / 单位长度 / 相对均值归一化。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="mode",
                    label="归一化方式",
                    field_type="selective",
                    default="minmax",
                    choices=["minmax", "zscore", "robust", "unitlength", "mean"],
                )
            ],
        )
    )
