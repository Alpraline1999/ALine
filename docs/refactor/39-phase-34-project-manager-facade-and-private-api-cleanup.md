# Phase 34：ProjectManager Facade 收口与私有 API 清理

## 目标与完成定义

目标：

- 继续缩减 `ProjectManager` 的中心化编排职责。
- 消除 UI / dialog / page 直接访问 `project_manager._*` 私有 helper 和私有状态字段的做法。
- 把名称规范、group 查询、目标节点解析、session 切换等能力下沉到明确的 public service / facade。

完成定义：

- UI / app / dialog 层不再直接调用 `project_manager._normalize_name_key`、`_find_folder_by_group_type`、`_canonical_group_type` 等私有 helper。
- 不再允许外部模块直接写入 `project_manager._current_project_id` 之类的私有状态。
- `core/project_manager.py` 的剩余能力可以按 query / mutation / session / naming / tree target resolution 解释清楚。

## 进入前提

- `Phase 33` 已稳定收口数据页、项目树和主窗口的树路由 surface。
- 当前 `ProjectManager` 的现有 service 提取已经足够支撑第二轮 facade 缩减。

## 本阶段纳入的范围

- `core/project_manager.py`
- `core/project_services/*`
- `core/project_name_rules.py`
- `ui/pages/process_page.py`
- `ui/pages/analysis_page.py`
- `ui/pages/digitize_page.py`
- `ui/dialogs/export_flow.py`
- 其他直接访问 `project_manager._*` 的 first-party 调用点

## 本阶段不纳入的范围

- 项目文件格式升级
- 新增项目树节点类型
- 重新设计全量数据模型

## 本阶段禁止事项

- 禁止把私有 helper 改名为 public 后原样外露，而不收敛语义。
- 禁止继续让页面自己拼装 tree target / group type 规则。
- 禁止为了兼容旧调用，在 UI 中保留双轨调用路径。

## 核心问题清单

- `ProcessPage` 仍直接使用 `project_manager._normalize_name_key(...)`。
- `DigitizePage`、`AnalysisPage`、`export_flow` 仍依赖 `_find_folder_by_group_type`、`_canonical_group_type` 等私有实现细节。
- 仍存在直接写 `project_manager._current_project_id` 的调用，说明 session 边界还不完整。
- `ProjectManager` 公开方法面仍然偏大，查询与变更职责混杂。

## 实施顺序

1. 先扫描并列出所有 `project_manager._*` 调用点，分类为：
   - naming
   - tree/group query
   - session mutation
   - path/target resolution
2. 针对每一类补 public facade / service 接口。
3. 替换 UI / dialog 调用点，删除对私有 helper 的依赖。
4. 最后继续压缩 `ProjectManager` 主文件中仍可外提的查询和目标解析逻辑。

## 验收标准

- first-party 代码中不再出现新的 `project_manager._*` 跨模块访问。
- 不再存在对 `project_manager` 私有字段的直接写入。
- `ProjectManager` 的服务面拆分后，页面只依赖稳定 public contract。

## 提交检查点

- 检查点 1：私有 API 调用点清单与 public facade 设计落地。
- 检查点 2：页面 / dialog 替换完成并删除私有 helper 依赖。
- 检查点 3：`ProjectManager` 第二轮 service/facade 收口与窄测验收完成。

## 风险与回退

风险：

- 若 public facade 定义过于贴近当前 UI，会把页面偶然需求固化进核心层。
- session 相关替换若不完整，可能再次引入当前项目切换异常。

回退方式：

- 若某类 helper 尚无法稳定 public 化，先提炼独立 query service，再由有限 façade 代转，不强行直接暴露 `ProjectManager` 方法。
- 若 session 接口替换引发链式回归，保留新 session service 并缩小单次接入面。

## 延后到后续阶段的问题

- AI 命令注册与执行重复定义问题，转入 `Phase 35`。
- 剩余页面壳层与共享对话框/控件深拆，转入 `Phase 36`。
