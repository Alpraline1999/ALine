# Phase 33：Data Workspace 与 Project Tree Surface 深拆

## 目标与完成定义

目标：

- 继续处理 `DataPage`、`ProjectTreeWidget` 与 `MainWindow` 之间仍然过厚的页面壳层和路由边界。
- 把数据页中并存的 source browser、pending import、preview、global resource 管理等子系统继续拆离。
- 把项目树从“构建 + 菜单 + 对话框 + 拖放 + 页面分发”混合控件，收口为更稳定的 surface。

完成定义：

- `ui/pages/data_page.py` 不再同时承担数据浏览器、预览渲染、导入队列、资源管理和上下文菜单全链路实现。
- `ui/widgets/project_tree.py` 不再继续承载菜单装配、命令桥接、拖放规则、delegate 绘制和导入对话框细节的全集合实现。
- `ui/main_window.py` 对项目树激活/选中/页面路由的职责进一步收口，只保留页面切换和顶层编排。

## 进入前提

- `Phase 32` 已完成对剩余 monolith 的第一轮二次拆分。
- 项目树、数据页、主窗口当前运行链路已稳定，具备继续按职责深拆的前提。

## 本阶段纳入的范围

- `ui/pages/data_page.py`
- `ui/widgets/project_tree.py`
- `ui/main_window.py`
- `ui/pages/data_page_*`
- `ui/widgets/project_tree_*`
- 与上述 surface 直接相关的 page dispatcher / command service / support 模块

## 本阶段不纳入的范围

- 新的数据导入格式
- 新的项目树交互能力
- 数值算法与大曲线性能优化

## 本阶段禁止事项

- 禁止只做“搬文件式拆分”，但保留同样的壳层耦合。
- 禁止把树节点语义、目标节点推导、预览状态重新塞回 `MainWindow`。
- 禁止让 `DataPage` 再次直接增长为新的工作台编排中心。

## 核心问题清单

- `DataPage` 仍然同时负责 source manager、preview 模式切换、source file 分页、pending import 队列、全局资源预览和管理面刷新。
- `ProjectTreeWidget` 仍然混合了树构建、右键菜单、导入入口、拖放/移动规则、wrapped text delegate 和页面事件分发。
- `MainWindow` 仍保留较多树节点激活与页面转发细节，workspace routing 还不够薄。

## 实施顺序

1. 先拆 `ProjectTreeWidget`：
   - 提取 menu builder / import action binder / drag-drop policy / selection-routing support。
   - 明确树控件只负责 view + signal surface。
2. 再拆 `DataPage`：
   - 提取 source browser presenter / pending import coordinator / preview presenter / global asset preview support。
   - 保留页面壳层只做布局、状态桥接和高层命令接线。
3. 最后收口 `MainWindow`：
   - 统一树选择与页面激活协议。
   - 减少页面特判和中转命令分支。

## 验收标准

- `DataPage` 的新增修复不再需要同时触碰 preview、browser、resource 管理多个无关区域。
- `ProjectTreeWidget` 可以清楚区分：
  - 视图层
  - 菜单/命令层
  - 拖放/目标解析层
- `MainWindow` 不再是树节点语义解释的默认落点。

## 提交检查点

- 检查点 1：`ProjectTreeWidget` 的 menu / command / drag-drop support 切分完成。
- 检查点 2：`DataPage` 的 source manager / preview / pending import 子系统切分完成。
- 检查点 3：`MainWindow` 树路由收口与窄测验收完成。

## 风险与回退

风险：

- 项目树拆分会同时影响多个页面，若 signal 契约变化不稳，容易引入交互回归。
- 数据页深拆若没有保持状态桥接边界，容易重新出现生命周期与延后刷新问题。

回退方式：

- 若树菜单或拖放重构影响面过大，先保留新 support 模块并仅替换单一子路径，不一次并入全部入口。
- 若 `DataPage` 某个 presenter 抽取后仍反向依赖页面私有属性，应回退并重新定义状态接口后再接入。

## 延后到后续阶段的问题

- `ProjectManager` 服务面继续缩减与私有 helper 泄漏清理，转入 `Phase 34`。
- AI 命令层重复实现与单一命令面收口，转入 `Phase 35`。
