# 优化 04：修复分析扩展非 dict 返回值导致崩溃

## 问题描述

所有分析扩展在运行时报错 `bool object is not iterable`。根因：

当分析扩展的 handler 返回 `True` / `False`（bool）而非 `dict` 时，
`analysis_page.py` 的 `_show_result()` 执行 `view["result"] = dict(r)`，
`dict(True)` 会抛出 `TypeError: 'bool' object is not iterable`。

## 当前调用链

```
handler(lines, params) → returns True (bool)  ← 扩展实现错误
  └─ invoke_analysis_extension_handler()       ← 虽然检查了 not isinstance(result, dict) 并返回了 bool
      └─ run_analysis()                        ← cast 成 Dict 但实际是 bool
          └─ _on_analysis_finished()           ← self._result = bool
              └─ _show_result() → dict(r)      ← TypeError: 'bool' object is not iterable
```

## 方案

1. 在 `invoke_analysis_extension_handler` 中：当 handler 返回非 dict 时，
   记录 warning 并返回包含错误信息的 dict 而不是原始 bool
2. 在 `_show_result` 中：安全地处理非 dict result（防御性编程）

## 验收

- 任何分析扩展 handler 返回 bool 时，不再崩溃
- 在状态栏显示清晰的错误提示而非 "bool object is not iterable"
