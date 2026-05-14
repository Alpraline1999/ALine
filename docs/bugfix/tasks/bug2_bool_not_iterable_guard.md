# Bug 2 Task: 所有分析扩展运行报错 "bool object is not iterable"

## 问题描述

所有分析扩展（统计分析、相关性分析、频谱分析等）运行时均报错：
```
TypeError: 'bool' object is not iterable
```

## 触发场景

任何分析扩展被调用时均可能触发（内置 + 自定义）。

## 根因

`normalize_lines()` 和 `series_payloads_to_curve_batch()` 未防护 bool 类型输入。

### `normalize_lines()` 在 `core/line_tools.py:78`

```python
def normalize_lines(raw: Any) -> List[Line]:
    if raw in (None, "", [], ()):
        return []
    return [normalize_line(item) for item in list(raw)]  # BOOM if raw=True/False
```

`True in (None, "", [], ())` 为 `False`（因为 `True == 1`，不等于任何元素），所以 `list(True)` 引发 `TypeError`。

### `series_payloads_to_curve_batch()` 在 `core/curve_data.py:166`

```python
def series_payloads_to_curve_batch(raw: Any) -> list[CurveBuffer]:
    if raw is None: return []
    if isinstance(raw, str) and not raw.strip(): return []
    if isinstance(raw, (list, tuple)) and len(raw) == 0: return []
    return [series_payload_to_curve_buffer(item) for item in raw]  # BOOM if raw=True
```

`True` 不是 `None`，不是 `str`，`isinstance(True, (list, tuple))` 为 `False`，所以进入 `for item in True` → TypeError。

### 扩散路径

1. 分析扩展 handler 返回 dict 中 `"lines"` 或 `"_plot_series"` 键的值为 `True`/`False`
2. 或 UI 层 result dict 中某键被赋 bool 值
3. 或 `params` 传递过程中 bool 值渗入 `lines` 参数
4. 上述函数未做 bool 防护 → `list(raw)` 或 `for item in raw` 直接崩溃

## 修复要求

### 1. `normalize_lines()` 添加 bool 防护

**文件**: `core/line_tools.py`
**位置**: 函数开头
**修改**: 增加 `isinstance(raw, bool)` 检查，遇到 bool 返回 `[]`

### 2. `normalize_line()` 添加 bool 防护

**文件**: `core/line_tools.py`
**位置**: 函数开头  
**修改**: 增加 `isinstance(raw, bool)` 检查，遇到 bool 返回 `[]`

### 3. `series_payloads_to_curve_batch()` 添加 bool 防护

**文件**: `core/curve_data.py`
**位置**: 函数开头
**修改**: 增加 `isinstance(raw, bool)` 检查，遇到 bool 返回 `[]`

### 4. `SeriesArrayView.__init__` 适当处理 bool（可选）

**文件**: `core/curve_data.py`
**位置**: `__init__` 方法
**修改**: `np.asarray(True)` 返回 `array(True)`（0维），后续 `reshape(-1)` 后变 1 维。这一般不会直接引发 bool 迭代错误，但可增加防御性处理。

## 验收标准

- [ ] `normalize_lines(True)` 返回 `[]`，不抛出异常
- [ ] `normalize_lines(False)` 返回 `[]`，不抛出异常
- [ ] `series_payloads_to_curve_batch(True)` 返回 `[]`
- [ ] `series_payloads_to_curve_batch(False)` 返回 `[]`
- [ ] `normalize_line(True)` 返回 `[]`
- [ ] 分析扩展正常运行，不再抛出 bool 迭代错误
- [ ] backend 回归全部通过
