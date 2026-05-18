from __future__ import annotations

from core.extension_api import DigitizeExtension, ExtensionConfigField
from extensions.digitize._shared import (
    apply_mask_polygons,
    color_mask_from_sampled,
    component_centroids,
    grayscale_curve_mask,
    read_image,
)
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy


def _centroids(figure: str, params):
    options = dict(params or {})
    image = read_image(str(figure or ""))
    sampled_color = options.get("sampled_color")
    tolerance = max(1, int(options.get("tolerance", 18) or 18))
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
    points = component_centroids(
        mask,
        min_area=max(1, int(options.get("min_area", 6) or 6)),
        max_area=max(0, int(options.get("max_area", 1000) or 1000)),
    )
    axis = "y" if str(options.get("sort_axis", "x") or "x").strip().lower() == "y" else "x"
    reverse = bool(options.get("reverse_order", False))
    key_index = 1 if axis == "y" else 0
    points.sort(key=lambda item: item[key_index], reverse=reverse)
    return line_from_xy([item[0] for item in points], [item[1] for item in points])


def register_extensions(registry) -> None:
    registry.register_digitize(
        DigitizeExtension(
            type="builtin_digitize_marker_centroid",
            name="散点质心识别",
            handler=_centroids,
            description="提取散点或标记的连通域质心，适合散点图数字化。",
            version=BUILTIN_EXTENSION_VERSION,
            source_kind="builtin",
            tool_tier="tool",
            settings=True,
            config_fields=[
                ExtensionConfigField(key="sampled_color", label="采样颜色", description="可选；提供后优先走颜色连通域。", field_type="pickcolor", default=None),
                ExtensionConfigField(key="tolerance", label="颜色容差", field_type="integer", default=18, min_value=1, max_value=80),
                ExtensionConfigField(key="threshold_mode", label="阈值模式", field_type="selective", default="otsu", choices=("otsu", "manual")),
                ExtensionConfigField(key="threshold", label="手动阈值", field_type="integer", default=160, min_value=0, max_value=255),
                ExtensionConfigField(key="invert", label="反相提取", field_type="boolean", default=True),
                ExtensionConfigField(key="blur_size", label="平滑核", field_type="integer", default=3, min_value=0, max_value=15),
                ExtensionConfigField(key="morph_close", label="闭运算核", field_type="integer", default=3, min_value=0, max_value=15),
                ExtensionConfigField(key="min_area", label="最小面积", field_type="integer", default=6, min_value=1, max_value=5000),
                ExtensionConfigField(key="max_area", label="最大面积", field_type="integer", default=1000, min_value=0, max_value=50000),
                ExtensionConfigField(key="sort_axis", label="排序轴", field_type="selective", default="x", choices=("x", "y")),
                ExtensionConfigField(key="reverse_order", label="逆序输出", field_type="boolean", default=False),
            ],
        )
    )
