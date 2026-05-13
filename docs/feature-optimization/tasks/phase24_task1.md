# Phase 24 Task 1: 启用 mypy strict 并修复 core/ 类型错误

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 24`

## 目标

在 `pyproject.toml` 中配置 mypy strict 模式，修复 `core/` 目录下所有类型错误，使类型检查器能有效捕获接口误用。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `pyproject.toml` | 添加 `[tool.mypy]` section |
| `core/**/*.py` | 逐个修复类型错误 |
| 新增 `py.typed` 标记（可选） | 无 |

## 实施步骤

### Step 1: 配置 mypy

```toml
# pyproject.toml
[tool.mypy]
strict = true
python_version = "3.11"

# PySide6 和部分第三方包未提供类型标注
ignore_missing_imports = true

# 禁止未使用的 type: ignore
warn_unused_ignores = true

# 允许未类型化的 def（逐步修复）
allow_untyped_defs = false
allow_untyped_decorators = true  # Qt slot 装饰器无法标注
```

### Step 2: 运行 mypy 并统计错误

```bash
mypy core/ --show-error-codes
```

预期错误类型分布：
1. **缺失返回类型** (return-type)：`def method() -> None` 未写
2. **缺失参数类型** (type-arg)：参数未标注
3. **Any 泄漏** (no-any-return, no-any-union)
4. **无效的 super() 调用**
5. **赋值类型不兼容** (assignment)

### Step 3: 按模块修复

优先级顺序：

**第一组**（无外部依赖，修复收益最大）：
- `models/schemas.py` — 数据模型，错误最少
- `core/project_serializer.py` — 纯逻辑，无 UI 依赖
- `core/tree_manager.py` — 纯逻辑

**第二组**（有少量依赖）：
- `core/extension_definition.py` — 类型系统核心
- `core/extension_registry.py` — 注册表
- `core/extension_validator.py` — 校验器
- `core/extension_loader.py` — 加载器

**第三组**（混合依赖）：
- `core/analysis_engine.py` — 依赖 numpy/scipy
- `core/exporter.py` — IO 操作
- `core/data_operations.py` — IO 操作

**第四组**（依赖最多）：
- `core/global_assets.py`
- `core/project_manager.py`
- `core/ai_client.py`
- `core/shortcut_manager.py`

### Step 4: 典型修复模式

**缺失 → None**：
```python
# 修复前
def save(self, project, path):
    ...

# 修复后
def save(self, project: Project, path: str) -> None:
    ...
```

**缺失参数类型**：
```python
# 修复前
def find_series(self, series_id):
    ...

# 修复后
def find_series(self, series_id: str) -> Optional[DataSeries]:
    ...
```

**Any 收缩**：
```python
# 修复前
def get_state(self) -> dict:
    return {"name": self.name, "count": len(self.items)}

# 修复后
def get_state(self) -> Dict[str, Any]:
    return {"name": self.name, "count": len(self.items)}
```

## 验收要点

- [ ] `mypy --strict core/` 返回 0 错误
- [ ] `mypy --strict core/ --show-error-codes` 无任何 error code 输出
- [ ] 所有类型修改仅影响标注，不影响运行时行为
- [ ] 全量 `pytest` 通过

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
