# ALine 扩展规则

ALine 会在启动时扫描当前工作区的 extensions 目录，并按处理、分析、绘图、数字化四类扩展注册到统一的 ExtensionRegistry。本文档只描述当前仓库已经落地的规则，不再保留旧版 PlotStyleExtension / CurveStyleExtension 约定。

## 1. 扩展分类

### 1.1 功能分类

| 功能分类   | 注册类型            | 强制处理函数签名         | 主要用途                                       |
| ---------- | ------------------- | ------------------------ | ---------------------------------------------- |
| 处理扩展   | ProcessingExtension | (lines, params) -> line  | 对单条或多条曲线做数据处理                     |
| 分析扩展   | AnalysisExtension   | (lines, params) -> dict  | 计算摘要、结果表、结果曲线                     |
| 绘图扩展   | PlotExtension       | (lines, params) -> None  | 在 before_plot / after_plot 阶段修改当前图表图元 |
| 数字化扩展 | DigitizeExtension   | (figure, params) -> line | 从当前数字化图像资源中提取点                   |

统一曲线协议：

- line = [x_list, y_list]
- lines = [line, ...]
- 仓库内 builtin / base / 新增扩展一律只使用 line / lines，不再使用 xs / ys、曲线 dict、plot_context 或 `points + summary` 兼容结构作为正式协议。

当前仓库推荐目录：

- extensions/processing
- extensions/analysis
- extensions/plot
- extensions/digitize

### 1.2 类别分类

- extensions/processing/kalman_filter.py：卡尔曼滤波（experimental）。
- extensions/processing/multi_curve_mean.py：多曲线均值（experimental）。
| source_kind | 含义     | 界面行为                                   |
| ----------- | -------- | ------------------------------------------ |
| base        | 基础扩展 | 不显示在可开关列表中，不允许关闭           |
| builtin     | 内置扩展 | 默认显示在扩展列表中，可随仓库分发         |
| external    | 外部扩展 | 来自外部目录或任何非 base / builtin 的来源 |

规则：

- 新增仓库内扩展时，必须显式声明 source_kind="builtin"。
- 工作台内部基础能力必须显式声明 source_kind="base"。
- 任何其他字符串都会在运行时被归一化为 external，但不应依赖这个隐式行为。

### 1.3 加载入口

每个扩展文件都必须导出 register_extensions(registry)：

```python
def register_extensions(registry):
    ...
```

加载规则：

- 工作区 builtin 扩展默认从当前目录下的 extensions 递归扫描。
- 外部扩展默认目录为 ~/.config/aline/extensions。
- 文件名建议使用 snake_case.py。
- 以下划线开头的 Python 文件不会自动加载。
- builtin 扩展不会加载 `_demo.py`；示例代码仅保留在 README 中。
- 修改扩展文件后，可通过页面上的“重载扩展”入口重新扫描，无需重启应用。

## 2. 扩展规则

### 2.1 扩展定义规则

所有扩展定义都应显式给出以下核心字段：

- type：扩展唯一标识，必须全局唯一。
- name：界面显示名称。
- handler：扩展处理函数。
- description：扩展用途说明。
- version：必须是 x.y.z 格式。
- settings：是否允许在设置页生成可保存配置。
- source_kind：必须显式声明为 base / builtin / external 之一。
- hidden：仅用于不希望显示在列表中的扩展。
- report_placeholders：仅分析扩展可声明；用于向报告模板系统注册额外占位符。

标准定义示例：

```python
from core.extension_api import ExtensionConfigField, ProcessingExtension
from processing.extension_tools import line_from_xy, line_xy, primary_line


def smooth_handler(lines, params):
    del params
    xs, ys = line_xy(primary_line(lines))
    return line_from_xy(list(xs), list(ys))


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="smooth",
            name="平滑",
            handler=smooth_handler,
            description="对当前曲线做平滑处理。",
            version="1.0.0",
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            default_options={"window": 9},
            config_fields=[
                ExtensionConfigField(
                    key="window",
                    label="窗口大小",
                    description="平滑窗口长度。",
                    field_type="integer",
                    default=9,
                    min_value=1,
                )
            ],
        )
    )
```

