# Phase 14：重复实现清理与架构一致性硬化

## 目标与完成定义

目标：

- 在 `Phase 12-13` 建立页面壳层和规范收口之后，继续清理仍然明显存在的高收益重复实现与弱边界。
- 优先处理“已经证实存在重复、且继续并存会产生静默分叉风险”的基础设施代码，而不是扩大到高风险重写。
- 纠正 `DataPage` 的前提判断，避免基于错误假设推进壳层统一。

完成定义：

- `extension_api` 与 `extension_runtime` 中的重复 handler / normalize 实现完成单源收口。
- `ProjectManager` 中重复的备份/删除备份逻辑被提炼为受控服务或等价结构，不再继续横向膨胀。
- matplotlib QtAgg 启动流程有统一入口，不再在多个页面支持模块里复制 try/except 引导代码。
- 明显的死转发层、错误 `__all__` 导出、死别名和小型一致性噪声被清理。
- `DataPage` 的后续改造前提被明确写死：
  - 当前纳入的是页面边界、状态整理和 monolith 拆分准备；
  - 不允许再假设它“已经拥有共享扩展侧栏，只差接入 mixin”。

## 进入前提

- `Phase 13` 已完成，且 `MainWindow` 与 `chart/analysis/process/digitize/settings` 的壳层边界稳定。
- 当前运行时回归已经收口到窄测可控范围内，不需要在本阶段重新设计扩展契约或页面交互模式。

## 本阶段纳入的状态与边界

- 纳入：
  - `core/extension_api.py`
  - `core/extension_runtime.py`
  - `core/extension_invoker.py`
  - `core/project_manager.py`
  - 新的备份/重复逻辑承载模块
  - `ui/matplotlib_fonts.py`
  - `ui/pages/*_support.py`
  - `ui/pages/process_page.py`
  - `core/ai/client.py`
  - `core/ai/config.py`
  - `core/extension_loader.py`
  - `core/analysis_engine.py`
  - `ui/pages/data_page.py`
  - `ui/page_view_state.py`
- 不纳入：
  - 新业务功能
  - 大规模页面视觉改版
  - `DataPage` 直接接入并不存在的扩展侧栏
  - 全量测试体系重写
  - `run_analysis` 级别的大型策略重写

## DataPage 前提澄清

`DataPage` 必须纳入后续阶段，但前提需要校正：

- `DataPage` 当前承担全局扩展配置节点的预览/编辑路由职责。
- `DataPage` 当前并不等同于 `chart/analysis/process/digitize` 那类“带共享扩展侧栏”的页面。
- 因此，本阶段禁止直接按“给 `DataPage` 补一个 `ExtensionPanelShellMixin` 即可完成壳层统一”的思路推进。

允许的方向：

- 整理 `DataPage` 的 view-state、页面骨架和重复状态初始化。
- 评估它是否需要独立的页面状态 dataclass。
- 为未来真正的页面拆分和右侧预览区/配置区边界收口做准备。

不允许的方向：

- 凭空引入一个并不存在的共享扩展侧栏。
- 为了追求“所有页面都继承同一 mixin”而扭曲 `DataPage` 的当前职责。

## 本阶段禁止改动的区域

- 禁止把 `extension_runtime` 收口再次做成新的双实现。
- 禁止在 `ProjectManager` 清理重复时顺手修改项目文件协议或备份语义。
- 禁止把 matplotlib 启动统一演变为 UI 渲染体系重写。
- 禁止在 `DataPage` 前提不清的情况下强行接入共享侧栏接口。
- 禁止以“规范化”为名做大范围 `ruff --fix` 或纯风格扫荡。

## 目标接口/类型/运行时对象

- `core.extension_runtime.*`
- `core.extension_invoker.*`
- `core.project_backup_manager.ProjectBackupManager`
- `ui.matplotlib_fonts.bootstrap_matplotlib_qtagg`
- `core.compat.*` 或等价受控兼容层
- `DataPageViewState` 或等价受控页面状态对象

## 实施顺序

1. 收口 extension handler 单源实现：
   - 清理 `extension_api` / `extension_runtime` 双份实现
   - 固定 `extension_invoker` 作为受控导入边界
2. 收口高价值重复基础设施：
   - 提炼项目备份管理逻辑
   - 收口 matplotlib 启动入口
3. 清理低风险一致性噪声：
   - 死转发层
   - 死别名
   - 错误导出面
   - 小型格式/后缀不一致
