# Phase 22 Task 2

## 阶段

- Phase 22 / large-workspace-performance-and-data-virtualization

## 对应方案

- `docs/refactor/26-phase-22-large-workspace-performance-and-data-virtualization.md`

## 目标

- 修复上轮重构留下的运行时导入回归，并在图表热路径加入低风险降采样，降低超大曲线渲染阻塞。

## 本任务范围

- `extensions/processing/smooth.py`
- `extensions/processing/resample.py`
- `ui/pages/process_page.py`
- `core/rendering.py`
- `ui/pages/chart_page.py`
- `tests/test_rendering.py`

## 不纳入

- 全量 UI 回归测试
- 全仓 list-to-numpy 重写
- 项目文件格式重写

## 验证

- `./.venv/bin/python -m py_compile extensions/processing/smooth.py extensions/processing/resample.py ui/pages/process_page.py core/rendering.py ui/pages/chart_page.py tests/test_rendering.py`
- `./.venv/bin/python -m unittest tests.test_rendering`

## 完成判定

- 扩展导入回归消失，应用可正常启动到相关页面。
- 大曲线渲染在超阈值时自动降采样，小数据路径保持不变。
