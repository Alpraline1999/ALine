from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from core.value_parsing import coerce_float
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def kalman_filter_handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    options = dict(params or {})
    if not ys:
        return line_from_xy(list(xs), [])

    process_variance = max(0.0, coerce_float(options.get("process_variance", 1e-4), 1e-4) or 0.0)
    measurement_variance = max(1e-12, coerce_float(options.get("measurement_variance", 1e-2), 1e-2) or 0.0)
    estimate = coerce_float(options.get("initial_estimate", ys[0]), ys[0]) or float(ys[0])
    error_covariance = max(1e-12, coerce_float(options.get("initial_error_covariance", 1.0), 1.0) or 0.0)

    filtered = []
    for raw_value in ys:
        measurement = float(raw_value)
        error_covariance += process_variance
        kalman_gain = error_covariance / (error_covariance + measurement_variance)
        estimate = estimate + kalman_gain * (measurement - estimate)
        error_covariance = (1.0 - kalman_gain) * error_covariance
        filtered.append(estimate)

    return line_from_xy(list(xs), filtered)


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="kalman_filter",
            name="卡尔曼滤波",
            handler=kalman_filter_handler,
            description="对一维序列执行标量卡尔曼滤波，适合平滑含噪测量数据。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            config_fields=[
                ExtensionConfigField(key="process_variance", label="过程噪声方差", description="过程噪声方差，越大表示对状态变化越敏感。", field_type="number", default=1e-4),
                ExtensionConfigField(key="measurement_variance", label="测量噪声方差", description="测量噪声方差，越大表示更信任历史估计。", field_type="number", default=1e-2),
                ExtensionConfigField(key="initial_estimate", label="初始估计值", description="初始状态估计值。", field_type="number", default=0.0),
                ExtensionConfigField(key="initial_error_covariance", label="初始误差协方差", description="初始误差协方差。", field_type="number", default=1.0),
            ],
        )
    )
