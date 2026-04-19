# ALine 扩展使用说明

ALine 会在启动时自动加载 `extensions/*.py`。当前支持 5 类扩展：

- `ProcessingExtension`: `(xs, ys, params) -> (xs, ys)`
- `AnalysisExtension`: `(inputs, params) -> result_dict`
- `PlotExtension`: 兼容旧签名 `(axis, series, options)`，推荐使用新签名 `(plot_context, options)`
- `PlotStyleExtension`: `(figure_state_dict, options) -> figure_state_dict`
- `CurveStyleExtension`: `(curve_style_dict, options) -> curve_style_dict`

## 1. 目录约定

- 扩展文件放在当前工作区的 `extensions` 目录。
- 文件名建议使用 `snake_case.py`。
- 以下划线开头的 Python 文件不会被自动加载。
- 不再维护单独的 JSON 示例文件。示例配置统一写在每个扩展的 `default_options` 里，界面中的“重置配置”会回填这份默认 JSON。

当前仓库自带 5 个纯 Python 示例：

- `processing_scale_demo.py`: 处理扩展，演示倍率缩放和基线偏移
- `analysis_peak_span_demo.py`: 分析扩展，返回峰谷跨度和样本数
- `plot_reference_line_demo.py`: 详细的 matplotlib 上下文式绘图扩展示例
- `plot_style_presentation_demo.py`: 绘图样式扩展，统一线宽、点大小和网格
- `curve_style_highlight_demo.py`: 曲线样式扩展，突出当前选中曲线

修改 `extensions/*.py` 后，不需要重启应用。处理页、分析页、图表页右侧扩展面板都有“重载扩展”按钮，点击即可重新扫描。

## 2. 入口函数

每个扩展文件都必须导出：

```python
def register_extensions(registry):
    ...
```

ALine 会把 `ExtensionRegistry` 实例传给这个函数，由扩展自行完成注册。

## 3. 配置如何进入扩展

扩展面板里的 JSON 会在应用时原样传给处理函数：

- 处理扩展 / 分析扩展：作为 `params`
- 绘图扩展 / 绘图样式扩展 / 曲线样式扩展：作为 `options`

为了让界面正确展示字段说明，建议同时提供：

- `default_options`: 默认配置
- `config_fields`: 字段描述列表

扩展面板会按 `key: field_type; 可选/必选; description` 的格式展示这些字段，因此示例里不再依赖 `label`。

字段描述结构如下：

```python
ExtensionConfigField(
    key="factor",
    description="把当前 Y 值乘以这个倍率。",
    field_type="number",
    required=False,
    default=2.0,
    choices=(),
)
```

## 4. PlotExtensionContext 速览

推荐为 `PlotExtension` 使用上下文签名：

```python
def handler(plot_context, options):
    ...
```

`plot_context` 会提供这些常用字段：

- `figure` / `canvas`: 当前 matplotlib Figure 与画布
- `axis` / `axes`: 当前主轴与 Figure 中全部轴
- `visible_series`: 还未绘制前的可见曲线源数据
- `plotted_series`: 默认绘制后得到的曲线摘要
- `figure_state`: 当前绘图状态字典
- `plot_style_extras`: 样式扩展附加到图表页的额外 matplotlib 参数
- `theme_colors`: 当前主题下的背景色、前景色、网格色
- `phase`: `before_plot` 或 `after_plot`
- `skip_default_plot`: 设为 `True` 可跳过默认折线绘制
- `skip_default_formatting`: 设为 `True` 可跳过默认坐标轴格式化
- `skip_default_layout`: 设为 `True` 可跳过默认布局调整

这允许扩展在 `before_plot` 阶段放置参考区域、额外轴或自定义底图，也可以在 `after_plot` 阶段对已经画出的曲线做标注、统计摘要或二次装饰。

## 5. 详细 Matplotlib 示例

`plot_reference_line_demo.py` 是当前最完整的绘图扩展示例。它演示了 4 件事：

- 在 `before_plot` 阶段基于当前可见曲线计算均值，并绘制水平参考线
- 可选地绘制一段半透明参考带
- 在 `after_plot` 阶段找到最高点并添加注释
- 把统计摘要追加到标题中，同时保留 matplotlib 原生接口的兼容写法

核心写法类似这样：

```python
def draw_reference_overlay(plot_context, options):
    axis = plot_context.axis
    points = _visible_points(plot_context.visible_series)
    if not points:
        return

    mean_level = sum(point[2] for point in points) / len(points)

    if plot_context.phase == "before_plot":
        axis.axhline(mean_level, color="#C23B22", linestyle="--")
        return

    if plot_context.phase == "after_plot":
        peak_name, peak_x, peak_y = max(points, key=lambda item: item[2])
        axis.annotate(f"峰值: {peak_name}", xy=(peak_x, peak_y), xytext=(10, 12), textcoords="offset points")
```

如果你要做 `subplot`、`inset axes`、`colorbar`、极坐标或完全自绘整张图，也建议沿用这个上下文签名。

## 6. 最小可运行示例

```python
from core.extension_api import ExtensionConfigField, ProcessingExtension


def scale_y(xs, ys, params):
    factor = float(params.get("factor", 1.0))
    return list(xs), [float(value) * factor for value in ys]


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="scale_y",
            name="Y 倍率缩放",
            handler=scale_y,
            description="按给定倍率缩放 Y 值。",
            default_options={"factor": 2.0},
            config_fields=[
                ExtensionConfigField(
                    key="factor",
                    description="把当前 Y 值乘以这个倍率。",
                    field_type="number",
                    default=2.0,
                )
            ],
        )
    )
```

## 7. 调试建议

- 扩展没有出现在界面里时，先检查文件是否位于 `extensions` 目录。
- 再检查是否实现了 `register_extensions(registry)`。
- 最后检查 `type` 是否唯一；重复的 `type` 会覆盖旧扩展。
- 如果扩展面板 JSON 解析失败，界面会提示配置必须是合法 JSON 对象。
- 如果是绘图扩展，优先确认 `phase` 是否符合你的绘制时机。

## 8. 程序化调用

- 手动加载目录：`extension_registry.load_from_directory("./extensions")`
- 处理扩展：`processing.data_engine.apply_operation(..., {"type": "scale_y", "params": {"factor": 2}})`
- 分析扩展：`core.analysis_engine.run_analysis("peak_span", inputs, params)`