# Phase 24 Task 3: 扩展 handler 签名引入 Protocol

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 24`

## 目标

为扩展系统的四类 handler 签名引入 `Protocol` 类型，使类型检查器能验证扩展 handler 是否满足签名约束。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_definition.py` | 定义 `ProcessingHandler`、`AnalysisHandler` 等 Protocol |
| `core/extension_validator.py` | 使用 `isinstance(handler, ProcessingHandler)` 校验 |
| 各扩展 `.py` 文件 | handler 函数自动满足 Protocol（结构子类型） |

## Protocol 定义

```python
# core/extension_definition.py
from typing import Protocol, runtime_checkable, List, Tuple, Dict, Any

# 曲线点类型
Point = Tuple[float, float]
Line = List[Point]  # [[x1,y1], [x2,y2], ...]

@runtime_checkable
class ProcessingHandler(Protocol):
    """处理扩展 handler 签名: (lines, params) -> line"""
    def __call__(self, lines: List[Line], params: Dict[str, Any]) -> Line: ...

@runtime_checkable
class AnalysisHandler(Protocol):
    """分析扩展 handler 签名: (lines, params) -> dict"""
    def __call__(self, lines: List[Line], params: Dict[str, Any]) -> Dict[str, Any]: ...

@runtime_checkable
class PlotHandler(Protocol):
    """绘图扩展 handler 签名: (plot_context, params) -> None"""
    def __call__(self, plot_context: "PlotExtensionContext", params: Dict[str, Any]) -> None: ...

@runtime_checkable
class DigitizeHandler(Protocol):
    """数字化扩展 handler 签名: (figure, params) -> line"""
    def __call__(self, figure: Any, params: Dict[str, Any]) -> Line: ...
```

## 在 ExtensionDefinition 中使用

```python
@dataclass(frozen=True)
class ProcessingExtension:
    type: str
    name: str
    handler: ProcessingHandler  # ← 不再是 Callable 而是 Protocol
    ...
```

## 在 Validator 中使用

```python
# core/extension_validator.py
from core.extension_definition import ProcessingHandler, AnalysisHandler, ...

@staticmethod
def validate_extension(ext) -> List[str]:
    errors = []
    handler = getattr(ext, "handler", None)
    if handler is None:
        errors.append("handler 不可调用")
        return errors
    
    # 类型检查（仅当有 handler 时做额外校验）
    if isinstance(ext, ProcessingExtension) and isinstance(handler, ProcessingHandler):
        pass  # 类型匹配
    elif isinstance(ext, AnalysisExtension) and isinstance(handler, AnalysisHandler):
        pass
    # 注意: @runtime_checkable 对 Callable Protocol 有局限，
    # 仅检查 __call__ 存在性，不检查参数签名。
    # 这里作为文档性约束，同时留扩展接口供 future static analysis
```

## 验证清单

- [ ] 所有内置扩展的 handler 被类型检查器接受
- [ ] `isinstance(handler, ProcessingHandler)` 对合法 handler 返回 True
- [ ] `isinstance(lambda l, p: l[0], ProcessingHandler)` 返回 True（满足结构）
- [ ] 测试通过

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
