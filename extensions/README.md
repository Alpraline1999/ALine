# ALine 扩展使用说明

ALine 支持 5 类 Python 扩展，并且应用启动时会自动加载 `extensions/*.py`：

- `ProcessingExtension`: 数据处理扩展，签名为 `(xs, ys, params) -> (xs, ys)`
- `AnalysisExtension`: 数据分析扩展，签名为 `(inputs, params) -> result_dict`
- `PlotExtension`: 绘图扩展，签名为 `(axis, series, options) -> None`
- `PlotStyleExtension`: 绘图样式扩展，签名为 `(figure_state_dict, options) -> figure_state_dict`
- `CurveStyleExtension`: 曲线样式扩展，签名为 `(curve_style_dict, options) -> curve_style_dict`

## 1. 放置位置

- 把扩展文件放进当前工作区的 `extensions` 目录。
- 文件名建议使用 `snake_case.py`。
- 以下划线开头的文件不会被自动加载。

## 2. 必须提供的入口函数

每个扩展文件都必须导出：

```python
def register_extensions(registry):
    ...
```

ALine 会把 `ExtensionRegistry` 实例传进来，你在这个函数里完成注册。

## 3. 配置接口

扩展配置面板里的 JSON 会在应用扩展时原样传给扩展处理函数：

- 处理扩展 / 分析扩展：作为 `params`
- 绘图扩展 / 样式扩展：作为 `options`

扩展作者可以通过以下两个字段告诉 ALine 如何显示配置：

- `default_options`: 默认 JSON 配置
- `config_fields`: 配置字段说明列表，用于在右侧扩展面板显示字段帮助

可用的字段说明结构：

```python
ExtensionConfigField(
    key="factor",
    label="倍率",
    description="把当前 Y 值乘以这个倍率",
    field_type="number",
    required=False,
    default=2.0,
    choices=(),
)
```

## 4. 完整示例

```python
from core.extension_api import (
    AnalysisExtension,
    ExtensionConfigField,
    PlotStyleExtension,
    ProcessingExtension,
)


def scale_y(xs, ys, params):
    factor = float(params.get("factor", 1.0))
    return list(xs), [value * factor for value in ys]


def peak_span(inputs, params):
    source = inputs[0]
    values = list(source.get("y", []))
    return {
        "analysis_type": "peak_span",
        "source_name": source.get("name", ""),
        "span": (max(values) - min(values)) if values else 0.0,
        "unit": params.get("unit", "a.u."),
    }


def widen_plot_style(state, options):
    updated = dict(state)
    updated["line_width"] = float(options.get("line_width", updated.get("line_width", 1.6)))
    return updated


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="scale_y",
            name="Y 倍率缩放",
            handler=scale_y,
            description="按给定 factor 缩放 Y 值。",
            default_options={"factor": 2.0},
            config_fields=[
                ExtensionConfigField(
                    key="factor",
                    label="倍率",
                    description="把当前 Y 值乘以这个倍率。",
                    field_type="number",
                    default=2.0,
                )
            ],
        )
    )

    registry.register_analysis(
        AnalysisExtension(
            type="peak_span",
            name="峰谷跨度",
            handler=peak_span,
            description="返回输入序列的峰谷跨度。",
            default_options={"unit": "MPa"},
            config_fields=[
                ExtensionConfigField(
                    key="unit",
                    label="结果单位",
                    description="用于写入分析结果摘要。",
                    field_type="string",
                    default="MPa",
                )
            ],
        )
    )

    registry.register_plot_style(
        PlotStyleExtension(
            type="widen_plot",
            name="增粗绘图样式",
            handler=widen_plot_style,
            description="把当前绘图样式中的线宽提高到给定值。",
            default_options={"line_width": 2.4},
            config_fields=[
                ExtensionConfigField(
                    key="line_width",
                    label="线宽",
                    description="最终应用到 FigureState 的线宽。",
                    field_type="number",
                    default=2.4,
                )
            ],
        )
    )
```

## 5. 处理函数约定

- `ProcessingExtension.handler(xs, ys, params)`
  - 返回新的 `xs, ys`
  - 适合平滑、缩放、裁剪、重采样等操作

- `AnalysisExtension.handler(inputs, params)`
  - `inputs` 是字典列表，包含 `x/y/name` 等字段
  - 返回值必须是可序列化字典，建议至少包含 `analysis_type`

- `PlotExtension.handler(axis, series, options)`
  - `axis` 是 matplotlib 轴对象
  - `series` 是当前图上的序列列表
  - 适合额外绘制辅助线、阴影带、参考区间等

- `PlotStyleExtension.handler(state, options)`
  - `state` 是当前 `FigureState` 的字典副本
  - 返回修改后的字典

- `CurveStyleExtension.handler(style, options)`
  - `style` 是当前曲线样式字典副本
  - 返回修改后的字典

## 6. 调试建议

- 扩展没有出现在界面里时，先检查文件是否位于 `extensions` 目录。
- 再检查是否实现了 `register_extensions(registry)`。
- 最后检查 `type` 是否唯一，重复的 `type` 会覆盖旧扩展。
- 如果扩展面板 JSON 解析失败，界面会提示必须是合法 JSON 对象。

## 7. 程序化调用

- 手动加载目录：`extension_registry.load_from_directory("./extensions")`
- 处理扩展：`processing.data_engine.apply_operation(..., {"type": "scale_y", "params": {"factor": 2}})`
- 分析扩展：`core.analysis_engine.run_analysis("peak_span", inputs, params)`