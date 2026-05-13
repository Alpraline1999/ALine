# Phase 29 Task 1: 扩展 API 版本声明

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 29`

## 目标

在扩展定义中增加 `aline_api_version` 字段，使扩展可声明其兼容的 ALine API 版本范围。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_definition.py` | 在四类 Extension Dataclass 中增加 `aline_api_version` 字段 |

## 实施

```python
# core/extension_definition.py

@dataclass(frozen=True)
class ProcessingExtension:
    type: str
    name: str
    handler: Callable
    # ... 现有字段 ...
    aline_api_version: str = ""   # 新增：例如 ">=0.3"
                                  # 空字符串表示"未声明"

@dataclass(frozen=True)
class AnalysisExtension:
    # ... 现有字段 ...
    aline_api_version: str = ""

@dataclass(frozen=True)
class PlotExtension:
    # ... 现有字段 ...
    aline_api_version: str = ""

@dataclass(frozen=True)
class DigitizeExtension:
    # ... 现有字段 ...
    aline_api_version: str = ""
```

### 版本范围格式

支持 PEP 440 子集：
- `"0.3"` — 精确匹配
- `">=0.3"` — 最低版本
- `">=0.3,<0.5"` — 版本范围
- `""` — 未声明（表示"无兼容保证"，不检查）

## 验证清单

- [ ] 已有扩展不声明的行为不变（`aline_api_version=""`）
- [ ] `">=0.3"` 扩展在 ALine 0.3.x 上正常
- [ ] `">=0.5"` 扩展在 ALine 0.3 上被标记

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
