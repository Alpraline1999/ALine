# ALine 扩展使用说明

ALine 启动时会自动递归扫描 extensions 目录及其子目录中的扩展文件。当前支持 4 类扩展：

- `ProcessingExtension`: 推荐 `(xs, ys, params, lines=None) -> (xs, ys)`；旧式三参数签名仍兼容
- `AnalysisExtension`: 推荐 `(inputs, params, lines_list=None) -> result_dict`；旧式双参数签名仍兼容
- `PlotExtension`: 推荐使用 `(plot_context, options)`；旧式 `(axis, plotted_series, options)` 仍兼容
- `DigitizeExtension`: 推荐使用 `(image_path, params) -> result_dict`

扩展来源分类只使用 3 个规范值：

- `base`: 基础扩展。用于工作台内置基础能力，默认不在扩展列表中展示，也不可关闭。
- `builtin`: 内置扩展。来自当前工作区或程序内置注册，默认出现在扩展列表中。
- `external`: 外部扩展。来自其他目录或任何非 `base` / `builtin` 的来源值。运行时会把其他字符串统一归一化到 `external`。

`PlotStyleExtension` 和 `CurveStyleExtension` 已不再支持。曲线透明度等样式参数现在直接由界面内置表单管理，不再通过扩展注入。

## 1. 加载模型

- 仓库内置扩展位于当前工作区的 `extensions` 目录；推荐按 `extensions/processing`、`extensions/analysis`、`extensions/plot`、`extensions/digitize` 分目录管理。
- 设置页可以控制“是否加载内置扩展”，并支持按扩展文件逐项禁用。
- 外部扩展仍然支持，默认扫描目录为 `~/.config/aline/extensions`。
- 文件名建议使用 `snake_case.py`。
- 以下划线开头的 Python 文件不会被自动加载。
- 每个扩展文件都必须导出 `register_extensions(registry)`。

当前仓库自带的内置示例包括：

- `processing/processing_kalman_filter_demo.py`: 处理扩展，演示卡尔曼滤波
- `processing/processing_multi_curve_mean_demo.py`: 多曲线处理扩展，演示多条曲线求均值
- `analysis/analysis_spectrum_demo.py`: 分析扩展，返回频谱结果、主频和可绘制曲线
- `analysis/analysis_multi_curve_correlation_demo.py`: 多曲线分析扩展，以第一条曲线为主曲线对其余曲线做相关性比较
- `plot/plot_reference_line_demo.py`: 绘图扩展，添加参考线和注释
- `plot/plot_arrow_annotation_demo.py`: 绘图扩展，绘制箭头标注
- `plot/plot_rectangle_annotation_demo.py`: 绘图扩展，绘制矩形框
- `plot/plot_circle_annotation_demo.py`: 绘图扩展，绘制圆形框
- `plot/plot_text_annotation_demo.py`: 绘图扩展，绘制文字说明
- `plot/plot_dual_curve_band_demo.py`: 双曲线绘图扩展，读取 `options["lines"]` 后仅绘制选中的两条曲线区间
- `plot/plot_science_style_demo.py`: 绘图扩展，套用 Science 风格图幅
- `plot/plot_polar_projection_demo.py`: 绘图扩展，将曲线改绘为极坐标图
- `digitize/color_detect.py`: 数字化扩展，按采样颜色自动识别散点
- `digitize/shape_detect.py`: 数字化扩展，按截图模板匹配相同形状

修改扩展文件后通常不需要重启应用。处理页、分析页和可视化页都提供“重载扩展”入口，可重新扫描当前 builtin 与外部扩展目录。

## 2. 入口函数

每个扩展文件都必须定义：

```python
def register_extensions(registry):
    ...
```

ALine 会将 `ExtensionRegistry` 实例传给这个函数，由扩展自行完成注册。

## 3. 配置如何进入扩展

- `ProcessingExtension`
    输入：当前主曲线 `xs` / `ys`，可选多曲线 `lines`
    输出：新的 `(xs, ys)` 元组，或兼容旧协议的等价结果
- `AnalysisExtension`
    输入：`inputs` 列表，每项至少包含 `x`、`y`、`name`；界面参数在 `params`
    输出：`dict` 结果。建议包含 `analysis_type`，可选 `_plot_series`、标量摘要字段和报告占位符字段
