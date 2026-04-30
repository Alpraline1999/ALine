# Phase 7 Task 3

## 阶段

- Phase 7 / ui-state-performance-and-polish

## 对应方案

- `docs/refactor/08-phase-7-ui-state-performance-and-polish.md`

## 目标

- 为数字化页自动检测建立后台执行路径。
- 避免自动检测在主线程里直接阻塞界面响应。

## 本任务范围

- 将数字化页自动检测改为后台执行。
- 保留现有“检测中”“应用”“取消预览”的交互。
- 取消操作只需要忽略尚未返回的检测结果，不强求终止底层计算。

## 验证

- `./.venv/bin/python -m unittest tests.test_digitize_auto_detect tests.test_ui_smoke`
- `./.venv/bin/python -m py_compile ui/pages/digitize_page.py tests/test_digitize_auto_detect.py`

## 完成判定

- 数字化页自动检测不再占用主线程完成整段计算。
