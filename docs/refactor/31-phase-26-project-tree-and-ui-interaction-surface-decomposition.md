# Phase 26：项目树与 UI 交互面拆分硬化

## 目标与完成定义

目标：

- 继续收口共享项目树与若干页面之间的交互面，降低 `project_tree.py`、导入/导出入口和页面长尾交互的回归概率。
- 把“菜单生成、命令绑定、目标锁定、导入/导出对话框预配置、页面目标定位”这类混杂在 widget 内的大量细节动作继续拆回更稳定的 surface。
- 为后续更大规模的 UI monolith 收尾保留清晰边界，而不是把 late-phase 修补继续堆回主 widget。

完成定义：

- `project_tree.py` 至少一组高频交互面被提取或模块化：
  - 菜单 section 组装
  - source-file import / digitize import 绑定
  - tree command service 适配层
- 页面与项目树共享的“目标节点解析”约定被明确，减少页面内私有状态回退。
- 至少一条 UI 交互链路具备稳定窄测并命中真实 service 绑定点。

## 进入前提

- `Phase 25` 已完成测试契约和模块导出面收口。
- 以 `2026-05-01` 的问题与审查结果进入本阶段：
  - 项目树右键导入路径暴露出 callback 绑定与测试 patch 点不一致的问题。
  - `project_tree.py` 仍是超大交互面，专家审查也将其列为低风险但高价值的后续拆分目标。

## 本阶段纳入的状态与边界

- 纳入：
  - `ui/widgets/project_tree.py`
  - `app/project_tree_command_service.py`
  - 与树目标定位直接相关的 `AnalysisPage` / `ProcessPage` / `DataPage`
  - 导入/导出对话框的目标预配置 surface
- 不纳入：
  - 整体 UI 风格改版
  - 主窗口导航重构重来
  - 不相关的分析/处理算法优化

## 本阶段禁止改动的区域

- 禁止把 `project_tree.py` 深拆扩张为无边界的 UI 全面重写。
- 禁止为了“可测”而引入过度抽象的 service / adapter 层。
- 禁止修改项目树的业务语义，只允许收口交互面和边界。

## 目标接口/类型/运行时对象

- `ProjectTreeCommandService`
- `ProjectTreePageDispatcher`
- `WorkspaceTargetResolver`
- `ImportTargetBinding`
- `ExportTargetBinding`

## 实施顺序

1. 列清项目树当前高频交互链路与绑定点。
2. 抽离最容易回归的一组导入/导出/目标锁定 surface。
3. 统一页面对树选中节点、目标文件夹和保存目标的解析方式。
4. 为真实交互绑定点补窄测。

## 核心问题清单

- `project_tree.py` 仍同时承担菜单组织、动作绑定、service 组装、目标锁定和页面协调，交互面过宽。
- 页面保存/导入/导出目标经常从私有属性、workspace state、project manager helper 多处解析，容易产生状态漂移。
- 许多 UI 测试 patch 了 widget 方法，但真实运行时调用链已经下沉到 service，导致测试命中面失真。

## 子阶段建议

### 26.1 Tree Interaction Inventory

目标：

- 固定项目树当前的高频交互链路和真实绑定点。

验收要点：

- 菜单动作、service 绑定、页面回调三者的映射关系清晰可查。

### 26.2 Import/Export Target Surface Extraction

目标：

- 抽离 source-file import、digitize import、analysis save target 等高回归 surface。

验收要点：

- 至少一组目标锁定 / 目标解析逻辑被提取为更小的 helper 或 adapter。

### 26.3 Page Target Resolution Normalization

目标：

- 统一页面对树目标节点的解析方式。

验收要点：

- 页面对树选中节点的读取优先来自 workspace state 或统一 resolver，不再散落私有属性回退。

## 验收标准

- 项目树的至少一组高频交互面被实质性缩窄。
- 窄测命中真实 service 绑定点，而不是只 patch widget 表层方法。
- 页面目标定位不再依赖不稳定私有属性散点。

## 提交检查点

- 检查点 1：项目树高频交互 inventory 完成。
- 检查点 2：导入/导出 target surface 首轮抽离完成。
- 检查点 3：页面目标解析统一与窄测补位完成。
- 检查点 4：阶段验收提交完成。

## 风险与回退办法

风险：

- 树交互拆分若切点选错，可能让调用链更绕而不是更清晰。
- 页面目标解析统一若未充分验证，可能误伤保存/导出默认目标。

回退办法：

- 若某个抽离 helper 只增加间接层，不提升清晰度，则回退到 inventory 文档，不强推实现。
- 若目标解析统一引入行为差异，优先保留稳定路径并补更小范围 helper。

## 延后到后续阶段的问题

- 更大规模的 `project_tree.py` 文件拆分。
- `DataPage` 与 `project_tree` 之间更深层的浏览/选择协同。
- 主窗口级菜单、树路由与页面 surface 的进一步统一。
