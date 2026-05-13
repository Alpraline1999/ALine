# Phase 26：全局单例治理

## 目标与完成定义

**目标**：消除模块级全局单例对测试隔离和模块耦合的负面影响，引入显式依赖管理机制。

**完成定义**：
- 引入 `AppContext` 或等效的显式依赖容器
- 核心服务（`project_manager`、`extension_registry`、`global_assets`、`shortcut_manager`）通过容器管理
- 测试支持独立 context，可 mock/替换任意核心服务
- 现有页面和模块代码无需大规模重写即可接入

## 当前代码现状

全局单例清单：

| 单例 | 模块 | 使用方 |
|---|---|---|
| `project_manager` | `core/project_manager.py` | 几乎所有页面和 core 模块 |
| `extension_registry` | `core/extension_api.py` | 页面、data_engine、analysis_engine |
| `global_assets` | `core/global_assets.py` | project_tree、settings_page 等 |
| `shortcut_manager` | `core/shortcut_manager.py` | main_window、settings_page |

问题：
- 测试之间状态共享，无法并行
- 依赖关系隐式，无显式声明
- 无法在单测中替换为 mock 实例

## 优化方案

### 1. 引入 AppContext

```python
# core/app_context.py
from dataclasses import dataclass

@dataclass
class AppContext:
    project_manager: "ProjectManager"
    extension_registry: "ExtensionRegistry"
    global_assets: "GlobalAssetManager"
    shortcut_manager: "ShortcutManager"
```

### 2. 创建全局 context 实例

```python
# core/app_context.py
from core.project_manager import ProjectManager
from core.extension_api import extension_registry  # 将在 Phase 23 拆分后调整
from core.global_assets import global_assets
from core.shortcut_manager import shortcut_manager

_app_context: Optional[AppContext] = None

def get_app_context() -> AppContext:
    global _app_context
    if _app_context is None:
        _app_context = AppContext(
            project_manager=ProjectManager(),
            extension_registry=extension_registry,
            global_assets=global_assets,
            shortcut_manager=shortcut_manager,
        )
    return _app_context

def set_app_context(ctx: AppContext) -> None:
    """测试用：替换全局 context"""
    global _app_context
    _app_context = ctx
```

### 3. 逐步迁移引用

当前：`from core.project_manager import project_manager`
改为：`from core.app_context import get_app_context; ctx = get_app_context(); ctx.project_manager`

或为减少改动量，在 `core/__init__.py` 中注入：
```python
# core/__init__.py
from core.app_context import get_app_context
```

### 4. 测试支持

```python
# tests/conftest.py
@pytest.fixture
def test_context():
    ctx = AppContext(
        project_manager=MagicMock(),
        extension_registry=MagicMock(),
        ...
    )
    set_app_context(ctx)
    yield ctx
    set_app_context(None)  # 清理
```

## 迁移策略

1. 创建 `AppContext` 和 `get_app_context()`
2. 不立即替换所有 import，先让 `set_app_context()` 可用
3. 对难测试的模块逐个迁移引用方式
4. 补充使用 test context 的集成测试

## 验收要点

- 可使用 `set_app_context()` 在测试中替换任意核心服务
- 现有测试和功能不受影响
- 逐步迁移后，不再需要 `from core.project_manager import project_manager` 这种模块级绑定

## 边界与约束

- 不强制立即迁移所有引用方式（兼容期存在）
- 不引入第三方 DI 框架（保持轻量）
- context 对外不可变（创建后不替换内部服务实例）
