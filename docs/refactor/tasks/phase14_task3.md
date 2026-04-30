# Phase 14 Task 3

## 阶段

- Phase 14 / redundancy-elimination-and-architectural-consistency

## 对应方案

- `docs/refactor/17-phase-14-redundancy-elimination-and-architectural-consistency.md`

## 目标

- 统一 matplotlib QtAgg 启动入口。
- 清理低风险一致性噪声：死转发层、错误 `__all__`、死别名、图片后缀不一致。

## 本任务范围

- 页面 support 模块中的 matplotlib 启动引导统一到单一函数。
- `core/ai/client.py` / `core/ai/config.py` 的零 importer 转发层收口。
- `core/extension_loader.py` 的错误导出面修正。
- `core/analysis_engine.py` 的死别名清理。
- `.gif` 后缀列表一致化。

## 不纳入

- 页面视觉重设计
- DataPage 深拆
- 业务流程重构
- 大规模静态清理

## 验证

- 先做 `py_compile`，再做架构护栏和 UI smoke 的窄测。
- 不做全量回归测试。

## 完成判定

- 页面 support 模块不再复制 QtAgg 启动代码。
- 死转发层与明显的导出噪声被清掉。
- 后缀和别名不一致问题被收口。
