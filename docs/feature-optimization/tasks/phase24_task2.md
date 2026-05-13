# Phase 24 Task 2: TypedDict 替换核心接口中的 Dict[str, Any]

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 24`

## 目标

将 `core/` 和 `processing/` 中核心接口的 `Dict[str, Any]` 替换为明确的 `TypedDict`，使 IDE 补全和类型检查能覆盖关键数据流。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `processing/data_engine.py` | 定义 `PipelineOp` TypedDict |
| `core/analysis_engine.py` | 定义 `FitResult`, `PeakResult`, `StatsResult` 等 |
| `core/extension_definition.py` | 定义 `ExtensionParams` |
| `models/schemas.py` | `AnalysisResult.summary` 用 TypedDict 细化 |
| `core/exporter.py` | 导出 payload 类型 |

## TypedDict 定义清单

### 1. Pipeline 操作类型

```python
# processing/data_engine.py
from typing import TypedDict, NotRequired, List, Dict, Any

class PipelineOp(TypedDict):
    type: str                               # "smooth" | "crop" | "fft" | ...
    params: NotRequired[Dict[str, Any]]     # 操作参数

class PairwiseComputeParams(TypedDict, total=False):
    primary_index: int
    secondary_index: int
    x_expr: str
    y_expr: str
    align_mode: str
    resample_mode: str
    n: int
```

全部 12 种 op 类型的 params:  
- SmoothParams: method (savgol/moving_average), window, poly
- CropParams: x_min, x_max (float)
- NormalizeParams: mode (minmax/zscore)
- ResampleParams: mode (spacing/align), n, step, target_line
- FFTParams: output (amplitude/phase/real/imag), detrend
- DerivativeParams: (无参数)
- IntegralParams: cumulative (bool)
- TransformParams: x_expr, y_expr
- FilterParams: cutoff, order, mode (low/high/band)
- PairwiseComputeParams: as above
- KalmanFilterParams: ...
- MultiCurveMeanParams: ...

### 2. 分析结果类型

```python
# core/analysis_engine.py
from typing import TypedDict, List, Optional

class FitResult(TypedDict):
    model: str
    params: List[float]
    param_names: List[str]
    r2: float
    fit_x: List[float]
    fit_y: List[float]
    equation: str
    covariance: Optional[List[List[float]]]

class PeakResult(TypedDict):
    peaks: List[Dict[str, float]]  # [{x, y, index}, ...]
    count: int

class StatsResult(TypedDict, total=False):
    n: int
    x_n: int
    x_min: float
    x_max: float
    x_mean: float
    x_std: float
    x_median: float
    # 同样对于 y_* ...

class CorrelationResult(TypedDict):
    pearson_r: float
    spearman_r: float
    n: int
```

### 3. 扩展参数类型

```python
# core/extension_definition.py
class ExtensionParams(TypedDict, total=False):
    lines_list: List[int]  # 运行时注入
```

### 4. 导出 Payload 类型

```python
# core/exporter.py
class SeriesExportPayload(TypedDict):
    name: str
    header: List[str]
    rows: List[List[float]]
```

## 实施步骤

1. 在每个模块中定义 TypedDict
2. 替换函数签名中的 `Dict[str, Any]` 为具体类型
3. 更新调用方使用新的类型（IDE 补全即可工作）
4. 对 `AnalysisResult.summary` 字段，保留 `Dict[str, Any]`（因为实际内容按 analysis_type 不同），但在操作函数返回值中使用具体 TypedDict

## 验证清单

- [ ] `mypy --strict processing/data_engine.py` 无 error
- [ ] `mypy --strict core/analysis_engine.py` 无 error
- [ ] IDE 中 `op["type"]` 补全为字面量字符串
- [ ] 所有测试通过

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
