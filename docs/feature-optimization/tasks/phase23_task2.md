# Phase 23 Task 2: 提取 ExtensionRegistry 模块

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 23`

## 目标

从 `core/extension_api.py` 中提取 `ExtensionRegistry` 类及其全局单例到独立的 `core/extension_registry.py` 模块。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_api.py` | 移除 `ExtensionRegistry` 类和 `extension_registry` 实例，改为重导出 |
| `core/extension_registry.py` | **新建** |
| `core/extension_definition.py` | 依赖（import Dataclass 类型） |
| `core/extension_loader.py` | 依赖（后续 task 3 将用到） |
| `data_engine.py`, `analysis_engine.py`, `project_tree.py` 等 | 逐步迁移 import |

## 需要移动的内容

```python
# 从 extension_api.py 中提取:
class ExtensionRegistry:
    """扩展注册表 — 管理所有注册的扩展。"""
    
    def __init__(self):
        self._processing: Dict[str, ProcessingExtension] = {}
        self._analysis: Dict[str, AnalysisExtension] = {}
        self._plot: Dict[str, PlotExtension] = {}
        self._digitize: Dict[str, DigitizeExtension] = {}
        self._plot_style: Dict[str, PlotStyleExtension] = {}
        self._curve_style: Dict[str, CurveStyleExtension] = {}
    
    def register_processing(self, ext) -> None: ...
    def register_analysis(self, ext) -> None: ...
    def register_plot(self, ext) -> None: ...
    def register_digitize(self, ext) -> None: ...
    def register_plot_style(self, ext) -> None: ...
    def register_curve_style(self, ext) -> None: ...
    
    def get_processing(self, type_: str) -> Optional[ProcessingExtension]: ...
    def get_analysis(self, type_: str) -> Optional[AnalysisExtension]: ...
    def get_plot(self, type_: str) -> Optional[PlotExtension]: ...
    def get_digitize(self, type_: str) -> Optional[DigitizeExtension]: ...
    
    def iter_extensions(self): ...
    def get_categories(self) -> Dict[str, List]: ...
    def get_total_count(self) -> int: ...
    def get_processing_types(self) -> List[str]: ...
    def get_analysis_types(self) -> List[str]: ...
    def get_plot_types(self) -> List[str]: ...
    def get_digitize_types(self) -> List[str]: ...
    
    def detect_conflicts(self) -> List[str]:
        """检测 type 冲突，返回冲突描述列表。"""
        ...

# 及其实例
extension_registry = ExtensionRegistry()
```

### 注册方法详细实现

```python
def register_processing(self, ext: ProcessingExtension) -> None:
    name_key = _extension_name_key(ext.type)  # 注意：此函数也需要引入
    if name_key in self._processing:
        existing = self._processing[name_key]
        # 同 source 同 type 的覆盖更新
        # 不同 source 的保留先注册的
        if ext.source_kind == existing.source_kind:
            pass  # 同源覆盖
        else:
            return  # 异源保留先注册者
    self._processing[name_key] = ext
```

## 实施步骤

### Step 1: 创建 extension_registry.py

```python
# core/extension_registry.py
from __future__ import annotations
from typing import Dict, List, Optional, Iterator
from core.extension_definition import (
    ProcessingExtension, AnalysisExtension, PlotExtension, DigitizeExtension,
    PlotStyleExtension, CurveStyleExtension,
    _extension_name_key,
)


class ExtensionRegistry:
    """扩展注册表。
    
    四类扩展分四本字典存储，支持按 type 查询和迭代。
    同一个 type 名在相同 source_kind 下可被后注册的扩展覆盖。
    """
    # 如上所述的所有方法 ...


# 全局单例
extension_registry = ExtensionRegistry()
```

### Step 2: 移除冲突的注册检查

确保 `register_*` 方法中的冲突检测逻辑完整保留：
- 同 `source_kind` 且同 `type` → 后注册覆盖先注册
- 不同 `source_kind` 且同 `type` → 内置优先，外部不覆盖内置

### Step 3: 更新 extension_api.py

```python
# core/extension_api.py
from core.extension_definition import *  # noqa
from core.extension_registry import extension_registry  # noqa
```

### Step 4: 更新调用方

```python
# 旧
from core.extension_api import extension_registry

# 新
from core.extension_registry import extension_registry
```

## 单元测试

```python
# tests/test_extension_registry.py
class TestExtensionRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ExtensionRegistry()
    
    def test_register_and_get_processing(self):
        ext = ProcessingExtension(type="test", name="测试", handler=lambda l, p: l[0],
                                   source_kind="builtin")
        self.registry.register_processing(ext)
        self.assertEqual(self.registry.get_processing("test"), ext)
    
    def test_register_duplicate_type_overwrites(self):
        ext1 = ProcessingExtension(type="same", name="旧", handler=lambda l, p: l[0],
                                    source_kind="builtin")
        ext2 = ProcessingExtension(type="same", name="新", handler=lambda l, p: l[0],
                                    source_kind="builtin")
        self.registry.register_processing(ext1)
        self.registry.register_processing(ext2)
        self.assertEqual(self.registry.get_processing("same").name, "新")
    
    def test_builtin_does_not_overwrite_external(self):
        # 外部的先注册，内置的不覆盖
        ext_ext = ProcessingExtension(type="x", name="外部", handler=lambda l, p: l[0],
                                       source_kind="external")
        ext_builtin = ProcessingExtension(type="x", name="内置", handler=lambda l, p: l[0],
                                          source_kind="builtin")
        self.registry.register_processing(ext_ext)
        self.registry.register_processing(ext_builtin)
        self.assertEqual(self.registry.get_processing("x").name, "外部")  # 保留先注册
    
    def test_get_nonexistent_returns_none(self):
        self.assertIsNone(self.registry.get_processing("nonexistent"))
    
    def test_get_categories_returns_all_types(self):
        cats = self.registry.get_categories()
        self.assertIn("processing", cats)
        self.assertIn("analysis", cats)
        self.assertIn("plot", cats)
        self.assertIn("digitize", cats)
    
    def test_detect_conflicts_no_conflicts(self):
        self.assertEqual(self.registry.detect_conflicts(), [])
```

## 边界情况

| 场景 | 预期 |
|---|---|
| 注册相同 type + 同 source | 覆盖（更新 version） |
| 注册相同 type + 不同 source | 保留先注册的 |
| 查询不存在的 type | 返回 None |
| 空注册表 detech_conflicts | 返回空列表 |

## 验证清单

- [ ] `TestExtensionRegistry` 全部通过
- [ ] 已有扩展加载后查询正常
- [ ] `extension_registry` 全局单例在 `core/extension_registry.py` 中定义
- [ ] `from core.extension_api import extension_registry` 仍然工作

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
