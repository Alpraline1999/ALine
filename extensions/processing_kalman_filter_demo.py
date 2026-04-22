from core.extension_api import ExtensionConfigField, ProcessingExtension


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def kalman_filter_series(xs, ys, params, lines=None):
    if not ys:
        return list(xs), []

    process_variance = max(0.0, _as_float(params.get("process_variance", 1e-4), 1e-4))
    measurement_variance = max(1e-12, _as_float(params.get("measurement_variance", 1e-2), 1e-2))
    estimate = _as_float(params.get("initial_estimate", ys[0]), ys[0])
    error_covariance = max(1e-12, _as_float(params.get("initial_error_covariance", 1.0), 1.0))

    filtered = []
    for raw_value in ys:
        measurement = float(raw_value)
        error_covariance += process_variance
        kalman_gain = error_covariance / (error_covariance + measurement_variance)
        estimate = estimate + kalman_gain * (measurement - estimate)
        error_covariance = (1.0 - kalman_gain) * error_covariance
        filtered.append(estimate)

    return list(xs), filtered


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="kalman_filter",
            name="卡尔曼滤波",
            handler=kalman_filter_series,
            line_mode="single",
            description="对一维序列执行标量卡尔曼滤波，适合平滑含噪测量数据。",
            default_options={
                "process_variance": 1e-4,
                "measurement_variance": 1e-2,
                "initial_estimate": 0.0,
                "initial_error_covariance": 1.0,
            },
            config_fields=[
                ExtensionConfigField(key="process_variance", description="过程噪声方差，越大表示对状态变化越敏感。", field_type="number", default=1e-4),
                ExtensionConfigField(key="measurement_variance", description="测量噪声方差，越大表示更信任历史估计。", field_type="number", default=1e-2),
                ExtensionConfigField(key="initial_estimate", description="初始状态估计值。", field_type="number", default=0.0),
                ExtensionConfigField(key="initial_error_covariance", description="初始误差协方差。", field_type="number", default=1.0),
            ],
        )
    )