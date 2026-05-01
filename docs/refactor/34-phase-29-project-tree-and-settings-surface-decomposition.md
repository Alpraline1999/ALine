# Phase 29：共享项目树与设置面深拆

## 目标与完成定义

目标：

- 对 `project_tree.py` 与 `settings_page.py` 这两类高复杂度 UI 入口做第二轮结构拆分。
- 把树委托、菜单、动作分发、目标锁定、设置页 tab/section 构建与主题 support 从壳层类中继续提取出去。
- 降低共享项目树和设置页继续吸纳新逻辑的风险。

完成定义：

- `ProjectTreeWidget` 不再同时承担节点构建、绘制、菜单生成、命令桥接、导入导出目标绑定和显示模式细节。
- `SettingsPage` 的 tab/section 构建、扩展面板 support、主题 support 至少分离到明确的 support 模块。
- 新模块边界与测试入口清晰，后续修复不需要再在 2000+ 行文件中横跳。

## 进入前提

- `Phase 28` 已固定 settings style/lifecycle contract。
- 当前已知结构性问题明确存在：
  - `ui/widgets/project_tree.py` 仍然超大且职责混杂。
  - `ui/pages/settings_page.py` 已完成功能扩展，但仍承担过多组装与主题细节。

## 本阶段纳入的范围

- `ui/widgets/project_tree.py` 及其直接 support/helper/delegate/menu/command 相关模块
- `ui/pages/settings_page.py` 及其 tab/section/support 模块
- 与两者直接相关的窄范围测试

## 本阶段不纳入的范围

- 业务算法优化
- `ProjectManager` / `command_layer` 的服务层拆分
- `data_page.py` / `chart_page.py` 的深层拆分

## 本阶段禁止事项

- 禁止为了拆文件而重写树节点模型或页面交互语义。
- 禁止把新 support 模块做成仅转发一层再返回壳层的空壳文件。
- 禁止把样式、命令、绘制和节点数据重新耦合回单个 helper。

## 核心问题清单

- `ProjectTreeWidget` 仍然是视图、控制器、菜单工厂、delegate 行为宿主和导入导出入口的复合体。
- `SettingsPage` 的 general/extensions/shortcuts/AI tab 构建与 support 逻辑都留在一个文件中，阅读和局部修改成本偏高。
- 共享 UI surface 没有被拆到足够细，导致后续任一小 bug 都容易跨越多个无关关注点。

## 实施顺序

1. 先按“纯 support / 纯构建 / 纯 delegate / 纯命令桥接”给 `ProjectTreeWidget` 划分边界。
2. 提取 `SettingsPage` 的 tab/section builder 与扩展设置 support。
3. 收口两侧壳层类的公开接口，只保留真正的页面/控件入口。
4. 补齐按模块定位的窄测，不再只从巨型壳层入口验证。

## 验收标准

- `project_tree.py` 和 `settings_page.py` 的壳层文件明显缩短，且职责描述可一句话概括。
- 至少下列关注点被拆出独立模块：
  - 项目树 delegate / 绘制 support
  - 项目树上下文菜单与命令映射
  - 设置页 tab/section builder
  - 设置页扩展面板或主题 support
- 壳层类不再直接操作大量跨关注点私有细节。

## 提交检查点

- 检查点 1：`ProjectTreeWidget` 拆分边界确定并完成第一批 support 提取。
- 检查点 2：`SettingsPage` tab/section/support 拆分完成。
- 检查点 3：壳层瘦身、窄测与阶段验收提交完成。

## 风险与回退

风险：

- 若先拆文件再补测试，容易把树菜单或设置页行为悄悄改坏。
- 若 support 模块切分过细，会制造新的薄转发层。

回退方式：

- 若某次拆分导致行为回退，先回退到上一稳定边界，保留已证明有收益的 support 提取。
- 若发现某个模块仅剩薄转发职责，应合并回最近的真实宿主，而不是保留空壳。

## 延后到后续阶段的问题

- `ProjectManager`、`ai.command_layer`、`data_page.py`、`chart_page.py` 的大型拆分延后到 `Phase 32`。
