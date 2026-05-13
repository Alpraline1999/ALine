# Phase 26 Task 1: 实现 AppContext 依赖容器

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 26`

## 目标

引入 `AppContext` 作为核心服务的显式依赖容器，替代模块级全局单例直接 import 的模式，使测试中可 mock/替换任意核心服务。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/app_context.py` | **新建** |
| `core/__init__.py` | 导出 `get_app_context` |
| `main.py` | 初始化时填充 context |
| `tests/conftest.py` | 添加 `app_context` fixture |
| `ui/main_window.py` | 通过 `get_app_context()` 获取服务 |
| 各 UI 页面 | 逐步迁移 |

## AppContext 设计

```python
# core/app_context.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.project_manager import ProjectManager
    from core.tree_manager import TreeManager
    from core.data_file_manager import DataFileManager
    from core.analysis_manager import AnalysisManager
    from core.extension_registry import ExtensionRegistry
    from core.global_assets import GlobalAssetManager
    from core.shortcut_manager import ShortcutManager


@dataclass
class AppContext:
    """应用级依赖容器。
    
    所有核心服务通过此容器访问，而非模块级 import。
    测试时可通过 set_app_context() 替换为 mock 实例。
    """
    
    project_manager: Optional["ProjectManager"] = None
    tree_manager: Optional["TreeManager"] = None
    data_file_manager: Optional["DataFileManager"] = None
    analysis_manager: Optional["AnalysisManager"] = None
    extension_registry: Optional["ExtensionRegistry"] = None
    global_assets: Optional["GlobalAssetManager"] = None
    shortcut_manager: Optional["ShortcutManager"] = None


# 全局 context 实例（模块级单例，但可通过 set_app_context 切换）
_context: AppContext = AppContext()


def get_app_context() -> AppContext:
    """获取当前应用上下文。"""
    return _context


def set_app_context(ctx: AppContext) -> None:
    """设置应用上下文（测试用）。"""
    global _context
    _context = ctx


def reset_app_context() -> None:
    """重置应用上下文为默认空容器。"""
    set_app_context(AppContext())
```

## 在 main.py 中填充

```python
# main.py
from core.app_context import AppContext, get_app_context, set_app_context

def main():
    # ... existing Qt setup ...
    
    # 初始化 context
    from core.project_manager import ProjectManager
    from core.tree_manager import TreeManager
    from core.data_file_manager import DataFileManager
    from core.analysis_manager import AnalysisManager
    from core.extension_registry import extension_registry
    from core.global_assets import global_assets
    from core.shortcut_manager import shortcut_manager
    
    pm = ProjectManager()
    ctx = AppContext(
        project_manager=pm,
        tree_manager=TreeManager(),
        data_file_manager=DataFileManager(pm),
        analysis_manager=AnalysisManager(pm),
        extension_registry=extension_registry,
        global_assets=global_assets,
        shortcut_manager=shortcut_manager,
    )
    set_app_context(ctx)
    
    # ... rest of setup ...
```

## 在页面中使用

```python
# ui/main_window.py
from core.app_context import get_app_context

class MainWindow:
    def __init__(self):
        ctx = get_app_context()
        self.project_manager = ctx.project_manager
        self.tree_manager = ctx.tree_manager
```

## 测试 fixture

```python
# tests/conftest.py
import pytest
from unittest.mock import MagicMock
from core.app_context import AppContext, set_app_context, reset_app_context


@pytest.fixture
def app_context():
    """提供可注入 mock 的 AppContext。"""
    ctx = AppContext(
        project_manager=MagicMock(),
        tree_manager=MagicMock(),
        data_file_manager=MagicMock(),
        analysis_manager=MagicMock(),
        extension_registry=MagicMock(),
        global_assets=MagicMock(),
        shortcut_manager=MagicMock(),
    )
    set_app_context(ctx)
    yield ctx
    reset_app_context()
```

## 迁移策略

1. 创建 `AppContext` 和初始化入口（不影响现有代码）
2. 对现有测试逐步添加 `app_context` fixture
3. 新模块直接使用 `get_app_context()`
4. 不强制一次性迁移所有旧 `from core.project_manager import project_manager` 引用

## 验证清单

- [ ] 应用启动时 `get_app_context()` 返回已填充的 context
- [ ] 在测试中使用 `set_app_context()` 可替换任意服务
- [ ] 所有现有测试不依赖全局 mock 即可运行
- [ ] `reset_app_context()` 后 context 为空，不残留状态

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `end`
