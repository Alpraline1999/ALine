# ALine 扩展开发指南

ALine 扩展是一个普通 Python 文件。应用启动或重载扩展时，会递归扫描 `extensions/` 目录，调用每个文件中的 `register_extensions(registry)`，并把扩展注册到处理、分析、绘图或数字化四类入口中。

本文档描述当前正式接口。ALine 尚未发布，因此扩展协议保持严格：新增扩展只允许使用这里写明的签名、曲线结构和输出结构。

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

保存为 `extensions/processing/offset_demo.py` 后，点击应用中的“重载扩展”即可加载。

## 扩展目录

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
- 以下划线开头的文件不会自动加载。
- 每个可加载文件必须提供 `register_extensions(registry)`。
- 注册函数只负责声明扩展，不做耗时计算、网络访问或页面状态读取。
- 内置扩展声明 `source_kind="builtin"`；外部目录扩展声明 `source_kind="external"`。

## 四类扩展

| 类型       | 注册类                | 强制签名                 | 输出   | 用途                               |
| ---------- | --------------------- | ------------------------ | ------ | ---------------------------------- |
| 处理扩展   | `ProcessingExtension` | `(lines, params)`        | `line` | 生成一条新的曲线                   |
| 分析扩展   | `AnalysisExtension`   | `(lines, params)`        | `dict` | 生成摘要、表格、文本和结果曲线     |
| 绘图扩展   | `PlotExtension`       | `(plot_context, params)` | `None` | 在当前 matplotlib 图表上绘制或标注 |
| 数字化扩展 | `DigitizeExtension`   | `(figure, params)`       | `line` | 从图像资源提取曲线点               |

`params` 是页面根据 `config_fields` 和运行时上下文生成的参数字典。扩展不得把页面私有对象作为 handler 参数。

## 曲线协议

正式曲线结构是 point-list：

```python
line = [[0.0, 1.0], [1.0, 2.0], [2.0, 4.0]]
lines = [line, ...]
```

规则：

- 每个点必须是 `[x, y]`，长度固定为 2。
- `x` 和 `y` 必须能转换为有限浮点数。
- 空曲线使用 `[]`。
- 不使用曲线 dict 作为扩展输入。
- 不使用独立 `xs` / `ys` 作为扩展输入或输出。
- 不使用 `[x_list, y_list]` 作为 line。

扩展内部如果需要在 `x_list` 与 `y_list` 之间转换，使用统一工具：

```python
from extensions.processing.extension_tools import line_from_xy, line_xy

line = line_from_xy([0, 1, 2], [3, 4, 5])
xs, ys = line_xy(line)
```

`line_from_xy(xs, ys)` 会检查两个序列长度一致，并验证所有坐标合法。所有内置扩展和内部方法都应复用它。

## 公共工具

当前稳定底层接口如下：

- `extensions.processing.extension_tools.line_from_xy(xs, ys)`：从 x/y 序列生成合法 point-list line。
- `extensions.processing.extension_tools.line_xy(line)`：把 point-list line 拆成 x/y 序列。
- `extensions.processing.extension_tools.primary_line(lines)`：取第一条输入曲线，缺省返回空曲线。
- `extensions.processing.extension_tools.align_lines_to_common_x(lines, params)`：把多条 point-list 曲线对齐到公共 X 网格。

裁剪、数学变换、重采样这类单扩展算法应保留在各自扩展文件内实现，不作为稳定公共 helper 暴露。数字化扩展如需识别颜色、形状或模板，也应在 `extensions/digitize/` 内实现，不依赖旧的外部提取器模块。

## 元数据字段

所有扩展建议显式声明：

- `type`：全局唯一标识。
- `name`：界面显示名称。
- `handler`：处理函数。
- `description`：用途说明。
- `version`：`x.y.z` 格式。
- `lines_number`：需要几条输入曲线，数字化扩展不需要。
- `settings`：是否生成可保存设置。
- `source_kind`：`base`、`builtin` 或 `external`。
- `tool_tier`：`tool` 或 `experimental`。
- `config_fields`：参数表单字段。
- `report_placeholders`：分析扩展可选，用于报告模板占位符。

`lines_number` 规则：

