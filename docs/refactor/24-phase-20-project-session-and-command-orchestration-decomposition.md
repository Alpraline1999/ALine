# Phase 20：Project Session 服务与命令编排拆分

## 目标与完成定义

目标：

- 继续拆解当前仍然明显偏大的业务编排中心，重点处理 `ProjectManager` 与 `ai/command_layer.py`。
- 把项目树操作、资产管理、项目级服务和 AI 命令处理从单文件堆积模式转向受控服务/命令模块。
- 限缩“单个入口承担全部业务动作”的趋势，降低后续功能演进的耦合成本。

完成定义：

- `ProjectManager` 至少一组高密度职责完成服务化或受控模块提炼，不再继续作为默认实现落点无限增长。
- `ai/command_layer.py` 的命令定义与命令处理按业务域拆分，`CommandDispatcher` 只保留装配和路由职责。
- 被拆出的服务或命令模块具有清晰归属，不只是把长文件切成多个无主 util。
- 相邻 UI / AI / backend 调用面保持稳定，不顺手改项目文件协议或命令语义。

## 进入前提

- `Phase 19` 已完成，表达式与处理扩展契约已经稳定。
- 当前阶段聚焦应用编排和项目级服务，不再回头处理底层数值 helper 或页面视觉样式。

## 本阶段纳入的状态与边界

- 纳入：
  - `core/project_manager.py`
  - 新的 project services / coordinators 模块
  - `ai/command_layer.py`
  - 新的 AI command handler / registry 模块
  - 直接依赖这些入口的少量 glue 代码
  - 必要时命中的 `ui/main_window.py` 命令桥接
- 不纳入：
  - 项目文件格式重写
  - 新 AI 产品能力
  - `MainWindow` 全面重构
  - 全局 UI 页面继续拆分

## 本阶段禁止改动的区域

- 禁止把 `ProjectManager` 的职责简单转移到另一个超大 service 文件。
- 禁止为了拆命令层而改变命令名称、入参结构或输出协议，除非阶段文档明确安排兼容桥。
- 禁止把 UI 事件处理重新灌回 `ProjectManager` 或 `CommandDispatcher`。
- 禁止把单文件拆分退化成无类型、无边界的函数散装目录。

## 目标接口/类型/运行时对象

- `ProjectTreeService`
- `ProjectAssetService`
- `ProjectMutationCoordinator`
- `CommandRegistry`
- `CommandHandler`
- `CommandDispatcher`

## 实施顺序

1. 先盘点 `ProjectManager` 的稳定职责切面：
   - 树操作
   - 资产 CRUD
   - 项目级资源协同
2. 再抽取首批 project services：
   - 保持 `ProjectManager` 为兼容 façade 或薄协调器
3. 再拆 `ai.command_layer`：
   - 命令定义
   - 领域 handler
   - dispatcher / registry
4. 最后校正少量调用面：
   - 仅触及直接依赖的 glue
   - 以窄测固定边界

## 核心问题清单

- `core/project_manager.py` 仍然是 2100 行级别的混合中心，继续承载过多项目树、资源、备份与协同行为。
- `ai/command_layer.py` 已成长为 700+ 行的单文件命令编排器，命令处理函数横向堆积。
- 现有拆分若只停留在“提一个小 helper”，无法阻止同类逻辑继续回流到原文件。
- 命令层与项目层都需要更清晰的服务归属，否则未来功能扩展仍会回到单文件追加。

## 子阶段建议

### 20.1 Project Service Boundary Extraction

目标：

- 提炼 `ProjectManager` 中一组稳定、可测试、可复用的项目级服务边界。

验收要点：

- 被提炼的服务拥有明确责任，不是简单把私有方法搬家。
- `ProjectManager` 对已提炼职责转为调用服务，而不是继续维护重复逻辑。

建议验证：

- 命中的 project/session/backend 窄测
- `py_compile` 相关 core 模块

### 20.2 AI Command Layer Split

目标：

- 把 `ai/command_layer.py` 中的命令定义与业务处理按领域拆分。

验收要点：

- dispatcher 不再承载大量具体命令实现。
- 项目、处理、分析、导入导出等命令有更清晰的落点。

建议验证：

- 命中的 AI command/backend 窄测
- 直接命中的手工命令链烟测

### 20.3 Command Glue Hardening

目标：

- 让被拆出的 project services 与 command handlers 通过稳定接口协作，避免再次形成隐式跨层调用。

验收要点：

- 新增命令或项目级动作有明确挂载点。
- 直接耦合 `ProjectManager` 内部私有实现的路径减少。

建议验证：

- 命中的 command/session 窄测
- 直接命中的 `main_window` 命令路由窄测

## 验收标准

- `ProjectManager` 与 `ai.command_layer` 至少各完成一轮实质性拆分。
- 被拆出的服务和命令模块边界清晰，且没有破坏项目协议与命令协议。
- 阶段验证聚焦命中的 session / command 流程，不扩张为全量回归。

## 提交检查点

- 检查点 1：`ProjectManager` 首批 service boundary 提炼完成。
- 检查点 2：AI command layer 按领域拆分完成。
- 检查点 3：command glue 与兼容 façade 收口完成。
- 检查点 4：阶段验收与后续边界文档化完成。

## 风险与回退办法

风险：

- 服务提炼过度可能制造新的“服务中心”而非清晰边界。
- 命令层拆分可能误伤外部调用约定。

回退办法：

- 若某次拆分只让调用链更长而没有边界收益，回退到薄 service + 明确接口。
- 若命令拆分引发兼容性问题，先保留旧 registry 装配层，不恢复单文件大杂糅。

## 延后到后续阶段的问题

- `DataPage` / `chart_page` / `digitize_page` 等剩余超大 UI 页面的完成拆分
- 大工作区、超大曲线与大批量导入导出的进一步性能优化
- 更大范围的 AI 工作流产品能力演进