- `PlotExtension`
    输入：推荐 `(plot_context, options)`，其中 `options` 为界面配置
    输出：通常直接修改图表上下文；如需跳过默认绘制，应通过 `plot_context` 的补丁/跳过标记完成
- `DigitizeExtension`
    输入：`image_path` 与 `params`
    输出：推荐返回 `{"points": [(x, y), ...], "summary": "..."}`；也兼容直接返回点列表

建议同时提供：

- `default_options`: 面板默认配置
- `config_fields`: 字段说明，用于在界面中展示配置提示
- `lines_number`: 处理扩展 / 分析扩展 / 绘图扩展的内置曲线数量协议

### 3.1 参数字段规范

`config_fields` 建议统一使用以下标准字段类型：

- `string`: 单行文本
- `integer`: 整数
- `number`: 浮点数
- `boolean`: 布尔开关
- `selective`: 固定选项
- `limited`: 带范围的连续值
- `color`: 颜色
- `line`: 单条曲线选择
- `lines`: 多条曲线选择
- `figure`: 文件 / 图像 / 路径类输入
- `pickcolor`: 点击按钮后在当前图像上取色，回填 `{ "r": int, "g": int, "b": int }`
- `shot`: 点击按钮后在当前图像上截图，回填模板字典，例如 `{ "size": [w, h], "bounds": [x1, y1, x2, y2] }`

内置扩展和基础扩展应优先直接声明这些标准字段类型，而不是依赖页面侧的临时别名或手写控件。

### 3.2 四类扩展的参数约定

- 处理扩展：界面参数统一放在 `params`；若扩展支持多曲线，建议通过 `lines_number` 和 `lines_list` 描述目标曲线。
- 分析扩展：界面参数统一放在 `params`；运行时会补齐当前参与分析的 `lines_list`，便于结果页恢复输入顺序。
- 绘图扩展：界面参数统一放在 `options`；若扩展需要引用曲线，应优先使用 `visible_series`、`plotted_series` 或显式 `lines_list`。
- 数字化扩展：界面参数统一放在 `params`；与图片交互相关的参数应优先声明为 `pickcolor` / `shot`，蒙版统一通过 `mask_polygons` 与 `mask_include_mode` 传入。

多曲线协议约定：

- 不显式声明 `lines_number`：表示该扩展不支持曲线选择内置参数，界面不会显示“选择曲线”控件
- 单曲线扩展：声明 `lines_number=(1, 1)` 或空值，运行时默认取当前上下文中的单条曲线
- 双曲线扩展：声明 `lines_number=(2, 2)`，界面会显示“选择曲线”按钮，用户需显式勾选两条曲线
- 多曲线扩展：声明 `lines_number=(2, -1)` 或其他范围，界面会显示“选择曲线”按钮并提示支持的数量范围
- `lines_list` 始终作为顶层参数保存，例如 `[1, 3, 4]`
- 分析扩展收到的 `lines_list` 顺序与界面最终解析顺序一致；第 1 项始终视为主曲线，其余项默认为副曲线
- 如果处理扩展声明了 `lines` 形参，运行时会收到当前参与处理的全部曲线 payload

字段描述结构示例：

```python
ExtensionConfigField(
    key="window",
    description="平滑窗口长度。",
    field_type="number",
    required=False,
    default=7,
)
```

## 4. AnalysisExtension 结果约定

除结果字段外，分析扩展建议把 `lines` 作为顶层参数的一部分保留在 `params` 中，便于页面恢复当前输入顺序。

分析扩展除了返回摘要字段外，还可以约定一些通用键，让分析页和报告模板自动消费：

- 普通标量字段：例如 `dominant_frequency`、`dominant_amplitude`
- 这些字段会自动出现在报告模板占位符列表中，可直接写成 `{{dominant_frequency}}` 或 `{{dominant_frequency:.2f}}`
- 以下划线开头的字段会被视为内部字段，不进入摘要列表和动态占位符
- `_plot_series`: 供分析页直接绘图的曲线列表
- `x_label` / `y_label` / `plot_title`: 自定义结果图的坐标轴标题和图标题

`_plot_series` 的典型结构如下：

