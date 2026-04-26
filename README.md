# ALine

ALine 是一款面向科研绘图数据重建、曲线处理、分析与出图的桌面应用。它以项目为单位管理图像、曲线、处理结果、分析结果和图表配置，并通过 Python 扩展系统开放处理、分析、绘图与数字化能力。

## 主要能力

- 图像数字化：导入图片，完成坐标校准、自动取点、手动修正和蒙版辅助识别。
- 数据管理：以项目树组织图像、曲线、处理结果、分析结果、图表与全局资源。
- 曲线处理：裁剪、重采样、平滑、滤波、归一化、积分、微分、FFT、双曲线计算等。
- 分析报告：统计、相关性、误差比较、峰值检测、曲线拟合、频谱分析与多曲线相关性。
- 图表编辑：管理曲线样式、图表主题、参考线、标注、双曲线差异带、极坐标投影等。
- 扩展系统：按处理、分析、绘图、数字化四类加载内置或外部 Python 扩展。
- AI 辅助：项目上下文、命令层与工具执行器为后续智能工作流提供基础。

## 基本流程

1. 在主页创建或打开项目。
2. 在数字化页导入图像并完成坐标校准。
3. 使用自动取点、画笔蒙版和手动编辑生成曲线。
4. 在数据页检查、重命名、分组和管理曲线资源。
5. 在处理页对曲线执行非破坏式处理流水线。
6. 在分析页生成统计结果、表格、摘要和报告占位符。
7. 在绘图页配置图表样式、应用绘图扩展并导出结果。
8. 在设置页管理主题、扩展、快捷键、AI 与全局偏好。

## 页面介绍

### 主页

主页用于创建、打开和恢复最近项目。页面会展示当前工作入口、最近项目、文档与扩展社区入口，适合从零开始或快速回到正在处理的数据集。

### 数字化页

数字化页负责从图片中提取曲线点。它支持坐标系选择、普通坐标校准、极坐标校准、自动取点、形状检测、颜色取样、截图模板、画笔蒙版大小调节以及手动点编辑。数字化扩展的输出统一为 point-list `line = [[x, y], ...]`。

### 数据页

数据页集中管理项目中的曲线与资源。它展示项目树、曲线列表、元数据和全局资源节点。专注模式下仍会展示全部节点，包括全局资源，避免用户在跨页面整理资源时丢失上下文。

### 处理页

处理页面向曲线流水线。每次处理会基于原始曲线生成新的结果，不直接覆盖已有数据。处理扩展统一签名为 `(lines, params) -> line`，多曲线工具通过 `lines_number` 和 `lines_list` 明确输入顺序。

### 分析页

分析页用于生成可读结果，包括摘要项、结果表、说明文本、可绘制结果曲线和报告模板占位符。分析扩展统一签名为 `(lines, params) -> dict`。

### 绘图页

绘图页用于配置最终图表，包括坐标轴、图例、曲线样式、注释、参考线、差异带和科学绘图风格。绘图扩展统一签名为 `(lines, params) -> None`，只操作当前 matplotlib 图元。

### 设置页

设置页负责主题、界面偏好、扩展启停、扩展参数、快捷键和 AI 配置。扩展管理区域会根据注册元数据展示版本、来源、工具层级和可配置字段。

## 扩展系统概览

ALine 扩展位于 `extensions/`，按功能分为：

- `extensions/processing/`：处理扩展。
- `extensions/analysis/`：分析扩展。
- `extensions/plot/`：绘图扩展。
- `extensions/digitize/`：数字化扩展。

正式曲线协议为 point-list：

```python
line = [[0.0, 1.0], [1.0, 2.0], [2.0, 4.0]]
lines = [line, ...]
```

扩展内部如需从 `x_list` 与 `y_list` 生成曲线，必须调用：

```python
from processing.extension_tools import line_from_xy, line_xy

line = line_from_xy(xs, ys)
xs, ys = line_xy(line)
```

四类扩展契约：

| 类型 | 签名 | 输出 |
| --- | --- | --- |
| 处理扩展 | `(lines, params)` | `line` |
| 分析扩展 | `(lines, params)` | `dict` |
| 绘图扩展 | `(lines, params)` | `None` |
| 数字化扩展 | `(figure, params)` | `line` |

完整扩展编写文档见 [extensions/README.md](extensions/README.md)。

## 内置接口示例扩展

仓库包含四个可加载、可测试的接口示例扩展：

- `interface_contract_processing`：展示处理扩展输入、参数字段和 line 输出。
- `interface_contract_analysis`：展示分析扩展 dict 输出、表格、摘要、文本和报告占位符。
- `interface_contract_plot`：展示绘图扩展对当前图表图元的修改。
- `interface_contract_digitize`：展示数字化扩展、figure 输入、pickcolor、shot 和 line 输出。

这些扩展位于对应的 `extensions/*/interface_contract_*.py` 文件中，并标记为 `experimental`。

## 开发与测试

推荐使用项目虚拟环境运行测试：

```bash
/home/alpraline/Projects/Python/ALine/.venv/bin/python -m pytest
```

常用窄测：

```bash
/home/alpraline/Projects/Python/ALine/.venv/bin/python -m pytest tests/test_backend.py -q
/home/alpraline/Projects/Python/ALine/.venv/bin/python -m pytest tests/test_ui.py -q
```

开发约束：

- 不删除既有功能，只做协议收口、实现优化或公共工具抽象。
- 扩展边界不保留旧输入输出兼容。
- 内置扩展和未来新增扩展都遵守 point-list 曲线协议。
- 稳定底层接口包括 `line_from_xy`、`align_lines_to_common_x`、`crop_xy`、`transform_xy`、`resample_xy`。
