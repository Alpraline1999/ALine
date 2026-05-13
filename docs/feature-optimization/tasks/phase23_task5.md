# Phase 23 Task 5: extension_api.py 收口为纯重导出

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 23`

## 目标

将 `core/extension_api.py` 从 1814 行缩减为纯重导出层（<50 行），并迁移所有现存 import 引用。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_api.py` | 替换为纯重导出 |
| 所有 import 此模块的文件 | 逐步迁移 |

## 实施步骤

### Step 1: 清点所有 import 引用

搜索全仓库中所有引用：

```bash
grep -rn "from core.extension_api\|import core.extension_api" --include="*.py" . | grep -v __pycache__
```

典型调用方：
- `core/extension_loader.py`
- `core/builtin_extensions.py`
- `processing/data_engine.py`
- `core/analysis_engine.py`
- `core/global_assets.py`
- `ui/widgets/project_tree.py`
- `ui/widgets/extension_panel.py`
- `ui/widgets/extension_options_form.py`
- `ui/pages/settings_page.py`
- `build.py`
- `main.py`

### Step 2: 替换 extension_api.py

```python
# core/extension_api.py
"""
扩展 API — 兼容重导出层。
新代码请直接引用对应模块。
"""
from core.extension_definition import *               # noqa: F401, F403
from core.extension_registry import extension_registry  # noqa: F401
from core.extension_loader import (                     # noqa: F401
    load_configured_extensions,
    reload_extensions,
    get_extension_load_status,
)
from core.extension_validator import ExtensionValidator  # noqa: F401

__all__ = [
    "ExtensionConfigField", "ProcessingExtension", "AnalysisExtension",
    "PlotExtension", "DigitizeExtension", "PlotExtensionContext",
    "PlotStyleExtension", "CurveStyleExtension",
    "ExtensionRegistry", "extension_registry",
    "load_configured_extensions", "reload_extensions",
    "get_extension_load_status", "ExtensionValidator",
    "normalize_extension_field_type", "normalize_extension_version",
    "normalize_extension_source_kind", "normalize_extension_tool_tier",
    "normalize_extension_lines_number", "normalize_extension_lines_list",
    "normalize_extension_lines_config", "normalize_plot_extension_phases",
    "extension_lines_number", "extension_lines_support_text",
    "extension_lines_picker_visible", "validate_extension_lines_list",
    "build_extension_entry", "invoke_processing_extension_handler",
    "invoke_analysis_extension_handler", "invoke_plot_extension_handler",
    "invoke_digitize_extension_handler",
    "get_extension_load_status", "clear_extension_cache",
]
```

### Step 3: 逐步迁移调用方

| 引用方 | 建议迁移目标 |
|---|---|
| `core/builtin_extensions.py` | `extension_definition` + `extension_registry` |
| `processing/data_engine.py` | `extension_definition` + `extension_registry` |
| `core/analysis_engine.py` | `extension_registry` |
| `ui/widgets/extension_panel.py` | `extension_loader` + `extension_registry` |
| `ui/widgets/extension_options_form.py` | `extension_definition` |
| `ui/pages/settings_page.py` | `extension_loader` |

### Step 4: 验证

- 全量测试通过
- 扩展加载、注册、调用全路径正常
- UI 扩展管理页面正常
- 无任何 ImportError

## 验证清单

- [ ] `extension_api.py` ≤ 100 行
- [ ] 4 个新模块无循环 import
- [ ] 旧 import 仍工作
- [ ] 新 import 也可用
- [ ] 全量测试 0 失败

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `end`，验证范围 `全量测试 + 扩展加载测试`
