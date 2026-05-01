# Phase 28：Settings/UI 样式契约与生命周期硬化

## 目标与完成定义

目标：

- 把 `Phase 27` 中已审计出的主题与绘制问题，从“发现并修补”推进到“共享契约与统一实现”。
- 收口 `SettingsPage`、共享设置卡片和少量共享 widget 中零散的 `setStyleSheet()`、文本查找式样式刷新和延后 UI 刷新生命周期噪声。
- 固定“设置卡片标题使用正文样式、描述使用灰色小字、分组标题使用组标题样式”的明确约定，并形成窄测护栏。

完成定义：

- `SettingsPage` 与直接复用的设置/说明型共享 widget 存在统一的样式注册或样式 helper，不再依赖散落的手写刷新分支。
- 延后 UI 刷新路径（如 `QTimer.singleShot()`、延后高度刷新、延后重绘）具备统一的销毁期 guard，不再在测试或关闭路径中产生已删除对象异常噪声。
- 至少有一组针对设置卡片标题/描述样式一致性的测试和一组针对延后 UI 刷新生命周期安全的测试被固定。

## 进入前提

- `Phase 27` 已建立主题切换、delegate paint 和 settings theme consistency 的审计矩阵。
- 当前已知现象已经明确：
  - `SettingsPage` 曾出现“项目树页面专注模式”标题在深色模式下漏刷。
  - 设置卡片的说明性文本存在未统一为灰色小字的问题。
  - 延后 UI 刷新在销毁阶段可能产生已删除 QObject 噪声。

## 本阶段纳入的范围

- `ui/pages/settings_page.py`
- `ui/theme.py` 与 settings 相关的样式 helper
- 直接服务于 Settings/UI consistency 的共享 widget 或 support 模块
- `QTimer.singleShot()`、延后高度刷新、延后主题刷新、延后重绘等小范围 UI 生命周期路径

## 本阶段不纳入的范围

- 视觉改版或重新设计设置页布局
- 项目树、数据页、图表页的大规模文件拆分
- 与样式无关的业务功能开发

## 本阶段禁止事项

- 禁止继续通过“按文本查找 label 然后补样式”的方式无限扩散维护成本。
- 禁止把主题一致性问题继续堆回 `MainWindow` 或全局事件分发链。
- 禁止为了消除生命周期噪声而取消已有延后刷新策略，除非有明确证据证明其无收益。

## 核心问题清单

- `SettingsPage` 仍然承担过多样式注册与局部刷新责任，容易在新增卡片时再次漏刷。
- 共享设置卡片标题/说明样式没有沉淀为统一契约，导致“正文标题”和“灰色说明”只能靠人工记忆。
- 少量延后 UI 刷新逻辑缺少销毁期 guard，测试期间会出现误导性的 QObject 已删除异常噪声。

## 实施顺序

1. 梳理 `SettingsPage` 当前所有手工样式入口，区分组标题、设置标题、说明文本、错误文本、次级状态文本。
2. 为设置卡片标题/说明文本沉淀共享样式注册机制或 helper。
3. 收口 `SettingsPage` 与关联共享 widget 中的延后刷新生命周期 guard。
4. 固定 settings style consistency 与 delayed refresh safety 的窄测。

## 验收标准

- 至少以下文本类型存在单一实现约定：
  - 分组标题
  - 设置卡片标题
  - 设置卡片说明
  - 错误/警告文本
  - 次级状态文本
- `SettingsPage.update_theme_colors()` 不再继续膨胀为零散 `if label is not None` 的累加列表。
- 关闭页面或销毁测试对象时，不再出现已删除 QObject 的延后刷新异常噪声。
- 新增设置卡片标题/说明样式时，有明确的接入方式和回归测试约束。

## 提交检查点

- 检查点 1：settings style contract 与 helper 设计完成。
- 检查点 2：`SettingsPage` 样式刷新与生命周期 guard 收口完成。
- 检查点 3：窄测与阶段验收提交完成。

## 风险与回退

风险：

- 若只改表层样式而不收口注册方式，后续仍会反复出现漏刷。
- 若生命周期 guard 处理过宽，可能掩盖真实运行时错误。

回退方式：

- 若统一 helper 方案导致接入成本过高，可先保留小范围适配层，但必须保留样式注册入口和测试。
- 若某条延后刷新 guard 可能吞掉真实问题，回退到最小 try/except，并补一条更精准的 smoke test。

## 延后到后续阶段的问题

- `SettingsPage` 的深层文件拆分与 tab/section 提炼，延后到 `Phase 29`。
- 全仓 UI token 与更广义的页面视觉统一，延后到更后续的 UI monolith / design consistency 阶段。