- 不声明：界面不显示曲线选择控件。
- `(1, 1)`：需要一条曲线。
- `(2, 2)`：需要两条曲线。
- `(2, -1)`：需要两条及以上曲线。
- `lines_list` 由运行时注入到 `params`，值为从 1 开始的曲线下标列表。
- `field_type="lines"` 是运行时隐式字段，扩展文件中不得显式注册。

## 参数字段

| `field_type` | 控件语义           | 常用字段                                    |
| ------------ | ------------------ | ------------------------------------------- |
| `string`     | 单行文本           | `default`、`placeholder`                    |
| `integer`    | 整数输入           | `default`、`min_value`、`max_value`、`step` |
| `number`     | 浮点输入           | `default`、`min_value`、`max_value`、`step` |
| `boolean`    | 开关               | `default=True/False`                        |
| `selective`  | 固定选项           | `choices=(...)`                             |
| `limited`    | 范围滑块           | `min_value`、`max_value`、`step`            |
| `color`      | 颜色选择           | `default="#0078D4"`                         |
| `line`       | 单条曲线引用       | `default=1`                                 |
| `figure`     | 图片或文件路径     | `placeholder`                               |
| `pickcolor`  | 在数字化图像上取色 | `default={"r": 0, "g": 120, "b": 212}`      |
| `shot`       | 在数字化图像上截图 | `default=None`                              |

示例：

```python
ExtensionConfigField(
    key="sampled_color",
    label="采样颜色",
    description="从当前图像拾取颜色。",
    field_type="pickcolor",
    default={"r": 0, "g": 120, "b": 212},
)
```

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
- 返回值必须是一条 `line`。
- 不返回 dict、warnings、多条曲线列表或页面操作指令。

## 分析扩展

分析扩展接收多条 point-list 曲线，返回 dict。

```python
def handler(lines, params):
    line = primary_line(lines)
    xs, ys = line_xy(line)
    result_line = line_from_xy(xs[:5], ys[:5])
    return {
        "analysis_type": "demo_analysis",
        "point_count": len(xs),
        "summary_items": [("点数", len(xs))],
        "tables": [
            {
                "title": "前几个点",
                "headers": ["X", "Y"],
                "rows": list(zip(xs[:5], ys[:5])),
            }
        ],
        "lines": [
            {"line_name": "前几个点", "line": result_line},
        ],
        "_plot_series": [
            {"name": "前几个点", "line": "前几个点", "color": "#0078D4"},
        ],
    }
```

常用结果键：

- `analysis_type`：结果类型标识。
- `summary_items`：摘要区，格式为 `[('项目', 值), ...]`。
- `tables`：表格区，格式为 `title / headers / rows`。
- `texts`：文本区。
- `lines`：分析结果携带的命名曲线，格式为 `[{"line_name": "名称", "line": line}]`。
- `_plot_series`：分析页可绘制结果曲线，每项通过 `line` 字段引用 `lines` 中的 `line_name`，不再直接返回 `x` / `y`。

规则：

- 分析扩展如需返回结果曲线，必须先构造合法 point-list `line`。
- `_plot_series[].line` 必须引用顶层 `lines` 中已声明的 `line_name`。
- 不再使用 `_plot_series[].x / y` 传递结果曲线。

分析扩展可以声明 `report_placeholders`：

```python
report_placeholders=[
    {
        "token": "{{dominant_frequency}}",
        "label": "主频",
        "description": "频谱分析得到的主频。",
    }
]
```

## 绘图扩展

绘图扩展接收 `plot_context` 与参数字典，直接操作当前 matplotlib figure / axis，返回 `None`。

```python
from core.extension_api import PlotExtension
from extensions.processing.extension_tools import line_xy, series_payloads_to_lines


def handler(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return None
    points = []
    for index, line in enumerate(series_payloads_to_lines(plot_context.visible_series), start=1):
        xs, ys = line_xy(line)
        points.extend((f"line_{index}", x_value, y_value) for x_value, y_value in zip(xs, ys))
    if not points:
        return None
    x = sum(point[1] for point in points) / len(points)
    y = sum(point[2] for point in points) / len(points)
    axis.scatter([x], [y], color=params.get("color", "#0078D4"))
    return None
```

规则：

- handler 始终是 `(plot_context, params)`。
- 参数统一命名为 `params`。
- `phases` 控制调用阶段，可选 `before_plot`、`after_plot`。
- 扩展只绘制或修改当前图元，不接管页面绘图流程。
- 需要读曲线数据时，使用 `plot_context.visible_series` / `plot_context.selected_series`，再按需转成 point-list。

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

