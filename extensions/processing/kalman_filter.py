from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from core.value_parsing import coerce_float
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def kalman_filter_handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    options = dict(params or {})
    if not ys:
        return line_from_xy(list(xs), [])

    # resolve smoothing parameters from preset or direct values
    preset = str(options.get("smoothing_preset", "moderate") or "moderate").strip().lower()
    presets = {
        "mild": (1e-3, 1e-3),
        "moderate": (1e-4, 1e-2),
        "strong": (1e-5, 1e-1),
    }
    default_pv, default_mv = presets.get(preset, presets["moderate"])
    process_variance = max(0.0, coerce_float(options.get("process_variance", default_pv), default_pv) or 0.0)
    measurement_variance = max(1e-12, coerce_float(options.get("measurement_variance", default_mv), default_mv) or 0.0)
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
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(key="smoothing_preset", label="平滑强度", description="预设平滑参数组。轻度：跟随测量；中度：平衡；强力：强平滑。", field_type="selective", default="moderate", choices=("mild", "moderate", "strong")),
                ExtensionConfigField(key="initial_estimate", label="初始估计值", description="初始状态估计值。", field_type="number", default=0.0),
                ExtensionConfigField(key="initial_error_covariance", label="初始误差协方差", description="初始误差协方差。", field_type="number", default=1.0),
            ],
        )
    )
