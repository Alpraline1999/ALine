# 优化 02：处理页多曲线输入不足时提示精简

## 问题描述

处理页在执行多曲线处理扩展时，如果输入曲线数量不足，当前会弹出一个大段报错对话框，
打断用户操作流程。用户希望改为仅显示一段小提示（如 InfoBar 警告），不弹大对话框。

## 当前调用链

```
process_page 运行 pipeline
  └─ data_engine.apply_pipeline_to_lines()
      └─ _validate_multiline_processing_extension()
          └─ raise ValueError(f"{ext.name} 至少需要 {min_lines} 条输入曲线")
              └─ 异常被 process_page 捕获
                  └─ show_error() → QMessageBox / 大段报错
```

## 根因

`_validate_multiline_processing_extension()` (data_engine.py L371-380) 直接 `raise ValueError`，
异常在 `process_page` 中被 `show_error()` 捕获并以弹窗显示。`show_error` 使用 Qt 模态对话框。

## 方案

修改 `process_page` 中捕获该异常的代码，将 `show_error` 替换为 `InfoBar.warning`：
- 在 process_page 的执行路径中识别"多曲线输入不足"的 `ValueError`
- 捕获后用 `InfoBar.warning` 显示简短提示文字
- 不打断用户操作

## 验收

- 处理页在输入曲线不足时运行多曲线扩展，显示简洁的 InfoBar 提示而非弹窗
- 其他真实的处理错误仍保持弹窗
