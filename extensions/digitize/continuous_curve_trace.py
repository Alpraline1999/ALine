from __future__ import annotations

from core.extension_api import DigitizeExtension, ExtensionConfigField
from extensions.digitize._shared import (
    apply_mask_polygons,
    color_mask_from_sampled,
    downsample_points,
    grayscale_curve_mask,
    read_image,
    smooth_point_series,
    trace_mask_columns,
)
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy


def _continuous_trace(figure: str, params):
    options = dict(params or {})
    image = read_image(str(figure or ""))
    sampled_color = options.get("sampled_color")
    tolerance = max(1, int(options.get("tolerance", 24) or 24))
    if isinstance(sampled_color, dict) and sampled_color:
        mask = color_mask_from_sampled(image, sampled_color, tolerance=tolerance)
    else:
        mask = grayscale_curve_mask(
            image,
            threshold_mode=str(options.get("threshold_mode", "otsu") or "otsu"),
            threshold=int(options.get("threshold", 160) or 160),
            invert=bool(options.get("invert", True)),
            blur_size=int(options.get("blur_size", 3) or 3),
            morph_close=int(options.get("morph_close", 3) or 3),
        )
    mask = apply_mask_polygons(mask, options.get("mask_polygons"), bool(options.get("mask_include_mode", True)))
    points = trace_mask_columns(mask, step=max(1, int(options.get("step", 2) or 2)), y_mode=str(options.get("y_mode", "median") or "median"))
    points = smooth_point_series(points, window=max(1, int(options.get("smooth_window", 1) or 1)))
    points = downsample_points(points, max_points=max(1, int(options.get("max_points", 5000) or 5000)))
    return line_from_xy([item[0] for item in points], [item[1] for item in points])


def register_extensions(registry) -> None:
    registry.register_digitize(
        DigitizeExtension(
            type="builtin_digitize_continuous_trace",
            name="连续曲线追踪",
            handler=_continuous_trace,
            description="对连续曲线做颜色或灰度追踪，输出按列排序的像素点。",
            version=BUILTIN_EXTENSION_VERSION,
            source_kind="builtin",
            tool_tier="tool",
            settings=True,
            config_fields=[
                ExtensionConfigField(key="sampled_color", label="采样颜色", description="可选；提供后优先走颜色追踪。", field_type="pickcolor", default=None),
                ExtensionConfigField(key="tolerance", label="颜色容差", field_type="integer", default=24, min_value=1, max_value=80),
                ExtensionConfigField(key="threshold_mode", label="阈值模式", field_type="selective", default="otsu", choices=("otsu", "manual")),
                ExtensionConfigField(key="threshold", label="手动阈值", field_type="integer", default=160, min_value=0, max_value=255),
                ExtensionConfigField(key="invert", label="反相提取", field_type="boolean", default=True),
                ExtensionConfigField(key="blur_size", label="平滑核", field_type="integer", default=3, min_value=0, max_value=15),
                ExtensionConfigField(key="morph_close", label="闭运算核", field_type="integer", default=3, min_value=0, max_value=15),
                ExtensionConfigField(key="step", label="扫描步长", field_type="integer", default=2, min_value=1, max_value=20),
                ExtensionConfigField(key="y_mode", label="列内 Y 统计", field_type="selective", default="median", choices=("median", "mean")),
                ExtensionConfigField(key="smooth_window", label="平滑窗口", field_type="integer", default=1, min_value=1, max_value=31),
                ExtensionConfigField(key="max_points", label="最大点数", field_type="integer", default=5000, min_value=100, max_value=50000),
            ],
        )
    )
