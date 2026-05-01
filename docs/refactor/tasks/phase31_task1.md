# Phase 31 Task 1：曲线数组视图兼容性与质量门槛回绿

## 目标

- 修复 `SeriesArrayView` 在 numpy 2.0 下的 `__array__` 兼容性问题，消除 copy 弃用警告。
- 用最小测试固定曲线运行时数组视图的无警告转换行为，避免后续再次回退。
- 继续保持扩展层最小 smoke 覆盖，不引入全量回归。

## 任务拆分

1. 调整 `core/curve_data.py` 中 `SeriesArrayView.__array__` 的签名与行为，显式支持 `copy` 参数。
2. 增补 `tests/test_curve_data.py` 中关于 `np.array(view, copy=False)` 的无警告断言。
3. 用 `py_compile` 和曲线数据窄测验证本次兼容性修复。
4. 使用 `important-change-commit` 形成 Phase 31 检查点提交。

## 验收方式

- `py_compile` 通过。
- 曲线数据窄测通过，且不再产生 numpy copy 相关 warning。
- 提交说明清楚描述问题来源、兼容性修复和验证结果。
