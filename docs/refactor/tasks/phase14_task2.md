# Phase 14 Task 2

## 阶段

- Phase 14 / redundancy-elimination-and-architectural-consistency

## 对应方案

- `docs/refactor/17-phase-14-redundancy-elimination-and-architectural-consistency.md`

## 目标

- 将 `ProjectManager` 中重复的备份/删除备份逻辑提炼为受控服务或等价结构。
- 保持项目文件协议、相对路径协议和删除语义不变。

## 本任务范围

- 提炼 image / picture / source_file 的备份路径生成、唯一化和复制逻辑。
- 提炼 managed backup 删除逻辑。
- 让 `ProjectManager` 仅保留薄包装和现有调用边界。

## 不纳入

- 项目文件协议变更
- 备份目录命名重构
- UI 层调整
- DataPage / shared widget 拆分
- 大规模测试或全量回归

## 验证

- 先做 `py_compile`，再做与项目保存/树删除相关的窄测。
- 不做全量回归测试。

## 完成判定

- 备份重复逻辑从 `ProjectManager` 主体中抽出。
- 保存与删除的行为在窄测中保持稳定。
- 为 `Phase 14` 的后续一致性收口保留清晰边界。
