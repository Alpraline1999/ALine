# Phase 13：项目树拖拽移动回归修复与拖放守护

## 目标与完成定义

目标：

- 修复项目树节点拖拽移动时报错的回归问题，恢复单选/多选拖放移动能力。
- 为重构后 `ProjectTreeWidget` 与 drag-drop helper 之间的接口漂移建立最小守护，避免类似错误再次进入运行时。

完成定义：

- 拖拽移动节点时不再触发 `ProjectTreeDragDropHelper` 缺失方法的异常。
- 单节点拖放、多节点拖放、跨项目阻止、非法目标阻止等基础行为保持可用。
- `project_tree.py`、`project_tree_view.py`、`project_tree_drag_drop.py` 之间的 helper 接口命名统一，不再混用旧私有名称和新公开名称。
- 增加最小窄测试或结构检查，覆盖拖放 helper 的关键调用面。

## 当前审查结论

这个问题已经定位到明确根因，不是 Qt 事件偶发现象。

已确认现状：

- `ui/widgets/project_tree_drag_drop.py`
  - helper 当前提供的方法名是：
    - `drag_source_item_for_drop()`
    - `drag_source_items_for_drop()`
  - 但 `perform_drop_move()` 内部仍调用旧名 `_drag_source_item_for_drop()`。
- `ui/widgets/project_tree.py`
  - 外层壳层仍保留 `_drag_source_item_for_drop()` 兼容包装，并委托给 helper 的 `drag_source_item_for_drop()`。
- `ui/widgets/project_tree_view.py`
  - `dropEvent()` 已走新的 owner 包装链路。

因此当前异常本质是：

- 拖放 helper 从 widget 内部逻辑拆出后，外部包装层和 helper 自身方法名没有完全同步。
- 旧私有命名残留在 helper 内部，运行到实际拖放路径时才暴露为 `AttributeError`。

## 主要问题

### 1. helper 内部仍残留已失效的旧私有调用

影响：

- 单节点拖放在真正落到 `perform_drop_move()` 时直接崩溃。
- 这类错误无法通过“页面能打开”或“树能显示”被提前发现。

### 2. 拖放链路跨 3 个模块，接口边界缺少一致性约束

影响：

- `ProjectTreeView` -> `ProjectTreeWidget` -> `ProjectTreeDragDropHelper` 的链路中，任一层改名都可能留下未同步残片。
- 重构阶段已经把逻辑拆开，但运行时接口守护仍然偏弱。

### 3. 当前缺少拖放路径的最小自动覆盖

影响：

- 即使 `MainWindow`、`ProjectTreeWidget` 的导入烟测通过，也挡不住“拖一下就炸”的行为回归。
- 后续继续优化项目树右键、拖拽、批量移动时风险会持续升高。

## 推荐优化方向

### A. 统一拖放 helper 的公开命名与内部调用

建议原则：

- helper 内部只使用自身公开 API 或明确的内部私有 API，不能混杂“旧 widget 私有方法名”。
- `ProjectTreeWidget` 只保留必要的 owner 包装，不再承担“为 helper 修补旧命名”的隐性兼容责任。

优先建议：

- 统一到一套命名：
  - `drag_source_item_for_drop()`
  - `drag_source_items_for_drop()`
  - `remember_drag_source_item(s)`
  - `clear_drag_source_item()`

### B. 给拖放路径补最小行为测试

建议覆盖：

- helper 记住拖放源后，单节点 drop 使用 remembered item
- 多节点 drop 使用 remembered items
- helper 在非法目标、跨项目目标时返回 `False`
- `dropEvent()` 完成后会清理 drag source 状态

测试可以以 helper / owner stub 为主，不必做完整 GUI 拖拽模拟。

### C. 把“接口漂移检查”纳入现有守护栏

建议方向：

- 若 `scripts/structure_check.py` 已承担“重构后接口漂移”的基础守护，可考虑把项目树拖放链路纳入轻量检查清单。
- 至少保证：
  - owner 需要的方法在 helper 侧存在
  - helper 自身不再调用已经不存在的旧名称

这类检查不必做成复杂 AST 工具，优先保证低成本和稳定性。

### D. 顺带校正拖放交互的一致性验收

因为本次问题发生在运行时主链路，修复阶段应顺带验证：

- 单选拖放
- 多选拖放
- 拖放完成后的选中恢复
- 拖放失败时的状态清理
- source file drop 与节点 move 两条路径不互相污染

## 验收标准

- 项目树节点拖拽移动不再抛出 `_drag_source_item_for_drop` 缺失异常。
- 单节点和多节点拖放都能走通或被正确拒绝。
- helper / widget / view 三层接口命名统一。
- 新增拖放路径窄测试或等价守护，并稳定通过。

## 本阶段不纳入的范围

- 项目树整体重设计
- 新增复杂拖放预览动画
- 全量项目树自动化 UI 测试
- 批量移动规则扩展

## 风险与回退

风险：

- 如果只补一个同名别名方法而不统一命名，后续仍可能在其他拖放分支残留旧调用。
- 如果把拖放测试做成完整 Qt 事件回放，维护成本会过高。

回退方式：

- 先统一命名与最短行为链路。
- 先做 helper 级和 owner stub 级窄测试，再视需要补一条轻量 UI smoke。