#### 扩展定义字段规则

1. register_extensions 中只做注册，不做重计算或 I/O。
2. handler 内只依赖入参与运行时上下文，不读取页面私有状态。
3. config_fields 优先使用标准字段类型，不再依赖页面侧别名。
4. lines_number 只用于处理扩展、分析扩展、绘图扩展；数字化扩展不需要这个字段。
5. 默认值应放在 default_options 中，并与 config_fields.default 保持一致。
6. 分析扩展如需暴露报告占位符，必须在 report_placeholders 中显式声明 token / label / description。

#### 分析扩展 report_placeholders 规则

- report_placeholders 只对 AnalysisExtension 生效。
- token 必须写成 {{placeholder_name}} 形式，最终会进入报告模板下拉列表。
- label 用于模板编辑器展示名称。
- description 用于解释占位符的来源和语义。
- 未声明的标量结果字段仍可能被动态识别为占位符，但仓库内分析扩展如需稳定模板能力，必须显式声明 report_placeholders。

示例：

```python
AnalysisExtension(
    type="demo_analysis",
    name="示例分析",
    handler=summary_only,
    version="1.0.0",
    lines_number=(1, 1),
    settings=True,
    source_kind="builtin",
    report_placeholders=[
        {
            "token": "{{dominant_frequency}}",
            "label": "主频",
            "description": "频谱分析结果中的主频",
        },
        {
            "token": "{{dominant_amplitude}}",
            "label": "主峰幅值",
            "description": "频谱分析结果中的主峰幅值",
        },
    ],
)
```

#### 标准字段类型与参数示例

| field_type | 用途                   | 参数示例                                                                  |
| ---------- | ---------------------- | ------------------------------------------------------------------------- |
| string     | 单行文本               | key="label", default="平均值"                                             |
| integer    | 整数                   | key="window", default=9, min_value=1                                      |
| number     | 浮点数                 | key="threshold", default=0.75, step=0.01                                  |
| boolean    | 布尔开关               | key="fill", default=False                                                 |
| selective  | 固定选项               | key="mode", choices=("low", "high")                                       |
| limited    | 区间滑杆               | key="alpha", default=0.2, min_value=0.0, max_value=1.0                    |
| color      | 颜色                   | key="line_color", default="#0078D4"                                       |
| line       | 单条曲线选择           | key="line_index", default=1                                               |
| lines      | 多条曲线选择（隐式）   | 由 lines_number 自动注入；不允许显式声明 ExtensionConfigField             |
| figure     | 路径 / 文件 / 图片输入 | key="template_path", placeholder="/tmp/template.png"                      |
| pickcolor  | 在当前图像上取色       | key="sampled_color", default={"r": 10, "g": 20, "b": 30}                  |
| shot       | 在当前图像上截图       | key="template_info", default={"size": [24, 11], "bounds": [0, 1, 24, 12]} |

推荐写法：

```python
ExtensionConfigField(
    key="sampled_color",
    label="采样颜色",
    description="点击按钮后在当前图片上取色。",
    field_type="pickcolor",
    default={"r": 255, "g": 0, "b": 0},
)
```

#### lines_number / lines_list 规则

- 不声明 lines_number：界面不显示“选择曲线”控件。
- lines_number=(1, 1)：单曲线扩展。
- lines_number=(2, 2)：双曲线扩展，必须显式勾选两条曲线。
- lines_number=(2, -1)：两条及以上曲线扩展。
- `field_type="lines"` 只允许作为运行时隐式字段存在；扩展文件中不得显式注册。显式补充参数只允许使用 `field_type="line"`。
- lines_list 始终保存为从 1 开始的下标列表，例如 [1, 3, 4]。
- 不再支持 all、:、*、selected 等旧哨兵值。

