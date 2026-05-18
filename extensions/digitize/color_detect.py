from __future__ import annotations

from typing import Any, Dict

from core.extension_api import DigitizeExtension, ExtensionConfigField
from digitize.auto_extractor import AutoExtractor
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy


COLOR_DIGITIZE_EXTENSION_TYPE = "builtin_digitize_color_detect"


def _resolve_tolerance(sampled_color: dict, tolerance: int) -> int:
    """Auto-tolerance: 0 means estimate from sampled color brightness."""
    if tolerance > 0:
        return tolerance
    # Estimate tolerance from color brightness
    brightness = (int(sampled_color.get("r", 0) or 0) * 0.299
                  + int(sampled_color.get("g", 0) or 0) * 0.587
                  + int(sampled_color.get("b", 0) or 0) * 0.114)
    return max(5, min(40, int(brightness / 8)))


def _color_digitize(figure: str, params: Dict[str, Any]):
    sampled_color = dict(params.get("sampled_color") or {})
    if not sampled_color:
        raise ValueError("请先使用取色按钮采样颜色")

    raw_tolerance = int(params.get("tolerance", 0) or 0)
    tolerance = _resolve_tolerance(sampled_color, raw_tolerance)
    points = AutoExtractor.extract(
        str(figure or ""),
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
    xs = [float(point[0]) for point in list(points or [])]
    ys = [float(point[1]) for point in list(points or [])]
    max_points = int(params.get("max_points", 5000) or 5000)
    if len(xs) > max_points:
        step = max(1, len(xs) // max_points)
        xs = xs[::step]
        ys = ys[::step]
    return line_from_xy(xs, ys)


def register_extensions(registry) -> None:
    registry.register_digitize(
        DigitizeExtension(
            type=COLOR_DIGITIZE_EXTENSION_TYPE,
            name="颜色识别",
            handler=_color_digitize,
            description="按采样颜色和容差自动提取图像中的散点位置。",
            version=BUILTIN_EXTENSION_VERSION,
            source_kind="builtin",
            tool_tier="tool",
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
                    description="颜色容差（0=自动，越大越宽松）。",
                    field_type="integer",
                    default=0,
                    min_value=0,
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
                ExtensionConfigField(
                    key="max_points",
                    label="最大点数",
                    description="输出点数的上限（超限时均匀下采样）。",
                    field_type="integer",
                    default=5000,
                    min_value=100,
                    max_value=50000,
                ),
            ],
        )
    )
