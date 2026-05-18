from __future__ import annotations

from statistics import median

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _replace_linear(xs, ys, index):
    if index <= 0 or index >= len(ys) - 1:
        return ys[index]
    left_x, left_y = float(xs[index - 1]), float(ys[index - 1])
    right_x, right_y = float(xs[index + 1]), float(ys[index + 1])
    current_x = float(xs[index])
    span = right_x - left_x
    if span == 0:
        return (left_y + right_y) / 2.0
    ratio = (current_x - left_x) / span
    return left_y + ratio * (right_y - left_y)


def _handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    if len(ys) < 3:
        return line_from_xy(list(xs), list(ys))
    options = dict(params or {})
    window = max(3, int(options.get("window", 7) or 7))
    if window % 2 == 0:
        window += 1
    radius = window // 2
    threshold = max(0.1, float(options.get("threshold", 3.5) or 3.5))
    replace_mode = str(options.get("replace_mode", "median") or "median").strip().lower()
    output = list(float(value) for value in ys)
    for index, current in enumerate(list(output)):
        lo = max(0, index - radius)
        hi = min(len(output), index + radius + 1)
        segment = output[lo:hi]
        if len(segment) < 3:
            continue
        local_median = float(median(segment))
        abs_devs = [abs(item - local_median) for item in segment]
        local_mad = float(median(abs_devs)) or 1e-12
        robust_z = abs(current - local_median) / (1.4826 * local_mad)
        if robust_z < threshold:
            continue
        output[index] = _replace_linear(xs, output, index) if replace_mode == "linear" else local_median
    return line_from_xy(list(xs), output)


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="despike",
            name="尖峰剔除",
            handler=_handler,
            description="使用局部中位数与 MAD 检测孤立尖峰，并以中位数或线性插值替换。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="window", label="局部窗口", field_type="integer", default=7, min_value=3),
                ExtensionConfigField(key="threshold", label="尖峰阈值", field_type="number", default=3.5, min_value=0.1, step=0.1),
                ExtensionConfigField(key="replace_mode", label="替换方式", field_type="selective", default="median", choices=("median", "linear")),
            ],
        )
    )
