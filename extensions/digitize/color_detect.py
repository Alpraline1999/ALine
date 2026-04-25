from __future__ import annotations

from typing import Any, Dict

from core.extension_api import DigitizeExtension, ExtensionConfigField


COLOR_DIGITIZE_EXTENSION_TYPE = "builtin_digitize_color_detect"
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


def register_extensions(registry) -> None:
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
