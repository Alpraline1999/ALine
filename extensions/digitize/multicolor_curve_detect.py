from __future__ import annotations

import cv2

from core.extension_api import DigitizeExtension, ExtensionConfigField
from extensions.digitize._shared import (
    apply_mask_polygons,
    dominant_color_centers,
    downsample_points,
    hsv_mask,
    read_image,
    trace_mask_columns,
)
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy


def _multicolor_curve_detect(figure: str, params):
    options = dict(params or {})
    image = read_image(str(figure or ""))
    centers = dominant_color_centers(
        image,
        cluster_count=max(1, int(options.get("cluster_count", 3) or 3)),
        saturation_min=max(0, int(options.get("saturation_min", 40) or 40)),
        value_min=max(0, int(options.get("value_min", 40) or 40)),
    )
    target_index = max(1, int(options.get("target_cluster", 1) or 1))
    if target_index > len(centers):
        raise ValueError(f"当前仅检测到 {len(centers)} 个有效颜色簇")
    h_value, s_value, v_value = centers[target_index - 1]
    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = hsv_mask(
        hsv_image,
        h_value,
        s_value,
        v_value,
        max(3, int(options.get("hue_tolerance", 12) or 12)),
        max(10, int(options.get("sv_tolerance", 40) or 40)),
        max(10, int(options.get("sv_tolerance", 40) or 40)),
    )
    mask = apply_mask_polygons(mask, options.get("mask_polygons"), bool(options.get("mask_include_mode", True)))
    points = trace_mask_columns(mask, step=max(1, int(options.get("step", 3) or 3)), y_mode="median")
    points = downsample_points(points, max_points=max(1, int(options.get("max_points", 5000) or 5000)))
    return line_from_xy([item[0] for item in points], [item[1] for item in points])


def register_extensions(registry) -> None:
    registry.register_digitize(
        DigitizeExtension(
            type="builtin_digitize_multicolor_curve",
            name="多色曲线识别",
            handler=_multicolor_curve_detect,
            description="自动聚类图中的主颜色簇，并按选定簇提取其中一条彩色曲线。",
            version=BUILTIN_EXTENSION_VERSION,
            source_kind="builtin",
            tool_tier="tool",
            settings=True,
            config_fields=[
                ExtensionConfigField(key="cluster_count", label="聚类颜色数", field_type="integer", default=3, min_value=1, max_value=8),
                ExtensionConfigField(key="target_cluster", label="输出颜色簇序号", field_type="integer", default=1, min_value=1, max_value=8),
                ExtensionConfigField(key="saturation_min", label="最小饱和度", field_type="integer", default=40, min_value=0, max_value=255),
                ExtensionConfigField(key="value_min", label="最小亮度", field_type="integer", default=40, min_value=0, max_value=255),
                ExtensionConfigField(key="hue_tolerance", label="色相容差", field_type="integer", default=12, min_value=1, max_value=60),
                ExtensionConfigField(key="sv_tolerance", label="饱和/亮度容差", field_type="integer", default=40, min_value=1, max_value=120),
                ExtensionConfigField(key="step", label="扫描步长", field_type="integer", default=3, min_value=1, max_value=20),
                ExtensionConfigField(key="max_points", label="最大点数", field_type="integer", default=5000, min_value=100, max_value=50000),
            ],
        )
    )
