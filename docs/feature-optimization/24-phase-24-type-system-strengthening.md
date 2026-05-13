# Phase 24：类型系统强化

## 目标与完成定义

**目标**：补全类型标注，引入 mypy strict 模式，消除 `Dict[str, Any]` 等类型漏洞，使 IDE 和类型检查器能有效捕获接口误用。

**完成定义**：
- `pyproject.toml` 中配置 mypy strict 模式并修复所有类型错误
- 核心接口中的 `Dict[str, Any]` 全部替换为 `TypedDict` 或具体模型
- 扩展 handler 签名使用 `Protocol` 明确定义
- 页面间通信的 dict 载荷定义显式类型

## 当前代码现状

- `pyproject.toml` 只有 ruff 配置，无 mypy
- 大量 `Dict[str, Any]` 在以下关键路径：
  - Pipeline ops：`List[Dict[str, Any]]` — 操作链定义
  - 扩展参数：`params: Dict[str, Any]` — 运行参数字典
  - AnalysisResult：`summary: Dict[str, Any]` — 结果摘要
  - FigureConfig：`style_extras: Dict[str, Any]` — 扩展样式附加数据
  - 页面间信号数据：各种隐式 dict 格式
- 扩展 handler 签名无类型约束（鸭子类型传递）

## 优化方案

### 1. 配置 mypy strict

```toml
# pyproject.toml
[tool.mypy]
strict = true
python_version = "3.11"
ignore_missing_imports = true  # PySide6 等非 typed 包
warn_unused_ignores = true
```

逐步修复：
- 先对 core/ 启用 strict
- 再对 processing/、digitize/、ai/
- 最后对 ui/（最困难，PySide6 类型不完整）

### 2. 用 TypedDict 替换 Dict[str, Any]

Pipeline op 类型：
```python
from typing import TypedDict, NotRequired

class PipelineOp(TypedDict):
    type: str
    params: NotRequired[Dict[str, Any]]  # params 本身仍灵活，但外层结构确定
```

扩展参数类型（按扩展分类）：
```python
class ProcessingParams(TypedDict):
    lines_list: NotRequired[List[int]]
    # 扩展特定字段由具体扩展定义
```

分析结果摘要：
```python
class FitResult(TypedDict):
    model: str
    params: List[float]
    param_names: List[str]
    r2: float
    fit_x: List[float]
    fit_y: List[float]
    equation: str
    covariance: Optional[List[List[float]]]
```

### 3. 扩展 handler Protocol

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class ProcessingHandler(Protocol):
    def __call__(self, lines: List[List[Tuple[float, float]]], params: Dict[str, Any]) -> List[Tuple[float, float]]: ...

@runtime_checkable
class AnalysisHandler(Protocol):
    def __call__(self, lines: List[List[Tuple[float, float]]], params: Dict[str, Any]) -> Dict[str, Any]: ...
```

### 4. 页面信号类型

为跨页面的 dict 通信定义显式类型，如：
```python
class TreeNodeSelectedPayload(TypedDict):
    kind: str
    node_id: str
    page: str
```

## 分步实施

1. 先配置 mypy 并修复 core/ 模块（影响面最小，收益最大）
2. 定义 TypedDict 替换核心接口
3. 为扩展系统引入 Protocol
4. 迁移 ui/ 中的类型

## 验收要点

- `mypy --strict core/` 零错误
- IDE 中对 PipelineOp、FitResult 等有完整补全
- 扩展 handler 签名变更后，类型检查器能捕获错误用法

## 边界与约束

- 不改变运行时行为，只加类型标注
- 不要求 PySide6 完全 typed（将未 typed 的包加入忽略列表）
- 扩展不一定要求全部标注类型，但核心接口必须覆盖
