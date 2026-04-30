# Phase 12：超大 UI 页面拆分与页面壳层标准化

## 目标与完成定义

目标：

- 把当前超大 UI 页面文件拆回可维护的装配结构，降低单文件状态堆积、初始化冗长和跨区域私有方法耦合。
- 统一页面壳层、workspace bridge、actions、panels、dialogs 的模块边界，使页面结构在功能增长后仍能持续维护。
- 为后续 UI 一致性与规范收尾建立清晰的共享组件和页面骨架。

完成定义：

- `chart_page`、`digitize_page`、`analysis_page`、`process_page`、`settings_page` 不再继续作为“所有逻辑都塞进一个 QWidget 子类”的主要实现承载文件。
- 至少图表页与数字化页完成实质性拆分；分析、处理、设置页采用同一套页面骨架方向。
- `MainWindow` 不再持有页面内部私有刷新细节、局部控件查找和临时装配逻辑。
- 页面新增功能时，有明确落点：
  - page shell
  - workspace bridge
  - page actions
  - panels / dialogs
  - shared presenters / helpers

## 进入前提

- `Phase 11` 完成。
- 大曲线热路径和页面间运行时协作边界已经稳定，不需要在拆页面时再次发明底层数据结构。

## 本阶段纳入的状态与边界

- 纳入：
  - `ui/pages/chart_page.py`
  - `ui/pages/digitize_page.py`
  - `ui/pages/analysis_page.py`
  - `ui/pages/process_page.py`
  - `ui/pages/settings_page.py`
  - `ui/main_window.py`
  - 页面相关的 panels、dialogs、helpers、presenters、bindings
- 不纳入：
  - 核心算法重写
  - 扩展协议再次重构
  - 纯视觉风格大改版
  - 脱离现有页面职责的大规模功能新增

## 本阶段禁止改动的区域

- 禁止借拆文件之名把业务状态重新塞回 `MainWindow` 或散回随机 helper。
- 禁止仅按函数数量机械切文件，而不定义清晰所有权边界。
- 禁止让页面拆分破坏既有 workspace/controller 边界。
- 禁止把局部 UI 便利逻辑再次反向渗透到 `core` 和 `processing`。

## 目标接口/类型/运行时对象

- `PageShell`
- `WorkspaceBindings`
- `PageActions`
- `PagePanelFactory`
- `StatusPresenter`
- `SelectionPresenter`
- `DialogCoordinator`

## 实施顺序

1. 盘点超大文件职责：
   - 初始化装配
   - actions / commands
   - 数据选择与同步
   - 图表/预览刷新
   - 状态呈现
   - dialogs / export flow
2. 先定义统一页面骨架：
   - shell 只负责装配和生命周期
   - bridge 只负责连接 workspace 与视图
   - actions 只负责页面动作
   - panels / dialogs 只负责局部 UI 片段
3. 按高收益页面优先拆分：
   - 先 `chart_page`
   - 再 `digitize_page`
   - 然后 `analysis_page` / `process_page`
   - 最后 `settings_page` / `main_window`
4. 收口页面间公共模式：
   - 统一状态栏/消息区
   - 统一空态/加载态/错态呈现
   - 统一列表选择、预览刷新和批量操作入口
5. 固定窄测和回退面：
   - 保证页面拆分不引入行为退化

## 超大文件拆分策略

推荐按职责拆分，而不是按“看起来差不多长短”拆分：

- `chart_page`
  - page shell
  - plot actions
  - style/workbench panels
  - extension overlay orchestration
  - selection / redraw presenters
- `digitize_page`
  - page shell
  - calibration actions
  - point editing actions
  - auto-detect panels
  - export / history coordination
- `analysis_page` / `process_page`
  - input selection
  - result/output presenters
  - parameter panels
  - export/report dialogs
- `settings_page`
  - category panels
  - template / extension / AI settings coordinators
- `main_window`
  - app shell lifecycle
  - page registration
  - top-level routing / notifications

## 兼容/迁移策略

- 页面对外公开入口尽量保持稳定：
  - 信号名
  - 页面创建方式
  - 上层调用入口
- 内部私有方法允许重排和收口，但必须避免把页面外代码继续绑定到新的私有实现细节。
- 若某页拆分风险过高，可先冻结主文件增长，再逐批迁移局部面板与 actions。

## 验收标准

- 至少 `chart_page` 与 `digitize_page` 完成主拆分，不再继续承担全部局部实现。
- `analysis_page`、`process_page`、`settings_page` 已有统一的拆分骨架并迁移首批职责模块。
- `main_window` 的页面内部私有编排进一步减少，只保留 app shell 级职责。
- 新增窄测覆盖页面壳层与关键 bridge，而不是只对超大文件做黑盒 smoke。
- 本阶段结束后，不再接受新的 2000+ 行页面 monolith 继续增长为默认开发方式。

## 提交检查点

- 检查点 1：统一页面骨架与拆分约定落地。
- 检查点 2：`chart_page` 主拆分完成。
- 检查点 3：`digitize_page` 主拆分完成。
- 检查点 4：分析/处理/设置/主窗口收口与窄测闭环完成。

## 风险与回退办法

风险：

- 只切文件不切边界，结果形成更多弱命名 helper 文件。
- 页面拆分时把状态同步链路打散，导致隐性行为退化。
- 为统一骨架过度抽象，反而压缩页面差异化需求。

回退办法：

- 若某次拆分只制造碎片化，不落位清晰边界，则回退该次拆分并重新定义职责。
- 若统一骨架过重，保留最小共享契约，把页面特有逻辑留在本页子模块。
- 若某页风险较高，先锁定其它高收益页面，延后该页最后一段迁移。