## 内置接口示例扩展

仓库包含四个专门展示和测试接口契约的内置扩展：

- `extensions/processing/interface_contract_processing.py`：展示 `(lines, params) -> line`，覆盖 string、integer、number、boolean、selective、limited、color、line、figure 字段。
- `extensions/analysis/interface_contract_analysis.py`：展示 `(lines, params) -> dict`，覆盖摘要、表格、文本、结果曲线和报告占位符。
- `extensions/plot/interface_contract_plot.py`：展示 `(plot_context, params) -> None`，覆盖绘图阶段、当前 axis 与常见绘图参数。
- `extensions/digitize/interface_contract_digitize.py`：展示 `(figure, params) -> line`，覆盖 figure、pickcolor、shot 与数字化输出。

这些扩展会正常加载，并标记为 `experimental`。它们既是功能示例，也是接口回归测试入口。

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

## 原子性要求

扩展应当只做一类职责，前置条件通过 pipeline 或显式前序步骤满足，而不是在 handler 内部偷偷代做。

推荐做法：

- `order_points` 只做点序重排。
- `sort_dedup_interpolate` 只做排序、去重和插值整理。
- `resample` 只做重采样。
- `pairwise_compute` 只对已经对齐的两条曲线做逐点运算。
- `plot_annotation` 作为统一标注入口，不再把箭头、矩形、圆形、文字作为多个公开默认扩展散落给用户。

不推荐做法：

- 在 `pairwise_compute` 内部隐式重采样或自动猜测公共 X 网格。
- 在平滑扩展内部顺带去重、补点、裁剪。
- 在某个数字化扩展内部同时承担颜色分离、点序修复、平滑和分析。

这种拆分方式更利于：

- 让用户理解每一步发生了什么。
- 在二维曲线工作流中复用相同步骤。
- 单独测试和定位误差来源。
- 保存为稳定可复现的模板。

## 推荐公开的内置扩展形态

处理扩展建议公开：

- `order_points`
- `sort_dedup_interpolate`
- `crop`
- `despike`
- `smooth`
- `filter`
- `baseline_correction`
- `normalize`
- `resample`
- `derivative`
- `integral`
- `transform`
- `kalman_filter`
- `fft`
- `multi_curve_mean`
- `pairwise_compute`

分析扩展建议公开：

- `statistics`
- `peak_detect`
- `curve_fit`
- `spectrum_analysis`
- `correlation`
- `lag_analysis`
- `curve_intersections`
- `area_between_curves`
- `error_compare`

绘图扩展建议公开：

- `plot_annotation`
- `plot_reference_line`
- `plot_line_end_label`
- `plot_uncertainty_band`
- `plot_dual_curve_band`
- `plot_local_zoom`
- `plot_polar_projection`

数字化扩展建议公开：

- `builtin_digitize_color_detect`
- `builtin_digitize_continuous_trace`
- `builtin_digitize_dashed_trace`
- `builtin_digitize_marker_centroid`
- `builtin_digitize_multicolor_curve`

默认隐藏更合适的内置扩展：

- `interface_contract_processing`
- `interface_contract_analysis`
- `interface_contract_plot`
- `interface_contract_digitize`
- `builtin_digitize_shape_detect`
- `ifft`
- `multi_curve_correlation`
- `plot_science_style`
- `plot_arrow_annotation`
- `plot_rectangle_annotation`
- `plot_circle_annotation`
- `plot_text_annotation`

## 发布检查表

提交扩展前逐项确认：

- `register_extensions(registry)` 存在且只做注册。
- `type` 全局唯一，`version` 是 `x.y.z`。
- handler 签名符合所属类型。
- 所有曲线输入输出都是 point-list line。
- 需要从 x/y 序列生成曲线时使用 `line_from_xy`。
- 多曲线工具声明了正确的 `lines_number`。
- `config_fields` 没有显式注册 `lines` 字段。
- 绘图扩展返回 `None`，只操作当前图元。
- 分析扩展返回 dict，表格、摘要、文本结构稳定。
- 数字化扩展返回 line，不返回点列表 dict 或额外页面指令。
- 扩展加载后能在对应页面执行，并通过相关测试。
