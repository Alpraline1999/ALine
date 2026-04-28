from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from core.extension_api import DigitizeExtension, ExtensionConfigField
from extensions.processing.extension_tools import line_from_xy


SHAPE_DIGITIZE_EXTENSION_TYPE = "builtin_digitize_shape_detect"
_BUILTIN_EXTENSION_VERSION = "0.1.0"


def _cv2_imread_unicode(image_path: str):
    data = np.fromfile(image_path, dtype=np.uint8)
    if data.size == 0:
        return cv2.imread(image_path)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        return cv2.imread(image_path)
    return image


class ShapeExtractor:
    @staticmethod
    def preprocess_region(
        image_path: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> dict:
        img = _cv2_imread_unicode(image_path)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")

        img_h, img_w = img.shape[:2]
        x1i = max(0, int(round(x1)))
        y1i = max(0, int(round(y1)))
        x2i = min(img_w, int(round(x2)))
        y2i = min(img_h, int(round(y2)))
        if x2i - x1i < 4 or y2i - y1i < 4:
            raise ValueError("截图区域过小（至少需要 4×4 像素）")

        raw = img[y1i:y2i, x1i:x2i].copy()
        gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 30, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dilated = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        binary = np.zeros_like(gray, dtype=np.uint8)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            cv2.drawContours(binary, [largest], -1, 255, cv2.FILLED)
        else:
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                largest = max(contours, key=cv2.contourArea)
            else:
                raise ValueError("无法从截图区域提取有效轮廓")

        contour_area = cv2.contourArea(largest)
        if contour_area < 4:
            raise ValueError("截图区域中的形状面积过小")

        hull = cv2.convexHull(largest)
        hull_area = cv2.contourArea(hull)
        solidity = contour_area / hull_area if hull_area > 0 else 0.0
        _, _, bw, bh = cv2.boundingRect(largest)
        aspect_ratio = bw / bh if bh > 0 else 1.0

        hsv_raw = cv2.cvtColor(raw, cv2.COLOR_BGR2HSV)
        fg_mask = binary > 0
        dominant_hsv, color_tol_hsv, has_color = ShapeExtractor._extract_dominant_color(hsv_raw, fg_mask)
        return {
            "raw": raw,
            "binary": binary,
            "contour": largest,
            "contour_area": float(contour_area),
            "solidity": float(solidity),
            "aspect_ratio": float(aspect_ratio),
            "dominant_hsv": dominant_hsv,
            "color_tol_hsv": color_tol_hsv,
            "has_color": has_color,
            "size": (x2i - x1i, y2i - y1i),
        }

    @staticmethod
    def extract(
        image_path: str,
        template_info: dict,
        mask_polygons: Optional[list] = None,
        mask_include_mode: bool = True,
        step: int = 1,
        threshold: float = 0.55,
        color_weight: float = 0.7,
    ) -> List[Tuple[float, float]]:
        del step
        img = _cv2_imread_unicode(image_path)
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")

        img_h, img_w = img.shape[:2]
        template_contour = template_info["contour"]
        template_area = template_info["contour_area"]
        template_solidity = template_info.get("solidity", 0.8)
        template_ar = template_info.get("aspect_ratio", 1.0)

        fg_mask = ShapeExtractor._build_foreground_mask(img, template_info, color_weight)
        if mask_polygons:
            search_mask = np.zeros((img_h, img_w), dtype=np.uint8)
            pts_list = [
                np.array([(int(x_value), int(y_value)) for x_value, y_value in polygon], dtype=np.int32)
                for polygon in mask_polygons
            ]
            cv2.fillPoly(search_mask, pts_list, 255)
            if mask_include_mode:
                fg_mask = cv2.bitwise_and(fg_mask, search_mask)
            else:
                fg_mask = cv2.bitwise_and(fg_mask, cv2.bitwise_not(search_mask))

        area_lo = template_area * 0.1
        area_hi = template_area * 8.0
        dist_thr = 0.05 + threshold * 1.45
        raw_candidates: list[Tuple[float, float, float]] = []

        tw, th = template_info["size"]
        min_dim = min(tw, th)
        max_ksize = max(3, min(min_dim // 3, 7))
        open_ksizes = [0] + list(range(2, max_ksize + 1))
        seen_centers: set = set()
        dedup_radius = max(3, min(tw, th) // 2)

        for ksize in open_ksizes:
            if ksize == 0:
                working_mask = fg_mask.copy()
            else:
                k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
                working_mask = cv2.morphologyEx(fg_mask, cv2.MORPH_OPEN, k_open, iterations=1)

            k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            working_mask = cv2.morphologyEx(working_mask, cv2.MORPH_CLOSE, k_close, iterations=1)
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(working_mask, connectivity=8)
            for index in range(1, num_labels):
                area = stats[index, cv2.CC_STAT_AREA]
                if area < area_lo or area > area_hi:
                    continue

                cx, cy = centroids[index]
                grid_key = (int(cx) // dedup_radius, int(cy) // dedup_radius)
                if grid_key in seen_centers:
                    continue

                blob_mask = (labels == index).astype(np.uint8) * 255
                blob_contours, _ = cv2.findContours(blob_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not blob_contours:
                    continue

                blob_contour = max(blob_contours, key=cv2.contourArea)
                blob_area = cv2.contourArea(blob_contour)
                if blob_area < 4:
                    continue

                score = ShapeExtractor._evaluate_candidate(
                    template_contour,
                    template_solidity,
                    template_ar,
                    blob_contour,
                    blob_area,
                    dist_thr,
                )
                if score >= 0:
                    seen_centers.add(grid_key)
                    raw_candidates.append((float(cx), float(cy), score))

        return ShapeExtractor._nms_points(raw_candidates, dedup_radius)

    @staticmethod
    def _evaluate_candidate(template_contour, template_solidity, template_ar, blob_contour, blob_area, dist_thr):
        d1 = cv2.matchShapes(template_contour, blob_contour, cv2.CONTOURS_MATCH_I1, 0.0)
        d2 = cv2.matchShapes(template_contour, blob_contour, cv2.CONTOURS_MATCH_I2, 0.0)
        d3 = cv2.matchShapes(template_contour, blob_contour, cv2.CONTOURS_MATCH_I3, 0.0)
        hu_dist = min(d1, d2, d3)
        if hu_dist > dist_thr:
            return -1.0

        hull = cv2.convexHull(blob_contour)
        hull_area = cv2.contourArea(hull)
        blob_solidity = blob_area / hull_area if hull_area > 0 else 0.0
        if abs(blob_solidity - template_solidity) > 0.35:
            return -1.0

        _, _, bw, bh = cv2.boundingRect(blob_contour)
        blob_ar = bw / bh if bh > 0 else 1.0
        ar_ratio = max(blob_ar, template_ar) / max(min(blob_ar, template_ar), 0.01)
        if ar_ratio > 2.5:
            return -1.0
        return hu_dist

    @staticmethod
    def _nms_points(candidates: list[Tuple[float, float, float]], radius: int) -> List[Tuple[float, float]]:
        if not candidates:
            return []
        candidates.sort(key=lambda item: item[2])
        results: List[Tuple[float, float]] = []
        radius_sq = radius * radius
        for cx, cy, _score in candidates:
            too_close = False
            for rx, ry in results:
                if (cx - rx) ** 2 + (cy - ry) ** 2 < radius_sq:
                    too_close = True
                    break
            if not too_close:
                results.append((cx, cy))
        return results

    @staticmethod
    def _build_foreground_mask(img: np.ndarray, template_info: dict, color_weight: float) -> np.ndarray:
        has_color = template_info.get("has_color", False)
        dominant_hsv = template_info.get("dominant_hsv")
        color_tol_hsv = template_info.get("color_tol_hsv")

        if has_color and dominant_hsv is not None and color_tol_hsv is not None:
            hsv_img = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            h_value, s_value, v_value = dominant_hsv
            dh, ds, dv = color_tol_hsv
            tol_scale = 2.0 - 1.5 * color_weight
            dh = max(5, int(dh * tol_scale))
            ds = max(20, int(ds * tol_scale))
            dv = max(30, int(dv * tol_scale))
            return ShapeExtractor._hsv_in_range(hsv_img, h_value, s_value, v_value, dh, ds, dv)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        return cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            11,
            4,
        )

    @staticmethod
    def _hsv_in_range(hsv_img: np.ndarray, h_value: int, s_value: int, v_value: int, dh: int, ds: int, dv: int) -> np.ndarray:
        s_lo, s_hi = max(0, s_value - ds), min(255, s_value + ds)
        v_lo, v_hi = max(0, v_value - dv), min(255, v_value + dv)
        if h_value - dh < 0:
            mask1 = cv2.inRange(hsv_img, np.array([0, s_lo, v_lo], np.uint8), np.array([h_value + dh, s_hi, v_hi], np.uint8))
            mask2 = cv2.inRange(hsv_img, np.array([180 + (h_value - dh), s_lo, v_lo], np.uint8), np.array([180, s_hi, v_hi], np.uint8))
            return cv2.bitwise_or(mask1, mask2)
        if h_value + dh > 180:
            mask1 = cv2.inRange(hsv_img, np.array([h_value - dh, s_lo, v_lo], np.uint8), np.array([180, s_hi, v_hi], np.uint8))
            mask2 = cv2.inRange(hsv_img, np.array([0, s_lo, v_lo], np.uint8), np.array([(h_value + dh) - 180, s_hi, v_hi], np.uint8))
            return cv2.bitwise_or(mask1, mask2)
        return cv2.inRange(hsv_img, np.array([h_value - dh, s_lo, v_lo], np.uint8), np.array([h_value + dh, s_hi, v_hi], np.uint8))

    @staticmethod
    def _extract_dominant_color(hsv_crop: np.ndarray, fg_mask: np.ndarray):
        pixels = hsv_crop[fg_mask]
        if len(pixels) == 0:
            return (0, 0, 128), (15, 60, 60), False

        h_vals = pixels[:, 0].astype(np.float32)
        s_vals = pixels[:, 1].astype(np.float32)
        v_vals = pixels[:, 2].astype(np.float32)
        h_rad = h_vals * (np.pi / 90.0)
        h_median = int(np.round(np.arctan2(np.median(np.sin(h_rad)), np.median(np.cos(h_rad))) * (90.0 / np.pi)) % 180)
        s_median = int(np.median(s_vals))
        v_median = int(np.median(v_vals))

        h_mad = max(10, int(np.median(np.abs(h_vals - h_median))) * 2)
        s_mad = max(40, int(np.median(np.abs(s_vals - s_median))) * 2)
        v_mad = max(50, int(np.median(np.abs(v_vals - v_median))) * 2)
        has_color = s_median > 40
        return (h_median, s_median, v_median), (h_mad, s_mad, v_mad), has_color


def _shape_digitize(figure: str, params: Dict[str, Any]):
    template_info = params.get("template_info")
    if template_info is None:
        raise ValueError("请先使用截图按钮截取图例形状")

    points = ShapeExtractor.extract(
        str(figure or ""),
        template_info=template_info,
        mask_polygons=params.get("mask_polygons"),
        mask_include_mode=bool(params.get("mask_include_mode", True)),
        step=int(params.get("step", 5) or 5),
        threshold=float(params.get("threshold", 0.65) or 0.65),
        color_weight=float(params.get("color_weight", 0.7) or 0.7),
    )
    xs = [float(point[0]) for point in list(points or [])]
    ys = [float(point[1]) for point in list(points or [])]
    return line_from_xy(xs, ys)


def register_extensions(registry) -> None:
    registry.register_digitize(
        DigitizeExtension(
            type=SHAPE_DIGITIZE_EXTENSION_TYPE,
            name="图形识别",
            handler=_shape_digitize,
            description="按截图模板和匹配阈值搜索图中相同形状。",
            version=_BUILTIN_EXTENSION_VERSION,
            source_kind="builtin",
            tool_tier="experimental",
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