4. 处理 `DataPage` 前提澄清后的首批整理：
   - 盘点重复状态初始化
   - 固定 view-state / shell 边界
   - 不跨入虚假的扩展侧栏统一
5. 为后续阶段固化 guardrails：
   - 防止 runtime/api 再次双实现
   - 防止共享基础设施初始化再复制回潮

## 子阶段建议

### 14.1 Extension Handler 去重

目标：

- 把 processing / analysis / plot / digitize 的 handler 调用逻辑固定为单源实现。

纳入：

- `core/extension_runtime.py`
- `core/extension_api.py`
- `core/extension_invoker.py`
- 直接调用这些函数的 processing/tests 模块

验收要点：

- 重复函数只保留一份权威实现。
- `extension_api` 不再与 `extension_runtime` 并行维护同名实现。
- 调用方导入边界清晰，不再出现“同一语义多个入口”。

建议验证：

- `tests/test_extension_runtime.py`
- 直接命中的 backend/processing 窄测

### 14.2 Project Backup 服务化

目标：

- 从 `ProjectManager` 中提炼重复的备份与删除备份逻辑。

纳入：

- 备份文件命名
- 唯一路径生成
- 项目文件夹推导
- 删除受管备份文件

验收要点：

- 三组备份方法收敛为参数化服务或等价结构。
- 现有行为保持稳定，不改变项目资源相对路径协议。

建议验证：

- 针对 project/session/backup 路径的窄测

### 14.3 Shared Bootstrap 与小型一致性收口

目标：

- 统一 matplotlib 启动引导，并清掉低风险小型噪声。

纳入：

- `bootstrap_matplotlib_qtagg`
- `.gif` 图片后缀不一致
- `core/ai/client.py` / `core/ai/config.py` 这类零 importer 死转发层
- `core/extension_loader.py` 的错误 `__all__`
- `analysis_engine.py` 的死别名

验收要点：

- 页面支持模块不再各自复制 QtAgg 启动代码。
- 被删除的转发层已确认没有 importer，或已迁入受控兼容层。

建议验证：

- `tests/test_architecture_guardrails.py`
- `tests/test_ui_smoke.py`

### 14.4 DataPage 前提校正后的首批整理

目标：

- 不假设 `DataPage` 拥有共享扩展侧栏，先把其页面状态和壳层边界整理清楚。

纳入：

- 重复状态初始化盘点
- 右侧预览区 / 管理区 / 路由入口边界梳理
- 受控页面状态对象评估

验收要点：

- 文档和代码都不再把 `DataPage` 错当成 extension-panel page。
- `DataPage` 的下一阶段拆分入口清晰，而不是继续堆积到单文件。

建议验证：

- `tests/test_data_workspace.py`
- 命中的 `tests/test_ui.py -k "data_page or global_extension_config"`

## 验收标准

- 已证实存在的高噪声重复实现至少完成一轮实质性收口，而不是只补注释。
- `DataPage` 前提在文档中被明确校正，并体现在实施边界里。
- 本阶段窄测只覆盖直接命中的模块，不扩大成全量回归。
- 新 guardrails 或导入边界能阻止 runtime/api 再次形成双实现。

## 提交检查点

- 检查点 1：extension runtime / api 双实现清单与首批收口完成。
- 检查点 2：Project backup 重复服务化完成。
- 检查点 3：shared bootstrap 与小型一致性噪声收口完成。
- 检查点 4：DataPage 前提校正后的首批整理与阶段验收完成。

## 风险与回退办法

风险：

- 在 extension handler 去重时误伤旧导入路径，造成隐性调用断裂。
- 在 `ProjectManager` 服务化时把重复提炼成更难理解的抽象层。
- 把 `DataPage` 错误前提从“有扩展侧栏”换成另一种未经验证的假设。

回退办法：

- 若导入边界收口造成回归，先恢复单一兼容桥，不恢复双实现。
- 若 backup 服务提炼过重，回退到薄 service + 明确参数，而不是继续塞回 `ProjectManager`。
- 若 `DataPage` 边界仍不清楚，先冻结其壳层统一动作，只保留文档化前提和最小状态整理。

## 延后到后续阶段的问题

- `DataPage`、`chart_page` 等超大 monolith 的深层继续拆分
- `run_analysis` 大型分支重构
- 扩展测试覆盖面系统补齐
- 扩展目录下共享数值/格式化工具进一步统一
- 更大范围的 UI token / presenter 深化统一
