"""延迟加载数据代理 — LazyDataSeries 和 LazyCurve

在 ZIP 容器格式基础上，为 DataSeries 和 Curve 提供懒加载代理：
数据点字段 (x/y/y_err 和 x_data/y_data/x_actual/y_actual)
在首次访问时才从 ZIP 文件读取，模型层面保持透明。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, TYPE_CHECKING

from pydantic import PrivateAttr

from models.schemas import Curve, DataSeries

if TYPE_CHECKING:
    from models.schemas import Project


# ══════════════════════════════════════════════════════════════════
# LazyDataSeries
# ══════════════════════════════════════════════════════════════════


class LazyDataSeries(DataSeries):

    _project_path: str = PrivateAttr(default="")
    _loaded: bool = PrivateAttr(default=False)

    def __init__(self, *, project_path: str = "", **kwargs: Any) -> None:
        data_given = any(k in kwargs for k in ("x", "y", "y_err"))
        super().__init__(**kwargs)
        self._project_path = project_path
        if not data_given:
            object.__setattr__(self, "_loaded", False)

    def _load(self) -> None:
        if not self._project_path:
            return
        if not Path(self._project_path).exists():
            return

        from core.zip_serializer import ZipProjectSerializer

        data = ZipProjectSerializer.load_series_data(
            self._project_path, self.id
        )
        if data is None:
            object.__setattr__(self, "_loaded", True)
            return

        self.__dict__["x"] = data.get("x", [])
        self.__dict__["y"] = data.get("y", [])
        if "y_err" in data:
            self.__dict__["y_err"] = data["y_err"]
        object.__setattr__(self, "_loaded", True)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        self.x
        self.y
        self.y_err
        return super().model_dump(**kwargs)


def _make_series_property(field_name: str) -> property:
    def getter(self: Any) -> Any:
        if not self._loaded and self._project_path:
            self._load()
        return self.__dict__.get(
            field_name, [] if field_name != "y_err" else None
        )

    def setter(self: Any, value: Any) -> None:
        self.__dict__[field_name] = value
        object.__setattr__(self, "_loaded", True)

    return property(getter, setter)


setattr(LazyDataSeries, "x", _make_series_property("x"))
setattr(LazyDataSeries, "y", _make_series_property("y"))
setattr(LazyDataSeries, "y_err", _make_series_property("y_err"))


# ══════════════════════════════════════════════════════════════════
# LazyCurve
# ══════════════════════════════════════════════════════════════════


class LazyCurve(Curve):

    _project_path: str = PrivateAttr(default="")
    _loaded: bool = PrivateAttr(default=False)

    def __init__(self, *, project_path: str = "", **kwargs: Any) -> None:
        data_given = any(
            k in kwargs for k in ("x_data", "y_data", "x_actual", "y_actual")
        )
        super().__init__(**kwargs)
        self._project_path = project_path
        if not data_given:
            object.__setattr__(self, "_loaded", False)

    def _load(self) -> None:
        if not self._project_path:
            return
        if not Path(self._project_path).exists():
            return

        from core.zip_serializer import ZipProjectSerializer

        data = ZipProjectSerializer.load_curve_data(
            self._project_path, self.id
        )
        if data is None:
            object.__setattr__(self, "_loaded", True)
            return

        self.__dict__["x_data"] = data.get("x_data", [])
        self.__dict__["y_data"] = data.get("y_data", [])
        self.__dict__["x_actual"] = data.get("x_actual", [])
        self.__dict__["y_actual"] = data.get("y_actual", [])
        object.__setattr__(self, "_loaded", True)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        self.x_data
        self.y_data
        self.x_actual
        self.y_actual
        return super().model_dump(**kwargs)


def _make_curve_property(field_name: str) -> property:
    def getter(self: Any) -> Any:
        if not self._loaded and self._project_path:
            self._load()
        return self.__dict__.get(field_name, [])

    def setter(self: Any, value: Any) -> None:
        self.__dict__[field_name] = value
        object.__setattr__(self, "_loaded", True)

    return property(getter, setter)


setattr(LazyCurve, "x_data", _make_curve_property("x_data"))
setattr(LazyCurve, "y_data", _make_curve_property("y_data"))
setattr(LazyCurve, "x_actual", _make_curve_property("x_actual"))
setattr(LazyCurve, "y_actual", _make_curve_property("y_actual"))


# ══════════════════════════════════════════════════════════════════
# convert_to_lazy
# ══════════════════════════════════════════════════════════════════


def convert_to_lazy(project: Project, project_path: str) -> Project:
    for df in project.data_files:
        for i, s in enumerate(df.series):
            if not isinstance(s, LazyDataSeries):
                df.series[i] = LazyDataSeries(
                    project_path=project_path, **s.model_dump()
                )

    for ds in project.datasets:
        for i, s in enumerate(ds.series):
            if not isinstance(s, LazyDataSeries):
                ds.series[i] = LazyDataSeries(
                    project_path=project_path, **s.model_dump()
                )

    for img in project.images:
        for i, c in enumerate(img.curves):
            if not isinstance(c, LazyCurve):
                img.curves[i] = LazyCurve(
                    project_path=project_path, **c.model_dump()
                )

    for i, c in enumerate(project.imported_curves):
        if not isinstance(c, LazyCurve):
            project.imported_curves[i] = LazyCurve(
                project_path=project_path, **c.model_dump()
            )

    return project
