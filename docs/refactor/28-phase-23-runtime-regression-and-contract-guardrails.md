# Phase 23：运行时回归恢复与契约护栏

## 目标与完成定义

目标：

- 针对 `Phase 18` 到 `Phase 22` 期间引入的运行时回归和契约漂移做一次集中收口。
- 把“页面方法签名 / workspace state proxy / command service 绑定回调 / 过期测试契约”这类 late-stage refactor 常见断点补上护栏。
- 清理已确认的死代码和过期测试前提，避免下一轮性能或结构优化建立在不稳定接口上。

完成定义：

- 最近一轮已暴露的运行时回归类型有对应护栏：
  - 回调签名漂移
  - 页面 state proxy 漏接
  - 扩展 handler / runtime 测试契约过期
- `core.extension_api` 中已确认的死私有函数被删除或明确转移到唯一活跃实现。
- 至少一组共享命令 / 页面 / 扩展回归拥有可重复的窄测，而不是只靠手工点击验证。

## 进入前提

- `Phase 22` 已完成基础性能样本与首轮优化。
- 以 `2026-05-01` 的运行时问题为证据进入本阶段：
  - 项目树右键导入数据文件时 `configure_source_file_import_target` 与 widget 方法签名漂移。
  - `AnalysisPage` 保存分析结果时 `_selected_tree_node_id` state proxy 断开。
  - 专家审查指出 `tests/test_backend.py` 中 plot extension handler 测试契约过期。

## 本阶段纳入的状态与边界

- 纳入：
  - `ProjectTreeCommandService` 与 `ProjectTreeWidget` 的回调绑定面
  - `AnalysisPage` / `ProcessPage` / 同类页面的 workspace state proxy
  - `core.extension_api` / `core.extension_runtime` 的重复私有归一化逻辑
  - 已过期的扩展运行时测试与命令层窄测
- 不纳入：
  - 大规模性能重写
  - `project_tree.py` 深拆
  - 全量 UI 回归

## 本阶段禁止改动的区域

- 禁止借“修回归”之名扩张为另一轮大规模页面拆分。
- 禁止没有测试补位就继续移动 service / widget 回调边界。
- 禁止把死代码清理与协议改写混成一次大提交。

## 目标接口/类型/运行时对象

- `ProjectTreeCommandService`
- `AnalysisWorkspaceState`
- `invoke_plot_extension_handler`
- `invoke_processing_extension_handler`
- `HAS_MATPLOTLIB` / `_HAS_MPL` 一致性约定

## 实施顺序

1. 收集最近一轮实际运行时回归并补窄测。
2. 修复页面 state proxy 与 service 回调签名漂移。
3. 删除或收口 `extension_api` 中已确认死私有函数。
4. 更新过期的扩展运行时 / 命令层测试契约。
5. 固定 late-stage refactor 的最小护栏文档。

## 核心问题清单

- widget 在初始化时把方法绑定进 service，后续仅 patch widget 方法并不能覆盖实际回调链路，测试很容易失真。
- 页面从私有属性迁到 workspace state 后，若缺少 property proxy，很容易在保存、导出、目标定位等长尾路径上回归。
- 一部分扩展测试仍停留在 `Phase 10` 之前的旧 handler 签名，无法真实保护当前 runtime。
- `core.extension_api` 与 `core.extension_runtime` 之间仍有少量重复私有逻辑和死代码，增加认知噪声。

## 子阶段建议

### 23.1 Runtime Regression Sweep

目标：

- 收口最近一轮已确认的运行时异常与回调签名漂移。

验收要点：

- 用户已报告的回归有窄测覆盖。
- service 与 widget 绑定点的真实调用链被测试命中。

### 23.2 Contract And Test Guardrails

目标：

- 更新扩展 runtime、plot handler、命令层的过期测试契约。

验收要点：

- 旧 mock 签名不再误导当前运行时。
- 至少一条共享命令路径和一条扩展路径具备稳定窄测。

### 23.3 Dead Code And Small Consistency Cleanup

目标：

- 删除已确认死代码，统一少量低风险命名/常量不一致。

验收要点：

- `extension_api` / runtime 中不再保留已确认无消费者的重复私有函数。
- `HAS_MATPLOTLIB` 一致性问题得到处理或被明确登记为下一阶段任务。

## 验收标准

- 回归修复建立在实际报错和可执行窄测之上。
- 过期测试契约更新后，不再依赖旧 handler 签名。
- 死代码与一致性清理不扩大为结构性重写。

## 提交检查点

- 检查点 1：运行时回归窄测补位完成。
- 检查点 2：service / page state proxy 漂移收口完成。
- 检查点 3：过期测试契约与死代码清理完成。
- 检查点 4：阶段验收提交完成。

## 风险与回退办法

风险：

- 回调绑定与测试 patch 点不一致，容易误判“测试已覆盖”。
- 小范围契约修正若未隔离好，可能连带影响仍未更新的旧测试。

回退办法：

- 若某条回归无法稳定复现，先固定最小复现测试，再做代码修正。
- 若某处死代码删除牵动不明消费者，先回退删除，只保留文档登记和调用扫描。

## 延后到后续阶段的问题

- `project_tree.py` 深拆与菜单/命令 surface 模块化。
- 更深层的多曲线性能与共享数值 primitive 收口。
- 扩展覆盖矩阵系统化建设。
