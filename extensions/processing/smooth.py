from __future__ import annotations

from typing import List, Tuple

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def _smooth_moving_average(x_values: List[float], y_values: List[float], window: int = 3) -> Tuple[List[float], List[float]]:
    if len(x_values) < 2:
        return list(x_values), list(y_values)
    window = max(3, window | 1)
    half = window // 2
    smoothed: List[float] = []
    for index in range(len(y_values)):
        lo = max(0, index - half)
        hi = min(len(y_values), index + half + 1)
        smoothed.append(sum(y_values[lo:hi]) / (hi - lo))
    return list(x_values), smoothed


def _transpose(matrix: List[List[float]]) -> List[List[float]]:
    return [[matrix[row][column] for row in range(len(matrix))] for column in range(len(matrix[0]))]


def _matmul(left: List[List[float]], right: List[List[float]]) -> List[List[float]]:
    result = [[0.0] * len(right[0]) for _ in range(len(left))]
    for row_index in range(len(left)):
        for column_index in range(len(right[0])):
            for inner_index in range(len(right)):
                result[row_index][column_index] += left[row_index][inner_index] * right[inner_index][column_index]
    return result


def _mat_inv(matrix: List[List[float]]) -> List[List[float]]:
    size = len(matrix)
    augmented = [row[:] + [1.0 if row_index == column_index else 0.0 for column_index in range(size)] for row_index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row_index: abs(augmented[row_index][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        if abs(divisor) < 1e-12:
            raise ValueError("矩阵奇异，无法求逆")
        augmented[column] = [value / divisor for value in augmented[column]]
        for row_index in range(size):
            if row_index == column:
                continue
            factor = augmented[row_index][column]
            augmented[row_index] = [
                augmented[row_index][idx] - factor * augmented[column][idx]
                for idx in range(2 * size)
            ]
    return [row[size:] for row in augmented]


def _savgol_coeffs(window: int, poly: int) -> List[float]:
    half = window // 2
    vandermonde = [[float(offset ** power) for power in range(poly + 1)] for offset in range(-half, half + 1)]
    transpose = _transpose(vandermonde)
    return _matmul(_mat_inv(_matmul(transpose, vandermonde)), transpose)[0]


def _smooth_savgol(x_values: List[float], y_values: List[float], window: int = 5, poly: int = 2) -> Tuple[List[float], List[float]]:
    if len(x_values) < window:
        return _smooth_moving_average(x_values, y_values, window=max(3, len(x_values) | 1))
    window = max(poly + 1, window | 1)
    half = window // 2
    coeffs = _savgol_coeffs(window, poly)
    smoothed: List[float] = []
    for index in range(len(y_values)):
        samples = []
        for cursor in range(index - half, index + half + 1):
            if cursor < 0:
                samples.append(y_values[0])
            elif cursor >= len(y_values):
                samples.append(y_values[-1])
            else:
                samples.append(y_values[cursor])
        smoothed.append(sum(weight * value for weight, value in zip(coeffs, samples)))
    return list(x_values), smoothed


def _smooth_handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    options = dict(params or {})
    method = options.get("method", "savgol")
    if method == "savgol":
        nx, ny = _smooth_savgol(list(xs), list(ys), int(options.get("window", 11)), int(options.get("poly", 3)))
        return line_from_xy(nx, ny)
    if method == "moving_avg":
        nx, ny = _smooth_moving_average(list(xs), list(ys), int(options.get("window", 5)))
        return line_from_xy(nx, ny)
    return line_from_xy(list(xs), list(ys))


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="smooth",
            name="平滑",
            handler=_smooth_handler,
            description="对 Y 序列做平滑处理，适合去除高频噪声。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                ExtensionConfigField(
                    key="method",
                    label="平滑方法",
                    field_type="selective",
                    default="savgol",
                    choices=("savgol", "moving_avg"),
                ),
                ExtensionConfigField(key="window", label="窗口大小", field_type="integer", default=9, min_value=1),
                ExtensionConfigField(key="poly", label="多项式阶数", field_type="integer", default=3, min_value=1),
            ],
        )
    )
