# ALine 扩展使用说明

ALine 启动时会自动扫描扩展文件。当前只支持 3 类扩展：

- `ProcessingExtension`: 推荐 `(xs, ys, params, lines=None) -> (xs, ys)`；旧式三参数签名仍兼容
- `AnalysisExtension`: 推荐 `(inputs, params, lines_list=None) -> result_dict`；旧式双参数签名仍兼容
- `PlotExtension`: 推荐使用 `(plot_context, options)`；旧式 `(axis, plotted_series, options)` 仍兼容

`PlotStyleExtension` 和 `CurveStyleExtension` 已不再支持。曲线透明度等样式参数现在直接由界面内置表单管理，不再通过扩展注入。

## 1. 加载模型

- 仓库内置扩展位于当前工作区的 `extensions` 目录；打包后会随程序一起分发。
- 设置页可以控制“是否加载内置扩展”，并支持按扩展文件逐项禁用。
- 外部扩展仍然支持，默认扫描目录为 `~/.config/aline/extensions`。
- 文件名建议使用 `snake_case.py`。
- 以下划线开头的 Python 文件不会被自动加载。
- 每个扩展文件都必须导出 `register_extensions(registry)`。

当前仓库自带的内置示例包括：

- `processing_kalman_filter_demo.py`: 处理扩展，演示卡尔曼滤波
- `processing_multi_curve_mean_demo.py`: 多曲线处理扩展，演示多条曲线求均值
- `analysis_spectrum_demo.py`: 分析扩展，返回频谱结果、主频和可绘制曲线
- `analysis_multi_curve_correlation_demo.py`: 多曲线分析扩展，以第一条曲线为主曲线对其余曲线做相关性比较
- `plot_reference_line_demo.py`: 绘图扩展，添加参考线和注释
- `plot_arrow_annotation_demo.py`: 绘图扩展，绘制箭头标注
- `plot_rectangle_annotation_demo.py`: 绘图扩展，绘制矩形框
- `plot_circle_annotation_demo.py`: 绘图扩展，绘制圆形框
- `plot_text_annotation_demo.py`: 绘图扩展，绘制文字说明
- `plot_dual_curve_band_demo.py`: 双曲线绘图扩展，读取 `options["lines"]` 后仅绘制选中的两条曲线区间
- `plot_science_style_demo.py`: 绘图扩展，套用 Science 风格图幅
- `plot_polar_projection_demo.py`: 绘图扩展，将曲线改绘为极坐标图

修改扩展文件后通常不需要重启应用。处理页、分析页和可视化页都提供“重载扩展”入口，可重新扫描当前 builtin 与外部扩展目录。

## 2. 入口函数

每个扩展文件都必须定义：

```python
def register_extensions(registry):
    ...
```

ALine 会将 `ExtensionRegistry` 实例传给这个函数，由扩展自行完成注册。

## 3. 配置如何进入扩展

- 处理扩展 / 分析扩展：界面 JSON 作为 `params` 传入
- 绘图扩展：界面 JSON 作为 `options` 传入

建议同时提供：

- `default_options`: 面板默认配置
- `config_fields`: 字段说明，用于在界面中展示配置提示
- `default_options["lines"]`: 处理扩展和分析扩展的顶层曲线选择协议

多曲线协议约定：

- 单曲线扩展：`{"lines": {"number": 1, "lines_list": "selected"}}`
- 双曲线扩展：`{"lines": {"number": 2, "lines_list": "selected"}}`，界面会显示“主曲线 / 副曲线”两个下拉框
- 多曲线扩展：`{"lines": {"number": -1, "lines_list": "selected"}}` 或 `{"lines": {"number": -1, "lines_list": "all"}}`
- `lines_list` 也可直接写成显式序号列表，例如 `[1, 3, 4]`
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
            default_options={
                "lines": {"number": 1, "lines_list": "selected"},
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