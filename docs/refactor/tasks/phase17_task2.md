# Phase 17 Task 2

## 阶段

- Phase 17 / domain-flow-and-analytical-workbench-normalization

## 对应方案

- `docs/refactor/20-phase-17-domain-flow-and-analytical-workbench-normalization.md`

## 目标

- 将导入预览文件类型分发从对话框类中提成一个薄 parser 对象，收口导入流程边界。

## 本任务范围

- `ui/dialogs/import_dialog.py`

## 不纳入

- 完整导入向导重写
- 数据解析算法变更
- 测试框架改造

## 验证

- 聚焦 `import_dialog` 的 `py_compile`
- 只跑导入对话框相关的窄测

## 完成判定

- 导入预览分发逻辑不再散在对话框流程里。
- 新 parser 作为薄边界对象可被直接调用。