### 2.2 扩展输入规则

#### 处理扩展输入规则

强制签名：

```python
def handler(lines, params):
    ...
```

输入规则：

- lines 是按顺序归一化后的曲线列表，`lines[0]` 始终是当前主曲线。
- 每条曲线都是 `line = [x_list, y_list]`。
- params 是页面解析后的参数字典。
- 多曲线处理一律通过 `lines_number` 和隐式 `lines_list` 选择输入顺序。
- 处理扩展不得再依赖 `xs / ys` 或曲线 dict 中的 `name / color` 等元数据；如需结果命名或颜色，应通过 params 驱动上层运行时处理。

参数示例：

```python
params = {
    "method": "moving_avg",
    "window": 9,
    "lines_list": [1, 2],
}
```

#### 分析扩展输入规则

强制签名：

```python
def handler(lines, params):
    ...
```

输入规则：

- lines 是 `list(line)`，不再包含 `name` 等元数据字段。
- params 是扩展参数字典。
- 多曲线分析扩展会在运行前补齐 lines_list，用于恢复输入顺序。
- 运行时会在结果 dict 缺省时补齐 `source_name / name1 / name2` 等标准元数据字段；扩展自身不应假设输入里带有名字。

参数示例：

```python
lines = [
    [[0.0, 1.0], [1.0, 2.0]],
    [[0.0, 1.0], [2.0, 3.0]],
]
params = {"lines_list": [1, 2], "method": "pearson"}
```

#### 绘图扩展输入规则

强制签名：

```python
def handler(lines, params):
    ...
```

输入规则：

- lines 是当前可见曲线的 `list(line)`；如存在选中曲线，运行时会优先把它放在第一项。
- params 是扩展参数字典，统一命名为 params，不再使用 options。
- 运行时会先把当前 matplotlib figure / axis 设为激活状态，再调用 handler。
- 绘图扩展只能直接操作当前图表图元；不得再依赖 `plot_context.patch_*`、`skip_default_plot` 等上下文私有 API。

params 示例：

```python
params = {
    "line_color": "#C23B22",
    "line_style": "--",
    "append_summary_to_title": True,
}
```

#### 数字化扩展输入规则

强制签名：

```python
def handler(figure, params):
    ...
```

输入规则：

- figure 是当前数字化图像资源；当前仓库实现中传入的是图片路径字符串。
- params 是数字化参数字典。
- mask_polygons 与 mask_include_mode 会由数字化页自动注入到 params。
- mask_polygons / mask_include_mode 属于运行时上下文参数，不需要也不应在 config_fields 中重复暴露。
- 与图片交互相关的字段优先用 pickcolor / shot。

参数示例：

```python
params = {
    "sampled_color": {"r": 10, "g": 20, "b": 30},
    "template_info": {"size": [24, 11], "bounds": [0, 1, 24, 12]},
    "threshold": 0.72,
    "mask_polygons": [[(1.0, 2.0), (3.0, 4.0), (3.0, 5.0)]],
    "mask_include_mode": False,
}
```

### 2.3 扩展输出规则

以下规则是当前仓库内扩展的固定输出规范。兼容层仍可能接受旧格式，但 builtin / base / 仓库内新扩展必须按这里的结构返回。

#### 处理扩展输出规则

标准输出：

```python
return [list(xs), list(ys)]
```

规则：

- 返回值必须能表示新的一条曲线。
- 必须返回 line，两个序列长度必须一致。
- 仓库内处理扩展不再返回 dict、warnings 或多条结果列表作为正式输出。
- 处理扩展不负责直接操作界面控件。

#### 分析扩展输出规则

标准输出必须是 dict。

常用结果键：

