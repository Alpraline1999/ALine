# Phase 23 Task 1: 提取 ExtensionDefinition 模块

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 23`

## 目标

从 1814 行的 `core/extension_api.py` 中提取所有扩展 Dataclass 定义到独立的 `core/extension_definition.py`。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_api.py` | 移除所有 class/Type/dataclass 定义，改为 import 重导出 |
| `core/extension_definition.py` | **新建**：所有扩展 Dataclass + 类型 normalize 函数 |
| 所有 `from core.extension_api import ProcessingExtension` 的调用方 | 逐步迁移 import 路径 |

## 需要移动的内容

### 1. Dataclass 定义

```python
# 以下全部原封不动从 extension_api.py 移到 extension_definition.py
@dataclass(frozen=True)
class ExtensionConfigField: ...

@dataclass(frozen=True)
class ProcessingExtension: ...
@dataclass(frozen=True)
class AnalysisExtension: ...
@dataclass(frozen=True)
class PlotExtension: ...
@dataclass(frozen=True)
class DigitizeExtension: ...
@dataclass
class PlotExtensionContext: ...
@dataclass(frozen=True)
class PlotStyleExtension: ...
@dataclass(frozen=True)
class CurveStyleExtension: ...
```

### 2. 类型系统函数

```python
# normalize 函数族
normalize_extension_field_type()
normalize_extension_version()
normalize_extension_source_kind()
normalize_extension_tool_tier()
normalize_extension_lines_number()
normalize_extension_lines_list()
normalize_extension_lines_config()
normalize_plot_extension_phases()
normalize_extension_lines_list()

# 版本工具
parse_extension_version()
compare_extension_versions()

# 查询辅助
extension_lines_number()
extension_lines_support_text()
extension_lines_picker_visible()
validate_extension_lines_list()

# 标签系统
_EXTENSION_CATEGORY_LABELS
_EXTENSION_SOURCE_LABELS
_EXTENSION_ORIGIN_LABELS
_EXTENSION_SOURCE_HINTS
_EXTENSION_TOOL_TIER_LABELS
_EXTENSION_SOURCE_KINDS
_NON_EXTENSION_MODULE_FILENAMES
```

### 3. 模块依赖

`extension_definition.py` 的依赖应该很轻：
```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Iterable
import re
```

**不依赖** `extension_registry` 或 `extension_loader`。

## 实施步骤

### Step 1: 创建 extension_definition.py

将上述所有 class 和函数按逻辑分组复制到新文件：
1. 标签字典（`_EXTENSION_CATEGORY_LABELS` 等）
2. Dataclass 定义（`ExtensionConfigField` → `CurveStyleExtension`）
3. 类型 normalize 函数
4. 辅助查询函数

### Step 2: 修复引用

在新模块中，`DEFAULT_EXTENSION_VERSION`、`_EXTENSION_VERSION_PATTERN` 等常量需要复制。
检查 `normalize_extension_lines_list` 调用了 `normalize_extension_lines_number` — 确保函数都在同一模块内。

### Step 3: 更新 extension_api.py

```python
# core/extension_api.py — 改为重导出
"""
扩展 API — 兼容入口
所有定义已移至 core/extension_definition.py
"""
from core.extension_definition import *  # noqa: F401, F403
```

### Step 4: 更新调用方

搜索 `from core.extension_api import ProcessingExtension`、`from core.extension_api import normalize_extension_version` 等模式，迁移到 `core.extension_definition`：

```python
# 旧
from core.extension_api import ProcessingExtension, ExtensionConfigField

# 新
from core.extension_definition import ProcessingExtension, ExtensionConfigField
```

**兼容期策略**：通过 `extension_api.py` 的 `*` 重导出保持向后兼容，新代码直接引用 `extension_definition`。

## 单元测试

`TestNormalizeFunctions` 应被拆分到 `tests/test_extension_definition.py`：

```python
class TestExtensionDefinition(unittest.TestCase):
    def test_normalize_field_type(self):
        self.assertEqual(normalize_extension_field_type("bool"), "boolean")
        self.assertEqual(normalize_extension_field_type("int"), "integer")
        self.assertEqual(normalize_extension_field_type("float"), "number")
    
    def test_normalize_version(self):
        self.assertEqual(normalize_extension_version("1.0.0"), "1.0.0")
        with self.assertRaises(ValueError):
            normalize_extension_version("1.0")
    
    def test_extension_lines_number(self):
        self.assertEqual(normalize_extension_lines_number((1, 1)), (1, 1))
        self.assertEqual(normalize_extension_lines_number((2, -1)), (2, -1))
```

## 边界情况

| 场景 | 预期 |
|---|---|
| 循环 import | `extension_definition` 不 import 任何其他 core 模块，无循环风险 |
| 5 种正常 + 4 种接口示例扩展 | 加载正常 |
| normalize 函数入参 None 全部 | 全部有默认值/安全回退 |

## 验证清单

- [ ] `from core.extension_definition import ProcessingExtension` 正常工作
- [ ] `from core.extension_api import ProcessingExtension` 仍然工作（兼容重导出）
- [ ] 所有扩展正常加载和执行
- [ ] `test_backend.py` 全部通过（特别是 `TestCommandLayer`、`TestSchemas`）

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
