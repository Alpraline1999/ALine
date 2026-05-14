# Optimization 02 Task：处理页多曲线输入不足时提示精简

## 对应方案

- `docs/optimization/02-processing-multiline-input-hint.md`

## 目标

将多曲线输入不足的弹窗报错改为 InfoBar 简短提示。

## 方案

1. 在 `process_page.py` 的运行 pipeline 的执行路径中，定位捕获 `ValueError` 的位置
2. 如果错误信息匹配"至少需要"模式，使用 `InfoBar.warning` 代替 `show_error`
3. 其他真实处理错误仍使用弹窗

## 涉及文件

- `ui/pages/process_page.py`

## 验收

- 多曲线输入不足时显示 InfoBar 提示，非弹窗
- 其他错误仍保持弹窗
