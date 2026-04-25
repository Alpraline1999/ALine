from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line
from processing.smoother import smooth_moving_average, smooth_savgol


def _smooth_handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    options = dict(params or {})
    method = options.get("method", "savgol")
    if method == "savgol":
        nx, ny = smooth_savgol(list(xs), list(ys), int(options.get("window", 11)), int(options.get("poly", 3)))
        return line_from_xy(nx, ny)
    if method == "moving_avg":
        nx, ny = smooth_moving_average(list(xs), list(ys), int(options.get("window", 5)))
        return line_from_xy(nx, ny)
    return line_from_xy(list(xs), list(ys))


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="smooth",
            name="平滑",
            handler=_smooth_handler,
            description="对 Y 序列做平滑处理，适合去除高频噪声。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="method",
                    label="平滑方法",
                    field_type="selective",
                    default="savgol",
                    choices=["savgol", "moving_avg"],
                ),
                ExtensionConfigField(key="window", label="窗口大小", field_type="integer", default=9, min_value=1),
                ExtensionConfigField(key="poly", label="多项式阶数", field_type="integer", default=3, min_value=1),
            ],
        )
    )
