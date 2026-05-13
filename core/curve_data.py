from __future__ import annotations

"""曲线运行时数组后端。

该模块负责把曲线主数据从 point-list / x-y 临时列表收口到 numpy
数组后端，并提供兼容序列视图，供现有代码渐进迁移。
"""

from dataclasses import dataclass
from typing import Any, Iterator, overload, Sequence, cast

import numpy as np


class SeriesArrayView(Sequence[float]):
    """对一维数值数组的只读兼容视图。"""

    __slots__ = ("_array",)

    def __init__(self, raw: Any = None, *, copy: bool = True) -> None:
        array = np.asarray([] if raw is None else raw, dtype=float)
        if array.ndim != 1:
            array = np.reshape(array, -1)
        if copy:
            array = np.array(array, dtype=float, copy=True)
        self._array = array

    def __len__(self) -> int:
        return int(self._array.size)

    def __iter__(self) -> Iterator[float]:
        return (float(value) for value in self._array)

    @overload
    def __getitem__(self, item: int) -> float: ...
    @overload
    def __getitem__(self, item: slice) -> SeriesArrayView: ...
    def __getitem__(self, item: int | slice) -> float | SeriesArrayView:
        value = self._array[item]
        if isinstance(item, slice):
            return SeriesArrayView(value, copy=False)
        return float(value)

    def __bool__(self) -> bool:
        return self._array.size > 0

    def __array__(self, dtype: Any = None, copy: Any = None) -> np.ndarray:
        if copy is False:
            if dtype is None:
                return self._array
            return self._array.astype(dtype, copy=False)
        if copy is True:
            return np.array(self._array, dtype=dtype, copy=True)
        return np.asarray(self._array, dtype=dtype)

    def __eq__(self, other: Any) -> bool:
        try:
            return list(self) == list(other)
        except TypeError:
            return False

    def __repr__(self) -> str:
        return f"SeriesArrayView({self.tolist()!r})"

    @property
    def array(self) -> np.ndarray:
        return self._array

    def to_numpy(self, *, copy: bool = True) -> np.ndarray:
        return np.array(self._array, dtype=float, copy=copy)

    def tolist(self) -> list[float]:
        result: Any = self._array.tolist()
        return cast(list[float], result)


@dataclass(frozen=True, slots=True)
class CurveBuffer:
    """曲线主数据的运行时缓存容器。"""

    x: np.ndarray
    y: np.ndarray

    def __post_init__(self) -> None:
        x_arr = np.asarray(self.x, dtype=float).reshape(-1)
        y_arr = np.asarray(self.y, dtype=float).reshape(-1)
        if x_arr.shape != y_arr.shape:
            raise ValueError("x 与 y 长度必须一致，无法构造曲线缓存")
        object.__setattr__(self, "x", np.array(x_arr, dtype=float, copy=True))
        object.__setattr__(self, "y", np.array(y_arr, dtype=float, copy=True))

    @classmethod
    def empty(cls) -> "CurveBuffer":
        return cls(np.empty(0, dtype=float), np.empty(0, dtype=float))

    @classmethod
    def from_xy(cls, xs: Any, ys: Any) -> "CurveBuffer":
        x_view = SeriesArrayView(xs, copy=False)
        y_view = SeriesArrayView(ys, copy=False)
        if len(x_view) != len(y_view):
            raise ValueError("x_list 与 y_list 长度必须一致，无法转换为曲线缓存")
        return cls(x_view.to_numpy(copy=True), y_view.to_numpy(copy=True))

    @classmethod
    def from_line(cls, raw: Any) -> "CurveBuffer":
        if raw is None:
            return cls.empty()
        if isinstance(raw, str) and not raw.strip():
            return cls.empty()
        if isinstance(raw, (list, tuple)) and len(raw) == 0:
            return cls.empty()
        try:
            raw_array = np.asarray(raw, dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("line 必须是 point-list，即 [[x, y], ...]") from exc
        if raw_array.size == 0:
            return cls.empty()
        if raw_array.ndim != 2 or raw_array.shape[1] != 2:
            raise ValueError("line 必须是 point-list，即 [[x, y], ...]")
        if not np.isfinite(raw_array).all():
            raise ValueError("line 包含无效坐标")
        return cls(raw_array[:, 0], raw_array[:, 1])

    @classmethod
    def from_series_payload(cls, item: Any) -> "CurveBuffer":
        if isinstance(item, CurveBuffer):
            return item
        if isinstance(item, dict):
            return cls.from_xy(item.get("x", []), item.get("y", []))
        return cls.from_xy(getattr(item, "x", []), getattr(item, "y", []))

    def to_views(self) -> tuple[SeriesArrayView, SeriesArrayView]:
        return SeriesArrayView(self.x, copy=False), SeriesArrayView(self.y, copy=False)

    def to_line(self) -> list[list[float]]:
        return [[float(x_value), float(y_value)] for x_value, y_value in zip(self.x, self.y)]

    def to_series_payload(self) -> dict[str, list[float]]:
        return {"x": self.x.tolist(), "y": self.y.tolist()}

    @property
    def size(self) -> int:
        return int(self.x.size)


def line_to_curve_buffer(raw: Any) -> CurveBuffer:
    if isinstance(raw, CurveBuffer):
        return raw
    return CurveBuffer.from_line(raw)


def curve_buffer_to_line(buffer: Any) -> list[list[float]]:
    return line_to_curve_buffer(buffer).to_line()


def curve_buffer_to_views(buffer: Any) -> tuple[SeriesArrayView, SeriesArrayView]:
    return line_to_curve_buffer(buffer).to_views()


def series_payload_to_curve_buffer(item: Any) -> CurveBuffer:
    if isinstance(item, CurveBuffer):
        return item
    return CurveBuffer.from_series_payload(item)


def series_payloads_to_curve_batch(raw: Any) -> list[CurveBuffer]:
    if raw is None:
        return []
    if isinstance(raw, str) and not raw.strip():
        return []
    if isinstance(raw, (list, tuple)) and len(raw) == 0:
        return []
    return [series_payload_to_curve_buffer(item) for item in raw]
