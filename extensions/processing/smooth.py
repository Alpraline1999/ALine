from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.base_tools import VERSION
from processing.smoother import smooth_moving_average, smooth_savgol


def _smooth_handler(xs, ys, params, lines=None):
    del lines
    options = dict(params or {})
    method = options.get("method", "savgol")
    if method == "savgol":
        return smooth_savgol(list(xs), list(ys), int(options.get("window", 11)), int(options.get("poly", 3)))
    if method == "moving_avg":
        return smooth_moving_average(list(xs), list(ys), int(options.get("window", 5)))
    return list(xs), list(ys)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="smooth",
            name="平滑",
            handler=_smooth_handler,
            description="对 Y 序列做平滑处理，适合去除高频噪声。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
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
