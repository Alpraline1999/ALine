from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from core.extension_api import DigitizeExtension, ExtensionConfigField
from extensions.processing.extension_tools import line_from_xy


COLOR_DIGITIZE_EXTENSION_TYPE = "builtin_digitize_color_detect"
_BUILTIN_EXTENSION_VERSION = "0.1.0"


def _cv2_imread_unicode(image_path: str):
    data = np.fromfile(image_path, dtype=np.uint8)
    if data.size == 0:
        return cv2.imread(image_path)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        return cv2.imread(image_path)
    return image


class AutoExtractor:
    @staticmethod
    def extract(
        image_path: str,
        target_r: int,
        target_g: int,
        target_b: int,
        h_tol: int = 15,
        s_tol: int = 50,
        v_tol: int = 50,
        mask_polygons: Optional[List[List[Tuple[float, float]]]] = None,
        mask_include_mode: bool = True,
        step: int = 2,
    ) -> List[Tuple[float, float]]:
        img_bgr = _cv2_imread_unicode(image_path)
        if img_bgr is None:
            return []

        h_img, w_img = img_bgr.shape[:2]
        target_bgr = np.array([[[target_b, target_g, target_r]]], dtype=np.uint8)
        target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0, 0]
        th, ts, tv = int(target_hsv[0]), int(target_hsv[1]), int(target_hsv[2])

        img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        lower1 = np.array([max(0, th - h_tol), max(0, ts - s_tol), max(0, tv - v_tol)])
        upper1 = np.array([min(180, th + h_tol), min(255, ts + s_tol), min(255, tv + v_tol)])
        color_mask = cv2.inRange(img_hsv, lower1, upper1)

        if th - h_tol < 0:
            lower2 = np.array([180 + th - h_tol, max(0, ts - s_tol), max(0, tv - v_tol)])
            upper2 = np.array([180, min(255, ts + s_tol), min(255, tv + v_tol)])
            color_mask = cv2.bitwise_or(color_mask, cv2.inRange(img_hsv, lower2, upper2))
        elif th + h_tol > 180:
            lower2 = np.array([0, max(0, ts - s_tol), max(0, tv - v_tol)])
            upper2 = np.array([th + h_tol - 180, min(255, ts + s_tol), min(255, tv + v_tol)])
            color_mask = cv2.bitwise_or(color_mask, cv2.inRange(img_hsv, lower2, upper2))

        if mask_polygons:
            region_mask = np.zeros((h_img, w_img), dtype=np.uint8)
            for polygon in mask_polygons:
                if len(polygon) >= 3:
                    pts = np.array([(int(point[0]), int(point[1])) for point in polygon], dtype=np.int32)
                    cv2.fillPoly(region_mask, [pts], 255)
            if not mask_include_mode:
                region_mask = cv2.bitwise_not(region_mask)
            color_mask = cv2.bitwise_and(color_mask, region_mask)

        points: List[Tuple[float, float]] = []
        for x_value in range(0, w_img, max(1, int(step))):
            column = color_mask[:, x_value]
            y_indices = np.where(column > 0)[0]
            if len(y_indices) > 0:
                points.append((float(x_value), float(np.mean(y_indices))))
        return points


def _color_digitize(figure: str, params: Dict[str, Any]):
    sampled_color = dict(params.get("sampled_color") or {})
    if not sampled_color:
        raise ValueError("请先使用取色按钮采样颜色")

    tolerance = int(params.get("tolerance", 20) or 20)
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
    return line_from_xy(xs, ys)


def register_extensions(registry) -> None:
    registry.register_digitize(
        DigitizeExtension(
            type=COLOR_DIGITIZE_EXTENSION_TYPE,
            name="颜色识别",
            handler=_color_digitize,
            description="按采样颜色和容差自动提取图像中的散点位置。",
            version=_BUILTIN_EXTENSION_VERSION,
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
