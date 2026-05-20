# ALine 扩展开发指南

ALine 扩展是一个普通 Python 文件。应用启动或重载扩展时，会递归扫描 `extensions/` 目录，调用每个文件中的 `register_extensions(registry)`，并把扩展注册到处理、分析、绘图或数字化四类入口中。

本文档描述当前正式接口。新增扩展只允许使用这里写明的签名、曲线结构和输出结构。

---

## 目录

- [快速开始](#快速开始)
- [扩展目录与加载规则](#扩展目录与加载规则)
- [四类扩展总览](#四类扩展总览)
- [曲线协议](#曲线协议)
- [曲线工具函数](#曲线工具函数)
- [Extension 数据类字段总表](#extension-数据类字段总表)
- [参数字段 ExtensionConfigField](#参数字段-extensionconfigfield)
- [PlotExtensionContext — 绘图扩展上下文](#plotextensioncontext--绘图扩展上下文)
- [处理扩展](#处理扩展)
- [分析扩展](#分析扩展)
- [绘图扩展](#绘图扩展)
- [数字化扩展](#数字化扩展)
- [四类扩展完整示例](#四类扩展完整示例)
- [发布层级与内置扩展策略](#发布层级与内置扩展策略)
- [原子性要求](#原子性要求)
- [发布检查表](#发布检查表)

---

## 快速开始

最小处理扩展：

```python
from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import line_from_xy, line_xy, primary_line


def offset_handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    offset = float(params.get("offset", 0.0) or 0.0)
    return line_from_xy(xs, [value + offset for value in ys])


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="offset_demo",
            name="偏移示例",
            handler=offset_handler,
            description="将输入曲线整体上移或下移。",
            version="1.0.0",
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(
                    key="offset",
                    label="Y 偏移",
                    field_type="number",
                    default=0.0,
                    step=0.1,
                )
            ],
        )
    )
```

保存为 `extensions/processing/offset_demo.py` 后，点击应用中的"重载扩展"即可加载。

---

## 扩展目录与加载规则

推荐目录结构：

```text
extensions/
  processing/   # 处理扩展
  analysis/     # 分析扩展
  plot/         # 绘图扩展
  digitize/     # 数字化扩展
```

加载规则：

- 文件名使用 `snake_case.py`。
- 以下划线 `_` 开头的文件不会自动加载。
- 每个可加载文件**必须**提供顶层函数 `register_extensions(registry)`。
- `register_extensions` 只负责注册扩展，不做耗时计算、网络访问或页面状态读取。
- 内置扩展声明 `source_kind="builtin"`；外部目录扩展声明 `source_kind="external"`。
- `extension_tools.py` 和 `analysis_tools.py` 不会被作为扩展加载（它们是工具模块）。

---

## 四类扩展总览

| 类型       | 注册类                | Handler 签名                          | 输出     | 用途                               |
| ---------- | --------------------- | ------------------------------------- | -------- | ---------------------------------- |
| 处理扩展   | `ProcessingExtension` | `(lines: List[Line], params) -> Line` | `line`   | 生成一条新的曲线                   |
| 分析扩展   | `AnalysisExtension`   | `(lines: List[Line], params) -> dict` | `dict`   | 生成摘要、表格、文本和结果曲线     |
| 绘图扩展   | `PlotExtension`       | `(plot_context, params) -> None`      | `None`   | 在当前 matplotlib 图表上绘制或标注 |
| 数字化扩展 | `DigitizeExtension`   | `(figure, params) -> Line`            | `line`   | 从图像资源提取曲线点               |

`params` 是页面根据 `config_fields` 和运行时上下文生成的参数字典。扩展**不得**把页面私有对象作为 handler 参数。

handler 签名对应的 Protocol 类型定义在 `core.extension_definition`：

```python
# 处理扩展
class ProcessingHandler(Protocol):
    def __call__(self, lines: List[Line], params: Dict[str, Any]) -> Line: ...

# 分析扩展
class AnalysisHandler(Protocol):
    def __call__(self, lines: List[Line], params: Dict[str, Any]) -> Dict[str, Any]: ...

# 绘图扩展
class PlotHandler(Protocol):
    def __call__(self, plot_context: "PlotExtensionContext", params: Dict[str, Any]) -> None: ...

# 数字化扩展
class DigitizeHandler(Protocol):
    def __call__(self, figure: Any, params: Dict[str, Any]) -> Line: ...
```

---

## 曲线协议

正式曲线结构是 point-list：

```python
line = [[0.0, 1.0], [1.0, 2.0], [2.0, 4.0]]   # Line = List[Point]
lines = [line, ...]                               # Lines = List[Line]
```

规则：

- 每个点必须是 `[x, y]`，长度固定为 2。
- `x` 和 `y` 必须能转换为有限浮点数。
- 空曲线使用 `[]`。
- 不使用曲线 dict 作为扩展输入。
- 不使用独立 `xs` / `ys` 作为扩展输入或输出。
- 不使用 `[x_list, y_list]` 作为 line。

---

## 曲线选择与引用机制

扩展开发中有五个容易混淆的 `lines`/`line`/`lines_list` 相关概念。理解它们的区别是正确编写扩展的关键。

### 概念总览

| 符号 | 出现位置 | 类型 | 含义 |
|------|----------|------|------|
| `lines` | handler 参数（processing/analysis） | `List[Line]` | 运行时传入的**实际的曲线数据**，由用户所选曲线列表转换而来 |
| `lines_number` | Extension 声明字段 | `Tuple[int,int]` | 扩展需要的曲线数量范围声明，**控制 UI 是否显示曲线选择控件** |
| `lines_list` | 运行时注入 `params` 的键 | `List[int]` | 用户在曲线选择控件中**勾选的曲线下标**（从 1 开始），由运行时自动注入 |
| `line` | `ExtensionConfigField.field_type` | 控件类型 | 参数表单中让用户**单选一条曲线**的控件，值写入 `params`（如 `params["target_curve"] = 2`）。与 `lines_list` 的区别见[绘图扩展](#获取用户选中的某条曲线) |
| `lines` | 分析扩展 return dict 的键 | `List[dict]` | 分析结果中**命名的结果曲线列表**，每条有 `line_name` 和 `line` 数据 |

### 1. `lines` — handler 的输入曲线参数

处理扩展和分析扩展的 handler 接收 `lines` 作为第一个参数。

`lines` 是一个 `List[Line]`，即多条 point-list 曲线的列表。每条曲线是 `[[x0, y0], [x1, y1], ...]`。

```python
def handler(lines, params):
    # lines = [
    #     [[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]],   # 曲线 1
    #     [[0.0, 0.5], [1.0, 1.0], [2.0, 1.5]],   # 曲线 2
    # ]
    first = primary_line(lines)     # 取第一条
    xs, ys = line_xy(first)         # 拆分为 x/y
    ...
```

`lines` 中的曲线顺序与用户在 UI 中选择的顺序一致（由 `lines_list` 决定）。如果 `lines_number=(1, 1)`，则 `lines` 只有一条曲线；如果 `lines_number=(2, 2)`，则有两条。

绘图扩展不直接接收 `lines`，而是通过 `plot_context.visible_series` 获取曲线数据，再用 `series_payloads_to_lines()` 转换。

### 2. `lines_number` — 声明需要的曲线数量

`lines_number` 在扩展注册时声明，**控制 UI 是否显示曲线选择控件**以及用户必须选择多少条曲线。

```python
ProcessingExtension(
    ...
    lines_number=(1, 1),   # 需要 1 条曲线 → UI 自动勾选 1 条
)
```

| 值 | 含义 | UI 行为 |
|----|------|---------|
| 不设置 / `None` | 不需要曲线输入 | 不显示曲线选择控件 |
| `(1, 1)` | 需要 1 条曲线 | 自动选择 1 条，用户可更换 |
| `(2, 2)` | 需要 2 条曲线 | 用户必须勾选恰好 2 条 |
| `(2, -1)` | 需要 2 条及以上 | 用户至少勾选 2 条，上不封顶 |
| `(0, -1)` | 零条到任意条 | 可选任意数量的曲线 |

`lines_number` 属于扩展声明字段，**不需要也不允许**在 `config_fields` 中重复声明。

#### 处理扩展示例：重采样

```python
# resample.py — lines_number=(1, 1)
# handler 接收 1 条输入曲线，但 align 模式需要访问完整的曲线池
def resample_handler(lines, params):
    return _resample_xy(primary_line(lines), params, lines=lines)
```

#### 绘图扩展示例：双曲线差异带

```python
# plot_dual_curve_band.py — lines_number=(2, 2)
# handler 通过 plot_context 访问曲线数据
def draw_dual_curve_band(plot_context, params):
    candidates = _context_lines(plot_context, params)[:2]
    aligned_lines, warnings = align_lines_to_common_x(candidates, params)
    ...
```

### 3. `lines_list` — 运行时注入的曲线选择

当 `lines_number` 不为 `None` 时，运行时会向 `params` 注入一个隐式参数 `lines_list`。它的值是一个整数列表，表示用户在曲线选择控件中**勾选的曲线下标**（从 1 开始）。

```
用户勾选了曲线池中的第 1 条和第 3 条 → params["lines_list"] = [1, 3]
```

扩展可以通过读取 `params["lines_list"]` 来感知用户选了什么：

```python
def handler(lines, params):
    selected = params.get("lines_list", [])
    # selected = [1, 3] 表示用户勾选了第 1 条和第 3 条
    # lines 中的顺序与 selected 一致
```

绘图扩展使用 `normalize_extension_lines_list()` 解析这个参数：

```python
from core.extension_api import normalize_extension_lines_list

def _context_lines(plot_context, params):
    base_series = list(plot_context.visible_series or plot_context.plotted_series or [])
    requested = normalize_extension_lines_list(params.get("lines_list")) if "lines_list" in params else []
    if requested:
        # 只返回用户选中的曲线
        return series_payloads_to_lines([base_series[index - 1] for index in requested])
    # 未选中时默认使用选中曲线 + 其余全部
    ...
```

**`lines_list` 不需要也不允许在 `config_fields` 中注册。** 运行时根据 `lines_number` 自动生成 UI 控件和注入参数。

### 4. `line` — 参数字段类型（单选一条曲线）

`line` 是一种 `ExtensionConfigField` 的 `field_type` 值。它生成的 UI 控件让用户**从当前曲线池中单选一条曲线**，并将选中的曲线下标（1-based）写入 `params`。

#### 用途：让用户指定"对齐到哪条曲线"

典型场景是重采样扩展的"对齐到某条参考曲线"：

```python
# resample.py — 用户通过此字段选择对齐目标
ExtensionConfigField(
    key="target_line",       # → params["target_line"]
    label="对齐曲线",
    field_type="line",       # 显示为下拉列表，列出所有可选曲线
    default=1,               # 默认选中第 1 条
    description="从当前数据集中选择 1 条曲线作为对齐参考。",
)

# handler 中读取
def _resample_xy(line, params, *, lines):
    target_idx = int(params.get("target_line", 1) or 1)
    target_x, _target_y = line_xy(pool[target_idx - 1])
    resample_to_grid(x_sorted, y_sorted, target_x)  # 对齐到目标曲线的 X 网格
```

**`line` 与 `lines_number` 的区别**：
- `lines_number` 声明扩展**处理**多少条曲线 → 控制 handler 的 `lines` 参数长度
- `field_type="line"` 让用户**引用**一条曲线作为参数 → 值存在 `params["field_name"]` 中

**`line` 与 `lines_list` 的区别**：
- `lines_list` 是运行时自动注入的，值为用户勾选的**全部曲线下标**
- `field_type="line"` 是扩展显式声明的，值为用户单选的一条曲线下标

### 5. `lines` — 分析扩展返回的已命名结果曲线

分析扩展的 return dict 中包含 `lines` 键，用于传递**已命名的结果曲线**：

```python
return {
    "lines": [
        {"line_name": "拟合曲线", "line": fit_line},           # 命名的结果曲线
        {"line_name": "+1σ", "line": line_from_xy(xs, ys_plus)},
    ],
    "_plot_series": [
        {"name": "拟合曲线", "line": "拟合曲线", "color": "#D13438"},  # 引用 lines 中的名称
        {"name": "+1σ", "line": "+1σ", "color": "#888888"},
    ],
}
```

每条曲线有唯一的 `line_name`，`_plot_series` 通过 `"line"` 字段引用 `lines` 中对应的 `line_name`。**不允许**在 `_plot_series` 中直接传递 `x`/`y` 数据。

---

## 曲线工具函数

所有正式曲线工具位于 `extensions.processing.extension_tools`，通过 `core.line_tools` 转发。扩展应始终通过 `extensions.processing.extension_tools` 导入。

### 基础转换

```python
from extensions.processing.extension_tools import (
    line_from_xy,           # (xs, ys) -> Line。检查长度一致并验证坐标合法性。
    line_xy,                # (line) -> (SeriesArrayView, SeriesArrayView)。拆分为 x/y 序列。
    primary_line,           # (lines) -> Line。取第一条输入曲线，缺省返回空曲线。
    normalize_line,         # (raw) -> Line。验证并标准化为合法 point-list。
    normalize_lines,        # (lines) -> List[Line]。批量验证并标准化。
)
```

`line_from_xy(xs, ys)` 会检查两个序列长度一致，并验证所有坐标合法。**所有内置扩展和内部方法都应复用它。**

### 数据载荷转换

```python
from extensions.processing.extension_tools import (
    series_payload_to_line,     # (dict) -> Line。从 {"x": [...], "y": [...]} 字典提取曲线。
    series_payloads_to_lines,   # (List[dict]) -> List[Line]。批量提取。
)
```

### 多曲线对齐

```python
from extensions.processing.extension_tools import (
    align_lines_to_common_x,    # (lines, params) -> Tuple[List[Line], List[str]]
                                # 把多条 point-list 曲线对齐到公共 X 网格。
                                # params 支持 {"align_mode": "union" | "intersect" | "first"}
    resolve_sample_rate,        # (xs) -> float。估算 X 序列的采样间距。
)
```

### 重采样与插值

```python
from core.line_tools import (
    sorted_unique_xy,           # (xs, ys) -> (xs, ys)。排序并去重。
    estimate_sample_spacing,    # (xs) -> float。估算采样间距。
    interp_linear,              # (xs, ys, target_x) -> float。线性插值。
    resample_uniform,           # (xs, ys, num) -> (xs, ys)。均匀重采样到指定点数。
    resample_uniform_spacing,   # (xs, ys, spacing) -> (xs, ys)。按指定间距重采样。
    nearest_value,              # (xs, ys, target_x) -> float。最近邻取值。
    x_values_equal,             # (xs_a, xs_b) -> bool。检查 X 序列是否相等。
    resample_to_grid,           # (xs, ys, grid_x) -> (ys)。在网格点上插值。
    build_alignment_grid,       # (x_arrays, mode) -> ndarray。构造对齐网格。
    recommended_alignment_spacing, # (xs) -> float。推荐对齐间距。
    describe_alignment_mode,    # (mode) -> str。描述对齐模式。
)
```

### 数值辅助

```python
from extensions.processing.extension_tools import (
    BUILTIN_EXTENSION_VERSION,  # str = "1.0.0"。内置扩展推荐版本号。
    apply_window,               # (size, window_name) -> ndarray。生成窗函数数组。
                                #   window_name: "hann"(默认) / "hamming" / "blackman" / "rect"
    linear_percentile,          # (sorted_vals, percentile) -> float。线性插值百分位数。
    baseline_correction,        # (xs, ys, method) -> ndarray。基线校正。
                                #   method: "none" / "constant" / "linear"
)
```

### CurveBuffer（底层容器）

```python
from core.curve_data import (
    CurveBuffer,        # (x: ndarray, y: ndarray) 的冻结数据类。
                        # 方法: from_xy(xs, ys), from_line(raw), empty()
                        #       to_line() -> Line, to_views() -> (SeriesArrayView, SeriesArrayView)
                        #       to_series_payload() -> dict
    SeriesArrayView,    # numpy 数组的只读 Sequence 视图。
)
```

曲线工具关系图：

```
参数 dict ({"x": [...], "y": [...]})
    │
    ▼
series_payload_to_line ───▶ Line (point-list)
    │                          │
    │                      line_xy
    │                          │
    └─── line_from_xy ◀────────┘
```

---

## Extension 数据类字段总表

四个扩展类共享以下基础字段（加 `*` 为某类特有）：

| 字段 | 类型 | 默认值 | 适用类型 | 说明 |
|------|------|--------|----------|------|
| `type` | `str` | (必填) | 全部 | 全局唯一标识。建议用 `snake_case`。 |
| `name` | `str` | (必填) | 全部 | 界面显示名称。 |
| `handler` | Handler | (必填) | 全部 | 处理函数。签名见四类扩展总览。 |
| `description` | `str` | `""` | 全部 | 用途说明。显示在扩展选择界面。 |
| `version` | `str` | `"1.0.0"` | 全部 | `x.y.z` 格式。 |
| `config_fields` | `List[ExtensionConfigField]` | `[]` | 全部 | 参数表单字段定义。 |
| `default_options` | `Dict[str, Any]` | `{}` | 全部 | 旧式默认值（已弃用，优先使用 `config_fields` 的 default）。 |
| `lines_number` | `Optional[Tuple[int,int]]` | `None` | processing, analysis, plot | 需要的输入曲线数量。 |
| `settings` | `bool` | `False` | 全部 | 是否生成可保存设置的参数表单。 |
| `source_kind` | `str` | `"builtin"` | 全部 | `"base"` / `"builtin"` / `"external"`。 |
| `tool_tier` | `str` | `"tool"` | 全部 | `"tool"`（默认显示）或 `"experimental"`（默认隐藏）。 |
| `hidden` | `bool` | `False` | 全部 | `True` 时不在扩展选择列表中显示。 |
| `capabilities` | `set[str]` | `set()` | 全部 | 扩展能力标签，预留。 |
| `api_version` | `str` | `""` | 全部 | 扩展自身 API 版本。 |
| `aline_api_version` | `str` | `""` | 全部 | 所依赖的 ALine API 版本。 |
| `depends_on` | `list[str]` | `[]` | 全部 | 依赖的其他扩展 type 列表。 |
| `supports_progress` | `bool` | `False` | 全部 | 是否支持进度回调。 |
| `supports_cancel` | `bool` | `False` | 全部 | 是否支持取消操作。 |
| `min_app_version` | `str` | `""` | 全部 | 最低 ALine 应用版本。 |
| `tested_app_range` | `list[str]` | `[]` | 全部 | 测试过的应用版本范围。 |
| `phases` * | `Tuple[str, ...]` | `("before_plot","after_plot")` | plot | 绘图阶段。可选 `"before_plot"` / `"after_plot"`。 |
| `report_placeholders` * | `List[Dict]` | `[]` | analysis | 报告模板占位符。 |
| `style_authority` * | `str` | `"advisory"` | plot | `"advisory"`（建议值）或 `"authoritative"`（强制值）。 |
| `authoritative_fields` * | `set[str]` | `set()` | plot | 当 `style_authority="authoritative"` 时，标记强制覆盖字段。 |
| `post_render_mutation` * | `bool` | `False` | plot | 是否在渲染后修改图表（要求渲染完成后再调用 handler）。 |

`lines_number` 规则：

| 值 | 含义 | UI 行为 |
|----|------|---------|
| 不设置 / `None` | 不需要曲线输入 | 不显示曲线选择控件 |
| `(1, 1)` | 需要一条曲线 | 自动选择 1 条，用户可更换 |
| `(2, 2)` | 需要两条曲线 | 用户必须勾选恰好 2 条 |
| `(2, -1)` | 需要两条及以上 | 用户至少勾选 2 条，上不封顶 |
| `(0, -1)` | 零条到任意条 | 可选任意数量的曲线 |

`lines_number` 仅控制 handler 的 `lines` 输入参数。详细信息见[曲线选择与引用机制](#3-lines_list--运行时注入的曲线选择)。

---

## 参数字段 ExtensionConfigField

```python
from core.extension_api import ExtensionConfigField

ExtensionConfigField(
    key="field_name",       # (必填) 参数字段标识，会作为 params dict 的 key
    label="字段名",         # 界面显示标签，默认空
    description="说明",     # 字段说明，显示为 tooltip
    field_type="string",    # 控件类型，见下表
    required=False,         # 是否必填
    default=None,           # 默认值
    choices=(),             # selective 类型时可用选项，tuple[str, ...]
    min_value=None,         # integer / number / limited 的最小值
    max_value=None,         # integer / number / limited 的最大值
    step=None,              # integer / number 的步长
    placeholder="",         # string / figure 的占位提示文本
    extra={},               # 额外元数据 dict（运行时使用，扩展无需关注）
)
```

### field_type 控件映射表

| `field_type` | 控件语义       | 常用字段                            |
| ------------ | -------------- | ----------------------------------- |
| `string`     | 单行文本       | `default`、`placeholder`            |
| `integer`    | 整数输入       | `default`、`min_value`、`max_value`、`step` |
| `number`     | 浮点输入       | `default`、`min_value`、`max_value`、`step` |
| `boolean`    | 开关           | `default=True/False`                |
| `selective`  | 下拉选择       | `choices=(...)`、`default`          |
| `limited`    | 范围滑块       | `min_value`、`max_value`、`step`、`default` |
| `color`      | 颜色选择器     | `default="#0078D4"`                 |
| `line`       | 单条曲线引用   | `default=1`（下标从 1 开始）。用于让用户指定"对齐到哪条曲线"等场景，见[曲线选择与引用机制](#4-line--参数字段类型单选一条曲线) |
| `figure`     | 文件路径选择   | `placeholder`                       |
| `pickcolor`  | 图像取色       | `default={"r": 0, "g": 120, "b": 212}` |
| `shot`       | 图像区域截图   | `default=None`                      |

```python
ExtensionConfigField(
    key="sampled_color",
    label="采样颜色",
    description="从当前图像拾取颜色。",
    field_type="pickcolor",
    default={"r": 0, "g": 120, "b": 212},
)
```

**不允许通过 `config_fields` 注册的字段**：`lines`、`lines_list`、`lines_number`。这些由运行时根据 `lines_number` 声明自动注入。详情见[曲线选择与引用机制](#曲线选择与引用机制)。

---

## PlotExtensionContext — 绘图扩展上下文

绘图扩展的 handler 接收 `plot_context: PlotExtensionContext` 作为第一个参数。

### 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `figure` | `matplotlib.figure.Figure` | 当前图表对象。 |
| `canvas` | `Any` | 当前画布对象。 |
| `axis` | `matplotlib.axes.Axes` | 当前活动坐标轴。 |
| `axes` | `List[Any]` | 图表中所有坐标轴列表。 |
| `visible_series` | `List[Dict]` | 可见曲线列表。每条含 `x`/`y`/`style`/`name`。 |
| `plotted_series` | `List[Dict]` | 已绘制的曲线列表。 |
| `selected_series` | `Optional[Dict]` | 当前选中的单条曲线。 |
| `selected_series_identity` | `Optional[str]` | 选中曲线的身份标识。 |
| `figure_state` | `Dict[str, Any]` | 当前图表状态。 |
| `plot_style_extras` | `Dict[str, Any]` | 绘图样式额外参数。 |
| `theme_colors` | `Dict[str, Any]` | 当前主题颜色。 |
| `phase` | `str` | 调用阶段：`"before_plot"` 或 `"after_plot"`。 |
| `skip_default_plot` | `bool` | 是否跳过默认绘图。 |
| `skip_default_formatting` | `bool` | 是否跳过默认格式化。 |
| `skip_default_layout` | `bool` | 是否跳过默认布局。 |

### 方法

```python
# 刷新 axes 列表（页面可能动态增删子图）
plot_context.refresh_axes()  # -> List[Any]

# 设置当前活动坐标轴
plot_context.set_active_axis(axis)  # -> axis

# 向图表状态打补丁
plot_context.patch_figure_state({"x_label": "时间 (s)"})

# 向绘图样式打补丁
plot_context.patch_plot_style({"grid_alpha": 0.5})

# 向指定曲线的样式打补丁
plot_context.patch_curve_style(curve_identity, {"linewidth": 2.0})

# 向选中曲线的样式打补丁
plot_context.patch_selected_curve_style({"color": "#FF0000"})

# 清除所有运行时补丁
plot_context.clear_style_patches()
```

### PatchAuthority 枚举

```python
from core.extension_types import PatchAuthority

PatchAuthority.ADVISORY        # 建议值。不覆盖用户手动修改的同字段。
PatchAuthority.AUTHORITATIVE   # 强制值。可覆盖用户手动修改。
```

控制 `PlotExtension` 的 `style_authority` 与 `authoritative_fields` 字段语义。

---

## 处理扩展

处理扩展接收多条 point-list 曲线，返回一条 point-list 曲线。

```python
def handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    return line_from_xy(xs, ys)
```

规则：

- 使用 `lines_number` 声明需要的曲线数量。
- 多曲线顺序由 `params["lines_list"]` 和运行时传入顺序决定。
- 返回值必须是一条 `line`（`List[Point]`）。
- 不返回 dict、warnings、多条曲线列表或页面操作指令。

完整示例见下文。

---

## 分析扩展

分析扩展接收多条 point-list 曲线，返回 dict。

### 返回 dict 的键

| 键 | 格式 | 必填 | 说明 |
|---|------|------|------|
| `analysis_type` | `str` | **是** | 结果类型标识。 |
| `summary_items` | `List[tuple[str, Any]]` | 推荐 | 摘要区，`[("项目", 值), ...]`。 |
| `tables` | `List[dict]` | 可选 | 表格区。每条含 `title` / `headers` / `rows`。 |
| `texts` | `List[str]` | 可选 | 自由文本区。 |
| `lines` | `List[dict]` | 可选 | 结果曲线，`[{"line_name": "名称", "line": line}]`。 |
| `_plot_series` | `List[dict]` | 可选 | 绘图系列，每项 `"line"` 引用 `lines` 中的 `line_name`。 |

规则：

- `_plot_series[].line` 必须引用顶层 `lines` 中已声明的 `line_name`。
- **不再**使用 `_plot_series[].x / y` 传递结果曲线。

### 报告占位符

```python
report_placeholders=[
    {
        "token": "{{dominant_frequency}}",
        "label": "主频",
        "description": "频谱分析得到的主频。",
    }
]
```

完整示例见下文。

---

## 绘图扩展

绘图扩展接收 `plot_context` 与参数字典，直接操作当前 matplotlib figure / axis，返回 `None`。

### 曲线数据获取

绘图扩展**不直接接收 `lines` 参数**。曲线数据通过 `plot_context` 获取，必须经过 `series_payloads_to_lines()` → `line_xy()` 标准链路转换：

```python
# 1. 从 plot_context 获取可见曲线列表（List[dict]）
base_series = list(plot_context.visible_series or plot_context.plotted_series or [])

# 2. 将 dict 载荷转换为标准 point-list Line（关键！不可省略）
lines = series_payloads_to_lines([base_series[idx]])

# 3. 将 Line 拆分为 x/y 数值序列
x_values, y_values = line_xy(lines[0])

# 4. 使用 x/y 数据绘图
axis.plot(list(x_values), list(y_values))
```

**不要直接从 `visible_series` 的 dict 中取 `"x"`/`"y"`**——数据格式可能是 `SeriesArrayView`，必须通过标准链路转换。

### 获取"用户选中的某条曲线"

绘图扩展中让用户指定"对哪条曲线操作"有两种方式：

#### 方式 A：通过 `field_type="line"` 参数（推荐）

在 `config_fields` 中声明 `field_type="line"` 的字段，UI 会生成一个曲线下拉选择器，用户选中的曲线下标（1-based）存入 `params`：

```python
ExtensionConfigField(
    key="target_curve",       # → params["target_curve"]
    label="目标曲线",
    field_type="line",        # 下拉列表，列出所有可选曲线
    default=1,                # 默认选中第 1 条
)

# handler 中读取
target_idx = int(params.get("target_curve", 1) or 1) - 1  # 转 0-based
target_entry = base_series[target_idx]
lines = series_payloads_to_lines([target_entry])
```

这种方式显式可控，扩展无需声明 `lines_number`。参考 `resample.py` 的 `target_line` 字段。

#### 方式 B：通过 `lines_number` + `lines_list` 自动注入

声明 `lines_number` 后，运行时会自动注入 `params["lines_list"]`（用户勾选的曲线下标列表）。适用于"用户勾选 N 条曲线统一处理"的场景：

```python
lines_number=(2, 2),  # 需要 2 条曲线

# handler 中读取
requested = params.get("lines_list", [])  # 如 [1, 3]
```

注意：`lines_list` 由 `resolved_options` 经表单保存后传入 handler。如果扩展不需要配置表单（`settings=False`），则该值可能为空。

#### 两种方式的区别

| | `field_type="line"` | `lines_number` + `lines_list` |
|---|---|---|
| UI 控件 | 扩展参数面板中的下拉选择器 | 扩展列表上方的通用曲线勾选框 |
| 适用场景 | 需要用户**单选**一条参考曲线 | 需要用户**选择 N 条**曲线作为输入 |
| 典型例子 | `resample.py` 的"对齐曲线" | `plot_dual_curve_band.py` 的双曲线差异带 |
| 值传递 | 通过 `config_fields` 显式声明 | 由运行时根据 `lines_number` 隐式注入 |

### 规则

- handler 始终是 `(plot_context, params)`。
- `phases` 控制调用阶段：`"before_plot"`（默认绘图之前）或 `"after_plot"`（默认绘图之后）。
- 扩展只绘制或修改当前图元，不接管页面绘图流程。
- 曲线数据必须经由 `series_payloads_to_lines()` → `line_xy()` 标准链路转换，不可直接从 dict 中取 `"x"`/`"y"`。
- 需要修改图表状态时，使用 `patch_figure_state()` / `patch_plot_style()` / `patch_curve_style()`。

完整示例见下文。

---

## 数字化扩展

数字化扩展接收当前图像资源和参数，返回 point-list line。

```python
def handler(figure, params):
    del figure
    count = int(params.get("point_count", 3) or 3)
    xs = list(range(count))
    ys = [value * value for value in xs]
    return line_from_xy(xs, ys)
```

运行时会自动把蒙版参数注入 `params`：

- `mask_polygons`：画笔蒙版多边形列表。
- `mask_include_mode`：蒙版包含或排除模式。

数字化扩展如需图像交互，使用 `pickcolor` 和 `shot` 字段声明取色与截图控件。

完整示例见下文。

---

## 四类扩展完整示例

以下四个完整示例展示了每类扩展的全部特性，包括所有参数字段类型和输出结构。这些示例既是接口契约文档，也是回归测试入口。

要使用这些示例，保存为对应目录下的 `.py` 文件后重载扩展即可。所有示例标记为 `tool_tier="experimental"`、`hidden=True`，不会干扰正常用户。

### 1. 处理扩展

保存为 `extensions/processing/interface_contract_processing.py`：

```python
from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION, line_from_xy, line_xy, primary_line


def processing_interface_contract(lines, params):
    xs, ys = line_xy(primary_line(lines))
    y_scale = float(params.get("y_scale", 1.0) or 1.0)
    y_offset = float(params.get("y_offset", 0.0) or 0.0)
    invert = bool(params.get("invert", False))
    label_prefix = str(params.get("label_prefix", "接口示例") or "接口示例")
    mode = str(params.get("mode", "scale") or "scale")
    clip_min = params.get("clip_min")
    clip_max = params.get("clip_max")
    _reference_line = params.get("reference_line")
    _preview_path = params.get("preview_path")
    _line_color = params.get("line_color")
    del label_prefix, _reference_line, _preview_path, _line_color

    result = []
    for value in ys:
        new_value = -value if invert else value
        if mode == "scale":
            new_value = new_value * y_scale + y_offset
        elif mode == "offset":
            new_value = new_value + y_offset
        elif mode == "normalize" and ys:
            y_min = min(ys)
            y_max = max(ys)
            new_value = (new_value - y_min) / (y_max - y_min or 1.0)
        if clip_min not in (None, ""):
            new_value = max(float(clip_min), new_value)
        if clip_max not in (None, ""):
            new_value = min(float(clip_max), new_value)
        result.append(new_value)
    return line_from_xy(xs, result)


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="interface_contract_processing",
            name="接口示例：处理扩展",
            handler=processing_interface_contract,
            description="展示处理扩展的强制签名 (lines, params) -> line，以及通用参数字段。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=(1, -1),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            hidden=True,
            config_fields=[
                ExtensionConfigField(key="label_prefix", label="结果名前缀", description="string 参数示例。", field_type="string", default="接口示例"),
                ExtensionConfigField(key="mode", label="处理模式", description="selective 参数示例。", field_type="selective", default="scale", choices=("scale", "offset", "normalize")),
                ExtensionConfigField(key="window", label="窗口大小", description="integer 参数示例。", field_type="integer", default=5, min_value=1),
                ExtensionConfigField(key="y_scale", label="Y 缩放", description="number 参数示例。", field_type="number", default=1.0, step=0.1),
                ExtensionConfigField(key="y_offset", label="Y 偏移", description="number 参数示例。", field_type="number", default=0.0, step=0.1),
                ExtensionConfigField(key="invert", label="反相", description="boolean 参数示例。", field_type="boolean", default=False),
                ExtensionConfigField(key="clip_min", label="最小裁剪", description="limited 参数示例。", field_type="limited", default=-10.0, min_value=-10.0, max_value=10.0, step=0.1),
                ExtensionConfigField(key="clip_max", label="最大裁剪", description="limited 参数示例。", field_type="limited", default=10.0, min_value=-10.0, max_value=10.0, step=0.1),
                ExtensionConfigField(key="line_color", label="结果颜色", description="color 参数示例。", field_type="color", default="#0078D4"),
                ExtensionConfigField(key="reference_line", label="参考曲线", description="line 参数示例。", field_type="line", default=1),
                ExtensionConfigField(key="preview_path", label="参考文件", description="figure 参数示例。", field_type="figure", default=""),
            ],
        )
    )
```

### 2. 分析扩展

保存为 `extensions/analysis/interface_contract_analysis.py`：

```python
from __future__ import annotations

from core.extension_api import AnalysisExtension, ExtensionConfigField
from extensions.processing.extension_tools import line_xy, normalize_lines


VERSION = "0.1.0"


def analysis_interface_contract(lines, params):
    normalized = normalize_lines(lines)
    precision = max(0, int(params.get("precision", 3) or 3))
    include_plot = bool(params.get("include_plot", True))
    title = str(params.get("title", "接口示例分析") or "接口示例分析")
    method = str(params.get("method", "summary") or "summary")

    rows = []
    result_lines = []
    plot_series = []
    total_points = 0
    for index, line in enumerate(normalized, start=1):
        xs, ys = line_xy(line)
        total_points += len(xs)
        y_min = min(ys) if ys else 0.0
        y_max = max(ys) if ys else 0.0
        y_mean = sum(ys) / len(ys) if ys else 0.0
        rows.append([index, len(xs), round(y_min, precision), round(y_max, precision), round(y_mean, precision)])
        if include_plot:
            line_name = f"line_{index}"
            result_lines.append({"line_name": line_name, "line": line})
            plot_series.append({"name": line_name, "line": line_name})

    result = {
        "analysis_type": "interface_contract_analysis",
        "title": title,
        "method": method,
        "line_count": len(normalized),
        "point_count": total_points,
        "summary_items": [
            ("曲线数量", len(normalized)),
            ("点数量", total_points),
            ("分析方法", method),
        ],
        "tables": [
            {
                "title": "输入曲线摘要",
                "headers": ["序号", "点数", "Y 最小值", "Y 最大值", "Y 均值"],
                "rows": rows,
            }
        ],
        "texts": ["该扩展示例展示分析扩展的 dict 输出结构。"],
    }
    if include_plot:
        result["lines"] = result_lines
        result["_plot_series"] = plot_series
    return result


def register_extensions(registry):
    registry.register_analysis(
        AnalysisExtension(
            type="interface_contract_analysis",
            name="接口示例：分析扩展",
            handler=analysis_interface_contract,
            description="展示分析扩展的强制签名 (lines, params) -> dict，以及摘要、表格、文本和绘图输出。",
            version=VERSION,
            lines_number=(1, -1),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            hidden=True,
            config_fields=[
                ExtensionConfigField(key="title", label="分析标题", description="string 参数示例。", field_type="string", default="接口示例分析"),
                ExtensionConfigField(key="method", label="分析方法", description="selective 参数示例。", field_type="selective", default="summary", choices=("summary", "quality", "report")),
                ExtensionConfigField(key="precision", label="小数位", description="integer 参数示例。", field_type="integer", default=3, min_value=0, max_value=8),
                ExtensionConfigField(key="include_plot", label="输出绘图序列", description="boolean 参数示例。", field_type="boolean", default=True),
                ExtensionConfigField(key="accent_color", label="强调色", description="color 参数示例。", field_type="color", default="#0078D4"),
            ],
            report_placeholders=[
                {"token": "{{line_count}}", "label": "接口示例曲线数", "description": "接口示例分析输入曲线数量。"},
                {"token": "{{point_count}}", "label": "接口示例点数", "description": "接口示例分析输入点总数。"},
            ],
        )
    )
```

### 3. 绘图扩展

保存为 `extensions/plot/interface_contract_plot.py`：

```python
from __future__ import annotations

from core.extension_api import ExtensionConfigField, PlotExtension, normalize_extension_lines_list
from extensions.processing.extension_tools import line_xy, series_payloads_to_lines


VERSION = "0.1.0"


def _context_series(plot_context, params):
    base_series = list(plot_context.visible_series or plot_context.plotted_series or [])
    requested = normalize_extension_lines_list(params.get("lines_list")) if "lines_list" in params else []
    if requested:
        return [base_series[index - 1] for index in requested if 1 <= index <= len(base_series)]

    ordered = []
    if isinstance(plot_context.selected_series, dict):
        ordered.append(plot_context.selected_series)
    for item in base_series:
        if isinstance(plot_context.selected_series, dict) and item is plot_context.selected_series:
            continue
        ordered.append(item)
    return ordered


def _visible_points(plot_context, params):
    points = []
    for index, line in enumerate(series_payloads_to_lines(_context_series(plot_context, params)), start=1):
        xs, ys = line_xy(line)
        for x_value, y_value in zip(xs, ys):
            points.append((f"line_{index}", float(x_value), float(y_value)))
    return points


def plot_interface_contract(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return None

    points = _visible_points(plot_context, params)
    color = str(params.get("color", "#0078D4") or "#0078D4")
    alpha = max(0.0, min(1.0, float(params.get("alpha", 0.9) or 0.9)))
    label = str(params.get("label", "接口示例绘图") or "接口示例绘图")
    show_centroid = bool(params.get("show_centroid", True))
    marker = str(params.get("marker", "o") or "o")
    size = max(1.0, float(params.get("marker_size", 36.0) or 36.0))

    if show_centroid and points:
        center_x = sum(point[1] for point in points) / len(points)
        center_y = sum(point[2] for point in points) / len(points)
        axis.scatter([center_x], [center_y], s=size, marker=marker, color=color, alpha=alpha, label=label, zorder=8)
        axis.annotate(label, xy=(center_x, center_y), xytext=(8, 8), textcoords="offset points", color=color)
    axis.grid(bool(params.get("show_grid", True)))
    return None


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="interface_contract_plot",
            name="接口示例：绘图扩展",
            handler=plot_interface_contract,
            description="展示绘图扩展的强制签名 (plot_context, params) -> None，只操作当前 matplotlib 图元。",
            version=VERSION,
            lines_number=(1, -1),
            phases=("after_plot",),
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            hidden=True,
            config_fields=[
                ExtensionConfigField(key="label", label="标注文本", description="string 参数示例。", field_type="string", default="接口示例绘图"),
                ExtensionConfigField(key="color", label="标注颜色", description="color 参数示例。", field_type="color", default="#0078D4"),
                ExtensionConfigField(key="marker", label="点形状", description="selective 参数示例。", field_type="selective", default="o", choices=("o", "s", "^", "D")),
                ExtensionConfigField(key="marker_size", label="点大小", description="number 参数示例。", field_type="number", default=36.0, min_value=1.0, step=1.0),
                ExtensionConfigField(key="alpha", label="透明度", description="limited 参数示例。", field_type="limited", default=0.9, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="show_centroid", label="显示中心点", description="boolean 参数示例。", field_type="boolean", default=True),
                ExtensionConfigField(key="show_grid", label="显示网格", description="boolean 参数示例。", field_type="boolean", default=True),
            ],
        )
    )
```

### 4. 数字化扩展

保存为 `extensions/digitize/interface_contract_digitize.py`：

```python
from __future__ import annotations

from core.extension_api import DigitizeExtension, ExtensionConfigField
from extensions.processing.extension_tools import line_from_xy


VERSION = "0.1.0"


def digitize_interface_contract(figure, params):
    del figure
    count = max(0, int(params.get("point_count", 3) or 3))
    spacing = max(1.0, float(params.get("spacing", 16.0) or 16.0))
    start_x = float(params.get("start_x", 10.0) or 10.0)
    start_y = float(params.get("start_y", 10.0) or 10.0)
    reverse_y = bool(params.get("reverse_y", False))
    _sampled_color = params.get("sampled_color")
    _template_info = params.get("template_info")
    _reference_figure = params.get("reference_figure")
    del _sampled_color, _template_info, _reference_figure

    xs = [start_x + index * spacing for index in range(count)]
    if reverse_y:
        ys = [start_y - index * spacing for index in range(count)]
    else:
        ys = [start_y + index * spacing for index in range(count)]
    return line_from_xy(xs, ys)


def register_extensions(registry):
    registry.register_digitize(
        DigitizeExtension(
            type="interface_contract_digitize",
            name="接口示例：数字化扩展",
            handler=digitize_interface_contract,
            description="展示数字化扩展的强制签名 (figure, params) -> line，以及 pickcolor / shot 交互字段。",
            version=VERSION,
            settings=True,
            source_kind="builtin",
            tool_tier="experimental",
            hidden=True,
            config_fields=[
                ExtensionConfigField(key="point_count", label="点数量", description="integer 参数示例。", field_type="integer", default=3, min_value=0, max_value=100),
                ExtensionConfigField(key="spacing", label="点间距", description="number 参数示例。", field_type="number", default=16.0, min_value=1.0, step=1.0),
                ExtensionConfigField(key="start_x", label="起点 X", description="number 参数示例。", field_type="number", default=10.0, step=1.0),
                ExtensionConfigField(key="start_y", label="起点 Y", description="number 参数示例。", field_type="number", default=10.0, step=1.0),
                ExtensionConfigField(key="reverse_y", label="Y 反向", description="boolean 参数示例。", field_type="boolean", default=False),
                ExtensionConfigField(key="sampled_color", label="采样颜色", description="pickcolor 参数示例。", field_type="pickcolor", default={"r": 0, "g": 120, "b": 212}),
                ExtensionConfigField(key="template_info", label="模板截图", description="shot 参数示例。", field_type="shot", default=None),
                ExtensionConfigField(key="reference_figure", label="参考图片", description="figure 参数示例。", field_type="figure", default=""),
            ],
        )
    )
```

---

## Registry API

扩展通过 `register_extensions(registry)` 接收的 `registry` 对象是一个 `ExtensionRegistry` 实例。以下列出扩展可用的注册方法：

```python
# 注册四类扩展
registry.register_processing(ProcessingExtension(...))
registry.register_analysis(AnalysisExtension(...))
registry.register_plot(PlotExtension(...))
registry.register_digitize(DigitizeExtension(...))
```

`register_extensions` 函数只负责注册，不做耗时计算。如果需要在注册前检查其他扩展是否就绪，可以使用：

```python
# 检查某类型扩展是否已注册
registry.get_processing(type_id)     # -> ProcessingExtension | None
registry.get_analysis(type_id)       # -> AnalysisExtension | None
registry.get_plot(type_id)           # -> PlotExtension | None
registry.get_digitize(type_id)       # -> DigitizeExtension | None
```

---

## 发布层级与内置扩展策略

对外发布时，建议把内置扩展分成两层：

- `tool`：默认展示给终端用户，强调通用、稳定、原子、低学习成本。
- `experimental`：默认隐藏，仅用于接口演示、能力试验或等待产品整合。

面向二维曲线软件，正式发布的内置扩展应优先覆盖四类基础能力：

- 数据整理：排序、去重、插值、裁剪、重采样、平滑、基线校正、归一化。
- 数值分析：统计、峰值、拟合、相关性、交点、面积差、误差比较。
- 图表表达：参考线、线尾标签、统一注释、局部放大、不确定性带。
- 图像数字化：连续曲线、虚线、多色曲线、标记点、单色曲线识别。

不建议对外默认公开的内置扩展通常包括：

- 仅用于接口契约回归的 `interface_contract_*`。
- 与通用入口重复、会增加认知负担的拆分型绘图扩展，例如把箭头、矩形、圆形、文字各自拆成单独工具。
- 仍依赖较强假设、适用范围偏窄或更适合沉入页面模板系统的扩展。

### 推荐公开的内置扩展

**处理扩展：** `order_points`、`sort_dedup_interpolate`、`crop`、`despike`、`smooth`、`filter`、`baseline_correction`、`normalize`、`resample`、`derivative`、`integral`、`transform`、`kalman_filter`、`fft`、`multi_curve_mean`、`pairwise_compute`

**分析扩展：** `statistics`、`peak_detect`、`curve_fit`、`spectrum_analysis`、`correlation`、`lag_analysis`、`curve_intersections`、`area_between_curves`、`error_compare`

**绘图扩展：** `plot_annotation`、`plot_reference_line`、`plot_line_end_label`、`plot_uncertainty_band`、`plot_dual_curve_band`、`plot_local_zoom`、`plot_polar_projection`

**数字化扩展：** `builtin_digitize_color_detect`、`builtin_digitize_continuous_trace`、`builtin_digitize_dashed_trace`、`builtin_digitize_marker_centroid`、`builtin_digitize_multicolor_curve`

**默认隐藏更合适的内置扩展：** `interface_contract_processing`、`interface_contract_analysis`、`interface_contract_plot`、`interface_contract_digitize`、`builtin_digitize_shape_detect`、`ifft`、`multi_curve_correlation`、`plot_science_style`、`plot_arrow_annotation`、`plot_rectangle_annotation`、`plot_circle_annotation`、`plot_text_annotation`

---

## 原子性要求

扩展应当只做一类职责，前置条件通过 pipeline 或显式前序步骤满足，而不是在 handler 内部偷偷代做。

推荐做法：

- `order_points` 只做点序重排。
- `sort_dedup_interpolate` 只做排序、去重和插值整理。
- `resample` 只做重采样。
- `pairwise_compute` 只对已经对齐的两条曲线做逐点运算。

不推荐做法：

- 在 `pairwise_compute` 内部隐式重采样或自动猜测公共 X 网格。
- 在平滑扩展内部顺带去重、补点、裁剪。
- 在某个数字化扩展内部同时承担颜色分离、点序修复、平滑和分析。

这种拆分方式更利于：

- 让用户理解每一步发生了什么。
- 在二维曲线工作流中复用相同步骤。
- 单独测试和定位误差来源。
- 保存为稳定可复现的模板。

---

## 发布检查表

提交扩展前逐项确认：

- `register_extensions(registry)` 存在且只做注册。
- `type` 全局唯一，`version` 是 `x.y.z` 格式。
- handler 签名符合所属类型的 Protocol。
- 所有曲线输入输出都是 point-list（`List[Point]`）。
- 需要从 x/y 序列生成曲线时使用 `line_from_xy`。
- 多曲线工具声明了正确的 `lines_number`。
- `config_fields` 没有显式注册 `lines`、`lines_list` 或 `lines_number` 字段。
- 绘图扩展返回 `None`，只操作当前图元。
- 分析扩展返回 dict，包含 `analysis_type` 键，表格/摘要/文本/结果曲线结构稳定。
- 数字化扩展返回 line，不返回点列表 dict 或额外页面指令。
- 使用 `tool_tier="experimental"` 和 `hidden=True` 标记仅用于接口演示的扩展。
- 扩展加载后能在对应页面执行，并通过相关测试。

---

## API Reference

本附录以结构化形式汇总所有扩展可用的公共接口，方便开发者快速查找导入路径和函数签名。也是 AI 辅助编写扩展时的规范手册。

### 导入路径速查

```python
# ─── Extension 数据类 ─────────────────────────────────────
from core.extension_api import (
    ProcessingExtension,       # 处理扩展
    AnalysisExtension,         # 分析扩展
    PlotExtension,             # 绘图扩展
    DigitizeExtension,         # 数字化扩展
    ExtensionConfigField,      # 参数字段
)

# ─── Handler Protocol 类型 ────────────────────────────────
from core.extension_definition import (
    ProcessingHandler,         # (lines, params) -> Line
    AnalysisHandler,           # (lines, params) -> dict
    PlotHandler,               # (plot_context, params) -> None
    DigitizeHandler,           # (figure, params) -> Line
    Point,                     # Tuple[float, float] = (x, y)
    Line,                      # List[Point] = [[x, y], ...]
)

# ─── 曲线工具函数（首选导入路径） ─────────────────────
from extensions.processing.extension_tools import (
    line_from_xy,              # (xs, ys) -> Line
    line_xy,                   # (line) -> (SeriesArrayView, SeriesArrayView)
    primary_line,              # (List[Line]) -> Line
    normalize_line,            # (raw) -> Line
    normalize_lines,           # (List[Line]) -> List[Line]
    series_payload_to_line,    # (dict) -> Line
    series_payloads_to_lines,  # (List[dict]) -> List[Line]
    align_lines_to_common_x,   # (lines, params) -> (List[Line], List[str])
    resolve_sample_rate,       # (xs) -> float
    BUILTIN_EXTENSION_VERSION, # str = "1.0.0"
    apply_window,              # (size, name) -> ndarray
    linear_percentile,         # (sorted_vals, percentile) -> float
    baseline_correction,       # (xs, ys, method) -> ndarray
)

# ─── 高级曲线工具（core.line_tools） ─────────────────
from core.line_tools import (
    sorted_unique_xy,          # (xs, ys) -> (xs, ys)
    estimate_sample_spacing,   # (xs) -> float
    interp_linear,             # (xs, ys, target_x) -> float
    resample_uniform,          # (xs, ys, num) -> (xs, ys)
    resample_uniform_spacing,  # (xs, ys, spacing) -> (xs, ys)
    nearest_value,             # (xs, ys, target_x) -> float
    x_values_equal,            # (xs_a, xs_b) -> bool
    resample_to_grid,          # (xs, ys, grid_x) -> [ys]
    build_alignment_grid,      # (x_arrays, mode) -> ndarray
    recommended_alignment_spacing, # (xs) -> float
    describe_alignment_mode,   # (mode) -> str
)

# ─── 绘图上下文 ─────────────────────────────────────────
from core.extension_types import (
    PlotExtensionContext,      # 绘图扩展上下文（16 个字段，7 个方法）
    PatchAuthority,            # ADVISORY / AUTHORITATIVE
)

# ─── 底层曲线容器 ──────────────────────────────────────
from core.curve_data import (
    CurveBuffer,               # (x: ndarray, y: ndarray) 冻结数据类
    SeriesArrayView,           # numpy 数组的只读 Sequence 视图
)

# ─── 辅助函数 ────────────────────────────────────────────
from core.extension_api import (
    normalize_extension_lines_list,  # (raw) -> List[int]
    normalize_extension_version,     # (str) -> str
)

from extensions.processing.extension_tools import (
    primary_line,              # 取第一条曲线（同上方声明）
)
```

### 函数签名详解

#### 曲线基础转换

```python
def line_from_xy(xs: Sequence[float], ys: Sequence[float]) -> Line:
    """从 x/y 序列生成标准 point-list line。
    检查两个序列长度一致，验证所有坐标为有限浮点数。
    异常：长度不一致或含无效坐标时抛出 ValueError。
    """
    # 示例：line_from_xy([0, 1, 2], [3, 4, 5]) -> [[0,3], [1,4], [2,5]]

def line_xy(line: Line) -> tuple[SeriesArrayView, SeriesArrayView]:
    """将 point-list line 拆分为 x/y 序列。
    返回 (SeriesArrayView, SeriesArrayView)，可直接用于 list()/len() 和 numpy 运算。
    """
    # 示例：line_xy([[0,3], [1,4], [2,5]]) -> ([0,1,2], [3,4,5])

def primary_line(lines: List[Line]) -> Line:
    """取第一条输入曲线。lines 为空时返回 []。"""
    # 示例：primary_line([[[0,3],[1,4]], [[0,5],[1,6]]]) -> [[0,3],[1,4]]

def normalize_line(raw: Any) -> Line:
    """验证并标准化为合法 point-list。非 list/tuple、元素不是 [x,y] 时抛出 ValueError。"""
    # 适用于处理前端传入的不可信数据

def normalize_lines(lines: Any) -> List[Line]:
    """批量 normalize_line。"""
```

#### 数据载荷转换

```python
def series_payload_to_line(payload: dict) -> Line:
    """从数据载荷 dict 提取曲线：payload 为 {"x": [...], "y": [...]}。"""

def series_payloads_to_lines(payloads: List[dict]) -> List[Line]:
    """批量转换。绘图扩展中使用 plot_context.visible_series 后必须经过此函数。"""
```

#### 多曲线对齐

```python
def align_lines_to_common_x(
    lines: List[Line],
    params: dict | None = None,
) -> tuple[List[Line], List[str]]:
    """将多条曲线对齐到公共 X 网格。
    params 支持：
      - align_mode: "union"（并集，默认）| "intersect"（交集）| "first"（以第一条为基准）
    返回 (aligned_lines, warnings)，warnings 为空列表时表示无警告。
    """

def resolve_sample_rate(xs: Sequence[float]) -> float:
    """估算 X 序列的采样间距。返回 xs 中相邻元素差值的众数。"""
```

#### 重采样与插值

```python
def sorted_unique_xy(xs, ys) -> tuple[list[float], list[float]]:
    """按 X 排序，合并重复 X（取对应 Y 的均值）。"""

def estimate_sample_spacing(xs) -> float:
    """估算 X 序列的平均采样间距。"""

def interp_linear(xs, ys, target_x) -> float:
    """在 (xs, ys) 上对 target_x 做线性插值。"""

def resample_uniform(xs, ys, num) -> tuple[list[float], list[float]]:
    """均匀重采样到指定点数。"""

def resample_uniform_spacing(xs, ys, spacing) -> tuple[list[float], list[float]]:
    """按指定间距重采样。"""

def nearest_value(xs, ys, target_x) -> float:
    """最近邻取值。"""

def x_values_equal(xs_a, xs_b) -> bool:
    """检查两个 X 序列是否相等（长度和值）。"""

def resample_to_grid(xs, ys, grid_x) -> list[float]:
    """在 grid_x 网格点上对 (xs, ys) 进行插值。"""

def build_alignment_grid(x_arrays, mode) -> np.ndarray:
    """构造对齐网格。mode 同 align_lines_to_common_x。"""

def recommended_alignment_spacing(xs) -> float:
    """推荐对齐间距。"""

def describe_alignment_mode(mode) -> str:
    """返回对齐模式的文字说明。"""
```

#### 数值辅助

```python
def apply_window(size: int, window_name: str) -> np.ndarray:
    """生成窗函数数组。
    window_name: "hann"(默认) | "hamming" | "blackman" | "rect"
    """

def linear_percentile(sorted_vals: List[float], percentile: float) -> float:
    """线性插值百分位数。"""

def baseline_correction(xs: np.ndarray, ys: np.ndarray, method: str) -> np.ndarray:
    """对 Y 序列进行基线校正。
    method: "none"(默认) | "constant"(减起点) | "linear"(减首尾连线)
    """
```

### 错误处理规范

扩展在遇到非法输入时应遵循以下规范：

| 场景 | 处理方式 |
|------|----------|
| 输入曲线为空 | 返回 `[]`（空 line），或继续执行并返回空结果 |
| 输入曲线含无效坐标 | 不主动验证（由 `normalize_line` / `line_from_xy` 在转换时处理），让 ValueError 传播 |
| 参数缺失 | 使用 `.get(key, default)` 安全读取，不假设参数必然存在 |
| 参数类型错误 | 尝试用 `float()`/`int()`/`str()` 转换，转换失败时使用兜底默认值 |
| 数据不足（如平滑窗口 > 数据长度） | 返回输入曲线的副本，或做安全裁剪，**不抛出 ValueError** |
| 分析扩展计算结果为空 | 返回包含 `analysis_type` 的空结构，`summary_items=[("状态", "无数据")]` |

示例：

```python
def handler(lines, params):
    xs, ys = line_xy(primary_line(lines))
    if not len(xs):                     # 空曲线 → 返回空
        return line_from_xy([], [])

    window = int(params.get("window", 5) or 5)
    window = max(3, min(window, len(ys) if len(ys) % 2 == 1 else len(ys) - 1))
    if window < 3:                      # 数据不足 → 返回副本
        return line_from_xy(list(xs), list(ys))
    # ... 正常处理
```

### 外部扩展开发说明

将扩展放在内置 `extensions/` 目录之外的自定义目录时，需注意：

```python
# 外部扩展必须声明 source_kind="external"
registry.register_processing(
    ProcessingExtension(
        ...
        source_kind="external",    # ← 必填！默认 "builtin"
        tool_tier="tool",          # 外部扩展默认可见
    )
)
```

**配置外部扩展目录**：
1. 打开设置页 → 扩展 → 外部扩展目录
2. 添加自定义目录（如 `~/.config/aline/extensions/`）
3. 将 `.py` 文件放入该目录
4. 点击"重载扩展"

**外部扩展的限制**：
- 不能依赖内置扩展的私有模块（以下划线开头的模块和函数）
- 建议使用 `source_kind="external"`，否则部分管理功能（重载、禁用、分类显示）可能异常
- 外部扩展通过 `~/.config/aline/extension_settings.json` 管理启停状态

### 扩展测试方法

编写扩展后，通过以下方式验证：

#### 方法一：加载测试（验证注册成功）

启动应用，打开对应页面，在扩展面板中确认：
- 扩展出现在扩展列表中
- 配置参数表单正确渲染
- 点击"应用"后能正常执行

#### 方法二：自动化测试（推荐）

在 `tests/` 目录中创建测试文件：

```python
# tests/test_my_extension.py
from core.extension_registry import extension_registry
from core.extension_loader import load_configured_extensions


def test_my_extension_loads():
    extension_registry.clear()
    load_configured_extensions("extensions")
    ext = extension_registry.get_processing("my_extension_type")
    assert ext is not None
    assert ext.version == "1.0.0"


def test_my_extension_handler():
    from extensions.processing.my_extension import my_handler
    from extensions.processing.extension_tools import line_from_xy, line_xy

    result = my_handler(
        [[[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]]],
        {"param1": 1.5},
    )
    xs, ys = line_xy(result)
    assert len(xs) > 0
```

运行测试：
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_my_extension.py -v
```
