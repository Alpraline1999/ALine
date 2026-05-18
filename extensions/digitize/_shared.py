from __future__ import annotations

from typing import Any, Iterable, List, Sequence, Tuple

import cv2
import numpy as np

from digitize.image_io import cv2_imread_unicode


Point = Tuple[float, float]


def read_image(image_path: str):
    image = cv2_imread_unicode(str(image_path or ""))
    if image is None:
        raise ValueError(f"无法读取图片: {image_path}")
    return image


def apply_mask_polygons(mask: np.ndarray, polygons: Any, include_mode: bool) -> np.ndarray:
    if not polygons:
        return mask
    region_mask = np.zeros(mask.shape[:2], dtype=np.uint8)
    pts_list = []
    for polygon in list(polygons or []):
        try:
            pts = np.array([(int(x_value), int(y_value)) for x_value, y_value in polygon], dtype=np.int32)
        except Exception:
            continue
        if len(pts) >= 3:
            pts_list.append(pts)
    if not pts_list:
        return mask
    cv2.fillPoly(region_mask, pts_list, 255)
    if include_mode:
        return cv2.bitwise_and(mask, region_mask)
    return cv2.bitwise_and(mask, cv2.bitwise_not(region_mask))


def color_mask_from_sampled(
    image_bgr: np.ndarray,
    sampled_color: dict[str, Any] | None,
    *,
    tolerance: int,
) -> np.ndarray:
    sampled = dict(sampled_color or {})
    if not sampled:
        raise ValueError("请先提供采样颜色")
    target_bgr = np.array(
        [[[int(sampled.get("b", 0) or 0), int(sampled.get("g", 0) or 0), int(sampled.get("r", 0) or 0)]]],
        dtype=np.uint8,
    )
    target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0, 0]
    h_value, s_value, v_value = [int(value) for value in target_hsv]
    hsv_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    h_tol = max(5, min(60, int(tolerance)))
    s_tol = max(15, min(255, int(tolerance) * 4))
    v_tol = max(15, min(255, int(tolerance) * 4))
    return hsv_mask(hsv_image, h_value, s_value, v_value, h_tol, s_tol, v_tol)


def hsv_mask(
    hsv_image: np.ndarray,
    h_value: int,
    s_value: int,
    v_value: int,
    h_tol: int,
    s_tol: int,
    v_tol: int,
) -> np.ndarray:
    s_lo, s_hi = max(0, s_value - s_tol), min(255, s_value + s_tol)
    v_lo, v_hi = max(0, v_value - v_tol), min(255, v_value + v_tol)
    if h_value - h_tol < 0:
        mask1 = cv2.inRange(hsv_image, np.array([0, s_lo, v_lo], np.uint8), np.array([h_value + h_tol, s_hi, v_hi], np.uint8))
        mask2 = cv2.inRange(hsv_image, np.array([180 + (h_value - h_tol), s_lo, v_lo], np.uint8), np.array([180, s_hi, v_hi], np.uint8))
        return cv2.bitwise_or(mask1, mask2)
    if h_value + h_tol > 180:
        mask1 = cv2.inRange(hsv_image, np.array([h_value - h_tol, s_lo, v_lo], np.uint8), np.array([180, s_hi, v_hi], np.uint8))
        mask2 = cv2.inRange(hsv_image, np.array([0, s_lo, v_lo], np.uint8), np.array([(h_value + h_tol) - 180, s_hi, v_hi], np.uint8))
        return cv2.bitwise_or(mask1, mask2)
    return cv2.inRange(hsv_image, np.array([h_value - h_tol, s_lo, v_lo], np.uint8), np.array([h_value + h_tol, s_hi, v_hi], np.uint8))


def grayscale_curve_mask(
    image_bgr: np.ndarray,
    *,
    threshold_mode: str,
    threshold: int,
    invert: bool,
    blur_size: int,
    morph_close: int,
) -> np.ndarray:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    blur_kernel = max(0, int(blur_size))
    if blur_kernel >= 2:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        gray = cv2.GaussianBlur(gray, (blur_kernel, blur_kernel), 0)
    mode = str(threshold_mode or "otsu").strip().lower()
    binary_mode = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    if mode == "manual":
        _, mask = cv2.threshold(gray, int(threshold), 255, binary_mode)
    else:
        _, mask = cv2.threshold(gray, 0, 255, binary_mode | cv2.THRESH_OTSU)
    close_size = max(0, int(morph_close))
    if close_size >= 2:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (close_size, close_size))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return mask