- analysis_type：分析类型标识。
- 普通标量字段：自动进入摘要与报告占位符。
- _plot_series 或 plot_series：供分析页绘图。
- summary_items：显式摘要表，格式为 [("项目", "结果"), ...]。
- tables / table_sections：结果表。
- texts / text_sections / text / markdown：补充说明文本。

规则：

- builtin / base / 仓库内分析扩展必须返回 dict，不再接受 tuple / list / 裸标量作为正式输出。
- `source_name / name1 / name2` 等标准命名字段允许由运行时在返回后补齐。
- 如需绘图，必须写入 plot_series 或 _plot_series，且每项至少包含 x / y。
- 如需表格，必须写入 tables 或 table_sections，格式固定为 title / headers / rows。
- 如需文本说明，必须写入 texts / text_sections / text / markdown 之一。
- summary_items 如已提供，将优先用于摘要区；否则其余标量字段会被自动整理成摘要。

结果示例：

```python
return {
    "analysis_type": "spectrum_analysis",
    "dominant_frequency": 12.5,
    "dominant_amplitude": 3.4,
    "summary_items": [("主频", 12.5), ("主峰幅值", 3.4)],
    "_plot_series": [
        {
            "name": "频谱",
            "x": [0.0, 1.0, 2.0],
            "y": [0.2, 3.4, 1.1],
            "color": "#0078D4",
            "line_width": 1.6,
        }
    ],
    "tables": [
        {
            "title": "峰值表",
            "headers": ["序号", "X", "Y"],
            "rows": [[1, 1.0, 3.4]],
        }
    ],
}
```

#### 绘图扩展输出规则

绘图扩展通常不返回数据，而是直接修改当前激活的 matplotlib figure / axis。

规则：

- before_plot / after_plot 仍由运行时 phase 控制，但 handler 本身始终只接收 `(lines, params)`。
- 扩展应直接通过 `matplotlib.pyplot.gcf()` / `gca()` 或当前 axis 对图元做修改。
- 不再允许通过 `plot_context.skip_default_plot` 等上下文字段篡改页面绘图流程。
- builtin / base / 仓库内绘图扩展不应返回新的曲线数据结构作为正式输出。

#### 数字化扩展输出规则

标准输出：

```python
return [[10.0, 13.0], [12.0, 15.0]]
```

规则：

- builtin / base / 仓库内数字化扩展必须返回 line。
- 页面运行时会把 line 转回 `[(x, y), ...]` 预览点列表。
- 数字化扩展不再返回 `points / summary / warnings` dict，也不再让页面猜测字段结构。

### 2.4 可使用的底层接口工具

扩展实现允许直接复用当前仓库已经稳定存在的底层工具，但正式对外仅保留以下 4 个底层接口：

- processing.data_engine.align_lines_to_common_x：多曲线按公共 X 网格自动对齐。
- processing.extension_tools.crop_xy：按 X 区间裁剪 line。
- processing.extension_tools.transform_xy：按表达式变换 line。
- processing.extension_tools.resample_xy：按点数 / 间距 / 对齐模式重采样 line。

规则：

- 优先复用这些底层接口，不要在扩展里重复实现相同的裁剪、变换、重采样、对齐逻辑。
- 如果扩展依赖这些工具，仍应通过 handler 入参与 params 驱动，不直接访问页面私有对象。
- 内置数字化算法应保留在 `extensions/digitize` 目录内部实现，不再依赖旧的 `digitize.auto_extractor` / `digitize.shape_extractor` 模块。

## 3. 扩展样例

### 3.1 处理扩展示例

最小样例：

```python
from core.extension_api import ProcessingExtension
from processing.extension_tools import line_xy, primary_line


def passthrough(lines, params):
    del params
    return primary_line(lines)


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="demo_processing",
            name="示例处理",
            handler=passthrough,
            version="1.0.0",
            settings=True,
            source_kind="builtin",
        )
    )
```

当前仓库样例：

