# Phase 25 Task 2: 实现懒加载数据代理

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 25`

## 目标

在 ZIP 容器格式基础上，为 `DataSeries` 和 `Curve` 模型引入懒加载代理，使曲线数据在使用时才从 ZIP 读取，而在模型层面保持透明。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/lazy_series.py` | **新建**：`LazyDataSeries` 和 `LazyCurve` 代理类 |
| `models/schemas.py` | 不修改（代理继承自 DataSeries/Curve） |

## 设计方案

### LazyDataSeries

```python
# core/lazy_series.py
from __future__ import annotations
import json
import zipfile
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from models.schemas import DataSeries


class LazyDataSeries(DataSeries):
    """延迟加载的 DataSeries。
    
    在需要访问 x/y/y_err 时才从项目文件读取。
    一旦加载，行为与普通 DataSeries 无异。
    """
    
    _project_path: str = ""
    _loaded: bool = False
    
    def __init__(self, *, project_path: str = "", **kwargs):
        # 从 kwargs 中分离 x/y/y_err（首次加载时不会传入）
        self._project_path = project_path
        self._loaded = False
        # 不调用父类 __init__ 的 x/y/y_err 设置
        super().__init__(**{k: v for k, v in kwargs.items() 
                           if k not in ('x', 'y', 'y_err')})
        # 不设置 x/y/y_err，保持默认空列表
        if 'x' in kwargs:
            object.__setattr__(self, '_x_loaded', kwargs.get('x'))
        if 'y' in kwargs:
            object.__setattr__(self, '_y_loaded', kwargs.get('y'))
    
    @property
    def x(self) -> List[float]:
        if not self._loaded and self._project_path:
            self._load()
        if hasattr(self, '_x_loaded'):
            return self._x_loaded
        return []
    
    @x.setter
    def x(self, value: List[float]):
        self._x_loaded = value
        self._loaded = True
    
    @property
    def y(self) -> List[float]:
        if not self._loaded and self._project_path:
            self._load()
        if hasattr(self, '_y_loaded'):
            return self._y_loaded
        return []
    
    @y.setter
    def y(self, value: List[float]):
        self._y_loaded = value
        self._loaded = True
    
    @property
    def y_err(self) -> Optional[List[float]]:
        if not self._loaded and self._project_path:
            self._load()
        if hasattr(self, '_y_err_loaded'):
            return self._y_err_loaded
        return None
    
    @y_err.setter
    def y_err(self, value: Optional[List[float]]):
        self._y_err_loaded = value
        self._loaded = True
    
    def _load(self) -> None:
        """从 ZIP 项目文件加载数据。"""
        if not self._project_path or not Path(self._project_path).exists():
            return
        try:
            import zipfile
            with zipfile.ZipFile(self._project_path, 'r') as zf:
                data = json.loads(zf.read(f'data/series_{self.id}.json'))
            self._x_loaded = data.get('x', [])
            self._y_loaded = data.get('y', [])
            self._y_err_loaded = data.get('y_err')
            self._loaded = True
        except (KeyError, FileNotFoundError, zipfile.BadZipFile):
            pass  # 懒加载失败则返回空数据
```

### LazyCurve（类似模式）

```python
class LazyCurve(Curve):
    """延迟加载的 Curve。"""
    
    _project_path: str = ""
    _loaded: bool = False
    
    @property
    def x_data(self) -> List[float]:
        if not self._loaded: self._load()
        return super().x_data  # or self._x_data_loaded
    
    # ... 同样对 y_data, x_actual, y_actual
```

### 使用方式

在 `ProjectSerializer` 或 `ZipProjectSerializer` 加载 `project.json` 后，替换所有 `DataSeries` 实例为 `LazyDataSeries`：

```python
def _convert_to_lazy(obj, project_path: str):
    """递归替换 DataSeries → LazyDataSeries"""
    if isinstance(obj, DataSeries) and not isinstance(obj, LazyDataSeries):
        lazy = LazyDataSeries(project_path=project_path, **obj.model_dump())
        return lazy
    if isinstance(obj, dict):
        return {k: _convert_to_lazy(v, project_path) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_to_lazy(item, project_path) for item in obj]
    return obj
```

## 验证清单

- [ ] 打开项目后 `DataSeries.x` 不触发 zipfile 操作（未访问时）
- [ ] 首次访问 `DataSeries.x` 时自动从 ZIP 读取
- [ ] 加载过的数据缓存到内存，二次访问不读盘
- [ ] 修改数据后标记已加载，后续保存时走正常序列化路径
- [ ] 所有测试通过（代理行为透明）

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