def trace_mask_columns(mask: np.ndarray, *, step: int, y_mode: str) -> List[Point]:
    height, width = mask.shape[:2]
    points: List[Point] = []
    stride = max(1, int(step))
    mode = str(y_mode or "median").strip().lower()
    for x_value in range(0, width, stride):
        y_indices = np.where(mask[:, x_value] > 0)[0]
        if y_indices.size == 0:
            continue
        if mode == "mean":
            y_value = float(np.mean(y_indices))
        else:
            y_value = float(np.median(y_indices))
        points.append((float(x_value), y_value))
    if width > 0 and (not points or points[-1][0] != float(width - 1)):
        y_indices = np.where(mask[:, width - 1] > 0)[0]
        if y_indices.size > 0:
            points.append((float(width - 1), float(np.median(y_indices))))
    return points


def fill_point_gaps(points: Sequence[Point], *, max_gap: float, step: int) -> List[Point]:
    source = list(points)
    if len(source) < 2 or max_gap <= 0:
        return source
    filled: List[Point] = [source[0]]
    stride = max(1, int(step))
    for left, right in zip(source, source[1:]):
        filled.append(right)
        gap = right[0] - left[0]
        if gap <= stride or gap > max_gap:
            continue
        insert_count = int(gap // stride) - 1
        for index in range(insert_count):
            ratio = float(index + 1) / float(insert_count + 1)
            x_value = left[0] + ratio * (right[0] - left[0])
            y_value = left[1] + ratio * (right[1] - left[1])
            filled.insert(-1, (float(x_value), float(y_value)))
    filled.sort(key=lambda item: item[0])
    return filled


def smooth_point_series(points: Sequence[Point], *, window: int) -> List[Point]:
    values = list(points)
    if len(values) < 3 or window <= 1:
        return values
    radius = max(1, int(window) // 2)
    smoothed: List[Point] = []
    for index, (x_value, _y_value) in enumerate(values):
        lo = max(0, index - radius)
        hi = min(len(values), index + radius + 1)
        segment = [values[item][1] for item in range(lo, hi)]
        smoothed.append((float(x_value), float(np.mean(segment))))
    return smoothed


def downsample_points(points: Sequence[Point], *, max_points: int) -> List[Point]:
    values = list(points)
    limit = max(1, int(max_points))
    if len(values) <= limit:
        return values
    stride = max(1, len(values) // limit)
    return values[::stride]


def component_centroids(mask: np.ndarray, *, min_area: int, max_area: int) -> List[Point]:
    num_labels, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    points: List[Point] = []
    for index in range(1, num_labels):
        area = int(stats[index, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        if max_area > 0 and area > max_area:
            continue
        x_value, y_value = centroids[index]
        points.append((float(x_value), float(y_value)))
    return points


def dominant_color_centers(
    image_bgr: np.ndarray,
    *,
    cluster_count: int,
    saturation_min: int,
    value_min: int,
) -> List[tuple[int, int, int]]:
    hsv_image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    pixels = hsv_image.reshape(-1, 3)
    filtered = pixels[(pixels[:, 1] >= int(saturation_min)) & (pixels[:, 2] >= int(value_min))]
    if filtered.shape[0] < max(4, cluster_count):
        raise ValueError("图像中满足条件的彩色像素不足，无法进行多色聚类")
    sample = np.float32(filtered[: min(len(filtered), 20000)])
    cluster_total = max(1, min(int(cluster_count), len(sample)))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _compactness, labels, centers = cv2.kmeans(sample, cluster_total, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=cluster_total)
    ranked = sorted(
        [(int(counts[index]), tuple(int(round(value)) for value in centers[index])) for index in range(cluster_total)],
        key=lambda item: item[0],
        reverse=True,
    )
    return [center for _count, center in ranked]
