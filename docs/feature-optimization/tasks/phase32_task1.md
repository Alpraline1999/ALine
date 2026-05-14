# Phase 32 Task 1: 分析运行时 bool 防御统一

## 目标

收口分析扩展 handler 输入/输出的 bool 防御，确保运行时入口不再把 bool 当作可迭代对象。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_runtime.py` | 审查并补齐分析结果字段归一化 |
| `core/analysis_engine.py` | 统一 `_ensure_list` 使用面 |
| `core/line_tools.py` | line/list 协议的 bool 防御复核 |
| `core/curve_data.py` | payload -> curve batch 的 bool 防御复核 |

## 验收清单

- [ ] 所有 list-like 字段都不会再触发 `list(True)`
- [ ] bool 不会再被隐式转换为合法曲线索引
- [ ] 运行时相关窄测通过
