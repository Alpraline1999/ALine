# Phase 21：UI Monolith 收尾与 Workspace Surface 硬化

## 目标与完成定义

目标：

- 完成前几轮页面拆分后仍然遗留的超大 UI monolith 收口，重点处理 `DataPage` 和仍然超过 2000-4000 行级别的工作页。
- 稳定页面 section controller / presenter / bridge / action coordinator 的落点，防止新逻辑继续回灌到页面类。
- 统一剩余页面的空态、错态、加载态和命令/激活路由边界，减少运行时空属性与 fallback 逻辑噪声。

完成定义：

- `DataPage`、`chart_page`、`digitize_page`、`analysis_page`、`process_page` 至少完成一轮继续拆分，不再把新功能默认落到原始大文件。
- `ui/main_window.py` 与页面之间的激活/命令/树路由 surface 更薄，不再继续堆积页面私有分发细节。
- 共享页面边界清晰：
  - shell
  - workspace bridge
  - presenter
  - section controller
  - action coordinator
- 常见 UI 状态与 fallback 约定更统一，降低运行时缺属性、空对象和临时分支风险。

## 进入前提

- `Phase 20` 已完成，项目级服务和命令编排边界已相对稳定。
- 本阶段只继续拆 UI monolith 和 workspace surface，不重写底层处理算法或扩展协议。

## 本阶段纳入的状态与边界

- 纳入：
  - `ui/pages/data_page.py`
  - `ui/pages/chart_page.py`
  - `ui/pages/digitize_page.py`
  - `ui/pages/analysis_page.py`
  - `ui/pages/process_page.py`
  - `ui/main_window.py`
  - 新的 page sections / presenters / controllers / bridges
  - 直接相关的页面 support / widget glue
- 不纳入：
  - 全新 UI 风格设计
  - 主题系统重写
  - 与页面无关的 core/processing 重构
  - 全量 UI 回归测试

## 本阶段禁止改动的区域

- 禁止为了缩短文件行数把逻辑散落到无主 helper 文件。
- 禁止把页面状态重新推回 `MainWindow` 或全局单例。
- 禁止借页面拆分之名更改现有交互语义。
- 禁止为统一表象而强迫所有页面套入并不匹配的同一 mixin。

## 目标接口/类型/运行时对象

- `DataPageSectionController`
- `ChartRenderController`
- `DigitizeWorkspaceBridge`
- `AnalysisResultPresenter`
- `ProcessPipelineCoordinator`
- `TreeCommandRoute`

## 实施顺序

1. 先完成 `DataPage`：
   - 节点路由
   - 右侧预览/管理区
   - 导入队列/全局扩展配置入口
2. 再处理最重的工作页：
   - `chart_page`
   - `digitize_page`
3. 再处理相邻页面与壳层路由：
   - `analysis_page`
   - `process_page`
   - `main_window`
4. 最后统一页面状态与 fallback 约定：
   - 空态/错态/加载态
   - 缺失依赖时的保护路径

## 核心问题清单

- `DataPage` 仍是 4900+ 行级别的多职责页面，后续继续增长风险很高。
- `chart_page`、`digitize_page`、`analysis_page`、`process_page` 仍保留大量页面级调度、状态桥接与显示 glue。
- `main_window.py` 仍承担一部分页面私有激活/命令分发职责，容易继续回流页面细节。
- 部分页面仍存在“属性可能缺失时靠临时 fallback 修补”的运行时噪声，可靠性与可维护性一般。

## 子阶段建议

### 21.1 DataPage Completion

目标：

- 把 `DataPage` 继续拆到“节点路由 / 右侧内容 / 页面状态”三个清晰层次。

验收要点：

- `DataPage` 不再同时堆积节点解析、预览装配、导入管理与全局扩展配置 glue。
- 页面状态与右侧展示逻辑有明确承载模块。

建议验证：

- 命中的 `data_page` 窄测
- 直接命中的项目树/节点激活烟测

### 21.2 Chart And Digitize Surface Hardening

目标：

- 继续收口渲染、工具模式、overlay、批量添加/刷新等高密度页面逻辑。

验收要点：

- `chart_page` / `digitize_page` 主文件显著缩短，渲染与工具控制有稳定归属。
- 相关页面不再依赖大量 ad-hoc fallback 属性修补。

建议验证：

- 命中的 chart / digitize UI 窄测
- 直接命中的手工页面烟测

### 21.3 Analysis Process And MainWindow Route Cleanup

目标：

- 让 `analysis_page`、`process_page` 与 `main_window` 的调用边界更薄、更稳定。

验收要点：

- `MainWindow` 不再继续承担页面内部路由细节。
- analysis/process 页面的状态桥接与动作协调有清晰落点。

建议验证：

- 命中的 page bridge / route 窄测
- 直接命中的 workspace 命令链烟测

## 验收标准

- 至少两类仍然超大的页面主文件完成继续拆分，并形成清晰边界而非纯拆文件。
- `MainWindow` 与页面的 surface 更薄，跨页私有调用减少。
- 页面缺失依赖与 fallback 约定更统一，降低运行时属性缺失问题。

## 提交检查点

- 检查点 1：`DataPage` 继续拆分与状态边界收口完成。
- 检查点 2：`chart_page` / `digitize_page` surface hardening 完成。
- 检查点 3：`analysis_page` / `process_page` / `main_window` 路由收口完成。
- 检查点 4：阶段验收与 UI surface guardrails 完成。

## 风险与回退办法

风险：

- 页面拆分时可能打散信号链和交互回调链。
- 过多 controller/presenter 名称可能制造新形式的复杂度。

回退办法：

- 若某次拆分没有带来更清晰的页面职责，回退该次拆分，不保留无收益文件切割。
- 若 controller/presenter 过重，收缩为薄边界对象，而不是回退到原 monolith。

## 延后到后续阶段的问题

- 大工作区、超大曲线与大批量数据流的进一步性能和虚拟化优化
- 更大范围的 UI 细节统一与视觉 polish