```python
{
    "analysis_type": "spectrum_analysis",
    "dominant_frequency": 12.5,
    "dominant_amplitude": 3.4,
    "x_label": "频率 (Hz)",
    "y_label": "幅值",
    "plot_title": "频谱分析",
    "_plot_series": [
        {
            "name": "频谱",
            "x": [0.0, 1.0, 2.0],
            "y": [0.2, 3.4, 1.1],
            "color": "#0078D4",
            "line_width": 1.6,
        }
    ],
}
```

分析页会优先绘制 `_plot_series` 中的数据；导出“分析曲线”时会导出其中第一条曲线。

## 5. PlotExtensionContext 速览

推荐为 `PlotExtension` 使用上下文签名：

```python
def handler(plot_context, options):
    ...
```

`plot_context` 常用字段包括：

- `figure` / `canvas`: 当前 matplotlib Figure 与画布
- `axis` / `axes`: 当前主轴与 Figure 内全部轴
- `visible_series`: 默认绘制前的可见曲线源数据
- `plotted_series`: 默认绘制后得到的曲线摘要
- `figure_state`: 当前绘图状态字典
- `theme_colors`: 当前主题下的背景色、前景色、网格色
- `phase`: `before_plot` 或 `after_plot`
- `skip_default_plot`: 设为 `True` 可跳过默认曲线绘制
- `skip_default_formatting`: 设为 `True` 可跳过默认坐标轴格式化
- `skip_default_layout`: 设为 `True` 可跳过默认布局调整

如果扩展希望以“最小覆盖”方式修改当前图表样式，而不是直接硬改 matplotlib 对象，可使用以下补丁方法：

- `patch_figure_state({...})`: 覆盖 `FigureState` 中的字段，例如 `x_label`、`legend_pos`、`line_width`
- `patch_plot_style({...})`: 覆盖 `plot_style_extras` 中的附加样式，例如 `tick_params`、`legend_kwargs`
- `patch_selected_curve_style({...})`: 覆盖当前选中曲线的样式字段
- `patch_curve_style(curve_identity, {...})`: 覆盖指定曲线的样式字段

这些补丁会与界面设置按“后操作覆盖先操作、且仅覆盖被修改参数”的规则合并。适合做 Science 风格、极坐标模式等需要和设置面板共同工作的绘图扩展。

这允许扩展在 `before_plot` 阶段放置参考区域、底图或额外轴，也允许在 `after_plot` 阶段补充注释、标记和统计信息。

## 6. 最小示例

```python
from core.extension_api import AnalysisExtension, ExtensionConfigField


def spectrum(inputs, params):
    xs = [0.0, 1.0, 2.0]
    ys = [0.2, 3.4, 1.1]
    return {
        "analysis_type": "demo_spectrum",
        "source_name": inputs[0].get("name", ""),
        "dominant_frequency": 1.0,
        "_plot_series": [{"name": "频谱", "x": xs, "y": ys}],
    }


def register_extensions(registry):
    registry.register_analysis(
        AnalysisExtension(
            type="demo_spectrum",
            name="示例频谱分析",
            handler=spectrum,
            description="返回一个带自定义占位符和结果曲线的分析结果。",
            lines_number=(1, 1),
            default_options={
                "window": 7,
            },
            config_fields=[
                ExtensionConfigField(
                    key="window",
                    description="频谱窗口长度。",
                    field_type="number",
                    default=7,
                )
            ],
        )
    )
```

## 7. 调试建议

- 扩展未出现在界面中时，先检查文件是否位于 builtin `extensions` 目录或默认外部目录 `~/.config/aline/extensions`。
- 确认文件中实现了 `register_extensions(registry)`。
- 确认 `type` 唯一；重复的 `type` 会覆盖已有扩展。
- 如果扩展面板 JSON 解析失败，界面会提示必须是合法 JSON 对象。
- 如果分析结果希望参与报告模板，返回字段应是标量，且键名不要以下划线开头。
- 如果分析结果希望直接绘图，确保 `_plot_series` 中每条曲线都提供等长的 `x` 和 `y`。

## 8. 程序化调用

- 手动加载目录：`extension_registry.load_from_directory("./extensions")`
- 处理扩展：`processing.data_engine.apply_operation(..., {"type": "kalman_filter", "params": {...}})`
- 分析扩展：`core.analysis_engine.run_analysis("spectrum_analysis", inputs, params)`