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

仓库内已经附带一组可直接加载的示例扩展与对应 JSON：

- `processing_scale_demo.py` / `processing_scale_demo.json`
- `analysis_peak_span_demo.py` / `analysis_peak_span_demo.json`
- `plot_reference_line_demo.py` / `plot_reference_line_demo.json`
- `plot_style_presentation_demo.py` / `plot_style_presentation_demo.json`
- `curve_style_highlight_demo.py` / `curve_style_highlight_demo.json`

其中 `.py` 文件会在启动时自动加载，`.json` 文件可直接作为扩展面板里的示例配置粘贴或另存。

处理页、分析页、图表页右侧扩展面板都带有“重载扩展”按钮；修改 `extensions/*.py` 后无需重启应用，点击该按钮即可重新扫描并刷新当前页面的扩展列表。

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
from core.extension_api import AnalysisExtension, ExtensionConfigField, PlotStyleExtension, ProcessingExtension


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

## 4.1 PlotStyleExtension 完整示例

```python
from core.extension_api import ExtensionConfigField, PlotStyleExtension


def presentation_style(state, options):
    updated = dict(state)
    updated["grid"] = bool(options.get("grid", True))
    updated["grid_alpha"] = float(options.get("grid_alpha", 0.28))
    updated["line_width"] = float(options.get("line_width", 2.2))
    updated["marker_size"] = float(options.get("marker_size", 5.5))
    updated["font_size"] = int(options.get("font_size", updated.get("font_size", 10)))
    updated["legend_font_size"] = int(options.get("legend_font_size", updated.get("legend_font_size", 8)))
    return updated


def register_extensions(registry):
    registry.register_plot_style(
        PlotStyleExtension(
            type="presentation_style",
            name="演示版绘图样式",
            handler=presentation_style,
            description="统一调高线宽、字号和网格透明度。",
            default_options={
                "grid": True,
                "grid_alpha": 0.28,
                "line_width": 2.2,
                "marker_size": 5.5,
                "font_size": 11,
                "legend_font_size": 9,
            },
            config_fields=[
                ExtensionConfigField(key="grid", label="显示网格", field_type="boolean", default=True),
                ExtensionConfigField(key="grid_alpha", label="网格透明度", field_type="number", default=0.28),
                ExtensionConfigField(key="line_width", label="线宽", field_type="number", default=2.2),
                ExtensionConfigField(key="marker_size", label="点大小", field_type="number", default=5.5),
                ExtensionConfigField(key="font_size", label="字号", field_type="integer", default=11),
                ExtensionConfigField(key="legend_font_size", label="图例字号", field_type="integer", default=9),
            ],
        )
    )
```

## 4.2 CurveStyleExtension 完整示例

```python
from core.extension_api import CurveStyleExtension, ExtensionConfigField


def highlight_curve(style, options):
    updated = dict(style)
    updated["color"] = str(options.get("color", updated.get("color") or "#D13438"))
    updated["linestyle"] = str(options.get("linestyle", updated.get("linestyle") or "-"))
    updated["linewidth"] = float(options.get("linewidth", updated.get("linewidth", 1.6)))
    updated["marker"] = str(options.get("marker", updated.get("marker") or "o"))
    updated["marker_size"] = float(options.get("marker_size", updated.get("marker_size", 5.0)))
    updated["alpha"] = float(options.get("alpha", updated.get("alpha", 1.0)))
    updated["markevery"] = int(options.get("markevery", updated.get("markevery", 1)))
    return updated


def register_extensions(registry):
    registry.register_curve_style(
        CurveStyleExtension(
            type="highlight_curve",
            name="重点曲线高亮",
            handler=highlight_curve,
            description="统一设置颜色、线型、点型与采样密度。",
            default_options={
                "color": "#D13438",
                "linestyle": "-",
                "linewidth": 2.4,
                "marker": "o",
                "marker_size": 5.0,
                "alpha": 1.0,
                "markevery": 1,
            },
            config_fields=[
                ExtensionConfigField(key="color", label="颜色", field_type="string", default="#D13438"),
                ExtensionConfigField(key="linestyle", label="线型", field_type="string", default="-"),
                ExtensionConfigField(key="linewidth", label="线宽", field_type="number", default=2.4),
                ExtensionConfigField(key="marker", label="点型", field_type="string", default="o"),
                ExtensionConfigField(key="marker_size", label="点大小", field_type="number", default=5.0),
                ExtensionConfigField(key="alpha", label="透明度", field_type="number", default=1.0),
                ExtensionConfigField(key="markevery", label="标记密度", field_type="integer", default=1),
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