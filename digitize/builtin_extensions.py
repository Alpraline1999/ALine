from __future__ import annotations

from typing import Any, Dict

from core.extension_api import DigitizeExtension, ExtensionConfigField


COLOR_DIGITIZE_EXTENSION_TYPE = "builtin_digitize_color_detect"
SHAPE_DIGITIZE_EXTENSION_TYPE = "builtin_digitize_shape_detect"
_BUILTIN_EXTENSION_VERSION = "0.1.0"


def _color_digitize(image_path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from digitize.auto_extractor import AutoExtractor

    sampled_color = dict(params.get("sampled_color") or {})
    if not sampled_color:
        raise ValueError("请先使用取色按钮采样颜色")

    tolerance = int(params.get("tolerance", 20) or 20)
    points = AutoExtractor.extract(
        image_path,
        target_r=int(sampled_color.get("r", 0) or 0),
        target_g=int(sampled_color.get("g", 0) or 0),
        target_b=int(sampled_color.get("b", 0) or 0),
        h_tol=max(5, tolerance // 2),
        s_tol=min(255, tolerance * 4),
        v_tol=min(255, tolerance * 4),
        mask_polygons=params.get("mask_polygons"),
        mask_include_mode=bool(params.get("mask_include_mode", True)),
        step=int(params.get("step", 5) or 5),
    )
    return {
        "points": list(points or []),
        "summary": f"颜色识别到 {len(points or [])} 个点",
    }


def _shape_digitize(image_path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from digitize.shape_extractor import ShapeExtractor

    template_info = params.get("template_info")
    if template_info is None:
        raise ValueError("请先使用截图按钮截取图例形状")

    points = ShapeExtractor.extract(
        image_path,
        template_info=template_info,
        mask_polygons=params.get("mask_polygons"),
        mask_include_mode=bool(params.get("mask_include_mode", True)),
        step=int(params.get("step", 5) or 5),
        threshold=float(params.get("threshold", 0.65) or 0.65),
        color_weight=float(params.get("color_weight", 0.7) or 0.7),
    )
    return {
        "points": list(points or []),
        "summary": f"图形识别到 {len(points or [])} 个点",
    }


def ensure_builtin_digitize_extensions(registry) -> None:
    if registry.get_digitize(COLOR_DIGITIZE_EXTENSION_TYPE) is None:
        registry.register_digitize(
            DigitizeExtension(
                type=COLOR_DIGITIZE_EXTENSION_TYPE,
                name="颜色识别",
                handler=_color_digitize,
                description="按采样颜色和容差自动提取图像中的散点位置。",
                version=_BUILTIN_EXTENSION_VERSION,
                source_kind="builtin",
                settings=True,
                config_fields=[
                    ExtensionConfigField(
                        key="sampled_color",
                        label="采样颜色",
                        description="点击按钮后在图片上选点取色。",
                        field_type="pickcolor",
                        default=None,
                    ),
                    ExtensionConfigField(
                        key="tolerance",
                        label="颜色容差",
                        description="颜色识别使用的容差强度。",
                        field_type="integer",
                        default=20,
                        min_value=1,
                        max_value=80,
                    ),
                    ExtensionConfigField(
                        key="step",
                        label="搜索步长",
                        description="图像扫描步长。",
                        field_type="integer",
                        default=5,
                        min_value=1,
                        max_value=20,
                    ),
                ],
            )
        )

    if registry.get_digitize(SHAPE_DIGITIZE_EXTENSION_TYPE) is None:
        registry.register_digitize(
            DigitizeExtension(
                type=SHAPE_DIGITIZE_EXTENSION_TYPE,
                name="图形识别 (测试功能)",
                handler=_shape_digitize,
                description="按截图模板和匹配阈值搜索图中相同形状。",
                version=_BUILTIN_EXTENSION_VERSION,
                source_kind="builtin",
                settings=True,
                config_fields=[
                    ExtensionConfigField(
                        key="template_info",
                        label="截图模板",
                        description="点击按钮后在图片上框选模板区域。",
                        field_type="shot",
                        default=None,
                    ),
                    ExtensionConfigField(
                        key="threshold",
                        label="匹配精度",
                        description="形状匹配阈值。",
                        field_type="limited",
                        default=0.65,
                        min_value=0.3,
                        max_value=0.95,
                        step=0.01,
                    ),
                    ExtensionConfigField(
                        key="color_weight",
                        label="颜色权重",
                        description="颜色分数在总匹配评分中的占比。",
                        field_type="limited",
                        default=0.7,
                        min_value=0.0,
                        max_value=1.0,
                        step=0.01,
                    ),
                    ExtensionConfigField(
                        key="step",
                        label="搜索步长",
                        description="图像扫描步长。",
                        field_type="integer",
                        default=5,
                        min_value=1,
                        max_value=20,
                    ),
                ],
            )
        )