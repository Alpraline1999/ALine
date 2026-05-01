# Phase 30 Task 1：数字化扩展单源化与包面收口

## 目标

- 将 `extensions/digitize/color_detect.py` 中重复的颜色提取实现收口到 `digitize.auto_extractor.AutoExtractor`。
- 让数字化 builtin 扩展明确复用共享 extractor，而不是继续维护私有拷贝。
- 用一个窄测锁定“builtin 扩展确实走共享实现”的行为，作为 Phase 30 的第一个可验证切片。

## 任务拆分

1. 删除 `extensions/digitize/color_detect.py` 中的私有 `_cv2_imread_unicode` 与 `AutoExtractor` 实现。
2. 直接导入并使用 `digitize.auto_extractor.AutoExtractor`。
3. 增补一个仅覆盖颜色数字化扩展共享 extractor 路径的窄测，避免后续再分裂实现。
4. 通过 `py_compile` 和相关后端窄测验证本次收口。
5. 使用 `important-change-commit` 为 Phase 30 建立检查点提交。

## 验收方式

- `py_compile` 通过。
- 新增窄测通过，且能证明 builtin color digitize 扩展复用共享 extractor。
- 提交说明清楚描述本次单源化收口的边界与验证结果。