- extensions/processing/crop.py：裁剪指定区间。
- extensions/processing/derivative.py：导数计算。
- extensions/processing/fft.py：快速傅里叶变换。
- extensions/processing/filter.py：低通 / 高通滤波。
- extensions/processing/integral.py：积分计算。
- extensions/processing/normalize.py：归一化。
- extensions/processing/pairwise_compute.py：双曲线逐点计算。
- extensions/processing/kalman_filter.py：卡尔曼滤波（experimental）。
- extensions/processing/multi_curve_mean.py：多曲线均值（experimental）。
- extensions/processing/resample.py：重采样。
- extensions/processing/smooth.py：平滑。
- extensions/processing/transform.py：坐标变换。

### 3.2 分析扩展示例

最小样例：

```python
from core.extension_api import AnalysisExtension


def summary_only(lines, params):
    del params
    xs, _ys = lines[0] if lines else ([], [])
    return {
        "analysis_type": "demo_analysis",
        "point_count": len(xs),
    }


def register_extensions(registry):
    registry.register_analysis(
        AnalysisExtension(
            type="demo_analysis",
            name="示例分析",
            handler=summary_only,
            version="1.0.0",
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
        )
    )
```

当前仓库样例：

- extensions/analysis/curve_fit.py：曲线拟合。
- extensions/analysis/peak_detect.py：峰值检测。
- extensions/analysis/statistics.py：统计分析。
- extensions/analysis/correlation.py：相关性分析。
- extensions/analysis/error_compare.py：误差对比。
- extensions/analysis/spectrum_analysis.py：频谱分析（experimental）。
- extensions/analysis/multi_curve_correlation.py：多曲线相关性（experimental）。

### 3.3 绘图扩展示例

最小样例：

```python
from core.extension_api import PlotExtension


def add_title_note(lines, params):
    import matplotlib.pyplot as plt

    del lines
    axis = plt.gca() if plt.gcf().axes else None
    if axis is None:
        return
    axis.set_title(str(params.get("title", "绘图扩展示例")))


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="demo_plot",
            name="示例绘图",
            handler=add_title_note,
            version="1.0.0",
            settings=True,
            source_kind="builtin",
        )
    )
```

当前仓库样例：

- extensions/plot/plot_reference_line.py：参考线与峰值标注（experimental）。
- extensions/plot/plot_arrow_annotation.py：箭头标注（tool）。
- extensions/plot/plot_rectangle_annotation.py：矩形框（tool）。
- extensions/plot/plot_circle_annotation.py：圆形框（tool）。
- extensions/plot/plot_text_annotation.py：文字标注（tool）。
- extensions/plot/plot_dual_curve_band.py：双曲线差异带（experimental）。
- extensions/plot/plot_science_style.py：Science 风格图幅（experimental）。
- extensions/plot/plot_polar_projection.py：极坐标投影（experimental）。

### 3.4 数字化扩展示例

最小样例：

```python
from core.extension_api import DigitizeExtension
from processing.extension_tools import line_from_xy


def detect_points(figure, params):
    del figure, params
    return line_from_xy([10.0, 20.0], [10.0, 20.0])


def register_extensions(registry):
    registry.register_digitize(
        DigitizeExtension(
            type="demo_digitize",
            name="示例数字化",
            handler=detect_points,
            version="1.0.0",
            settings=True,
            source_kind="builtin",
        )
    )
```

当前仓库样例：

- extensions/digitize/color_detect.py：取色后按颜色识别点。
- extensions/digitize/shape_detect.py：截图模板后按形状匹配点。

## 4. 程序化调用参考

- 手动加载目录：extension_registry.load_from_directory("./extensions")
- 处理扩展：processing.data_engine.apply_operation(..., {"type": "smooth", "params": {...}})
- 分析扩展：core.analysis_engine.run_analysis("curve_fit", inputs, params)
- 绘图扩展：通过可视化页触发当前 matplotlib figure / axis 生命周期
- 数字化扩展：通过数字化页自动检测入口触发
