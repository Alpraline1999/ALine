# Phase 18：共享处理基础与依赖方向纠偏

## 目标与完成定义

目标：

- 在 `Phase 17` 完成长流程收口后，继续处理仍然存在的基础层重复实现、跨层依赖反转和低风险一致性噪声。
- 把“处理基础算法”“扩展稳定类型”“页面共享 bootstrap”收口为单源实现，避免未来继续横向复制。
- 纠正 `processing` / `core` 继续反向依赖 `extensions` 的问题，为后续表达式、性能和 UI 阶段提供更稳定的底座。

完成定义：

- `processing` / `core` 中不再通过 `extensions.processing.*` 获取稳定基础能力；共享数值/对齐/插值 helper 已迁入中性模块或等价受控边界。
- `extension_runtime` 与 `extension_api` 间的 plot 类型/phase 归一化循环依赖被消除。
- `resample`、`smooth`、`data_engine` 中已证实的重复算法完成单源收口，不再继续多处并行维护。
- `process_page` 的 matplotlib QtAgg bootstrap 已切换到共享入口。
- 已确认的死代码、未使用导入、局部重复导入等低风险噪声被顺手清理，但不演变为全仓风格扫荡。

## 进入前提

- `Phase 17` 已完成，`analysis_engine` / `import_dialog` / `export_flow` / `data_engine` 的长流程边界已相对稳定。
- 当前阶段只允许处理共享基础、依赖方向与小型一致性问题，不重新设计表达式语义或页面结构。

## 本阶段纳入的状态与边界

- 纳入：
  - `processing/data_engine.py`
  - `processing/smoother.py`
  - `processing/extension_tools.py`
  - 新的中性共享处理 helper 模块
  - `extensions/processing/extension_tools.py`
  - `extensions/processing/resample.py`
  - `extensions/processing/smooth.py`
  - `core/extension_api.py`
  - `core/extension_runtime.py`
  - 新的 extension types / contracts 模块
  - `ui/pages/process_page.py`
  - `ai/skill_runner.py`
  - `core/project_manager.py`
  - `ui/pages/data_page.py`
- 不纳入：
  - 表达式引擎重写
  - 扩展协议大版本调整
  - 超大页面继续拆分
  - 全量 lint / 全量测试回归

## 本阶段禁止改动的区域

- 禁止用“继续从 `extensions` 导入私有 helper”来实现去重，这会固化错误依赖方向。
- 禁止为了解决循环依赖而重新制造新的双实现或新的惰性导入散点。
- 禁止把低风险清理扩大成全仓 `ruff --fix` 或纯样式整理。
- 禁止删除兼容桥后立刻要求所有外围调用方同步改造，必须保留受控迁移路径。

## 目标接口/类型/运行时对象

- `core.extension_types` 或等价中性模块
- `normalize_plot_extension_phases`
- 中性共享处理 helper 模块
- `processing.extension_tools` 受控兼容层
- `bootstrap_matplotlib_qtagg`

## 实施顺序

1. 先做低风险一致性收口：
   - 死代码
   - 未使用导入
   - 局部重复导入
   - `process_page` bootstrap 统一
2. 再处理 extension 类型边界：
   - plot extension dataclass / phase normalize 抽出
   - 消除 `extension_runtime` / `extension_api` 循环依赖
3. 再处理共享处理基础：
   - 抽取中性插值/对齐/采样 helper
   - 迁移 `data_engine` / `resample` / `smooth` 到单源实现
4. 最后收口兼容桥：
   - 限缩 `processing/extension_tools.py` 的过渡职责
   - 防止 `core` / `processing` 再次直接依赖 `extensions`

## 核心问题清单

- `processing/data_engine.py` 仍直接从 `extensions.processing.extension_tools` 获取稳定 helper，层次方向不合理。
- `extension_runtime.py` 仍通过惰性导入从 `extension_api.py` 获取 plot 类型与 phase normalize 能力，循环依赖仍然存在。
- `resample.py`、`smooth.py`、`data_engine.py` 中仍有已证实的重复插值、排序、平滑算法。
- `process_page.py` 仍保留与其他页面支持模块不一致的 matplotlib bootstrap 方式。
- 一批低风险噪声仍然真实存在：
  - `extension_api.py` 中的死私有 normalize 函数
  - `skill_runner.py` 中未读取的 `_ALLOWED_IMPORTS`
  - `project_manager.py` 中未使用导入
  - `data_page.py` 中遮蔽顶层导入的局部 `QMenu`

## 子阶段建议

### 18.1 Low-risk Cleanup And Bootstrap Convergence

目标：

- 清掉已确认存在且行为风险低的噪声，并统一 `process_page` 的 matplotlib bootstrap 入口。

验收要点：

- 被删除的导入、死函数和局部导入已确认无调用方。
- `process_page` 不再维护独立的 QtAgg try/except 启动代码。

建议验证：

- `py_compile` 命中的页面与基础模块
- 命中的 `process_page` UI 窄测

### 18.2 Extension Type Boundary Repair

目标：

- 把 plot extension 稳定类型和 phase normalize 迁出 `extension_api.py`，消除 `extension_runtime` 的循环依赖。

验收要点：

- `extension_runtime.py` 不再依赖从 `extension_api.py` 惰性导入 plot 类型。
- `extension_api.py` 只作为受控导出面，不再承担所有类型定义与 runtime glue。

建议验证：

- `tests/test_extension_runtime.py`
- 命中的 backend / extension 窄测

### 18.3 Shared Processing Foundation Extraction

目标：

- 把对齐、插值、排序去重、采样间距、平滑算法等共享基础能力收口到中性模块，供 `processing` 与 `extensions` 共同消费。

验收要点：

- `data_engine.py`、`resample.py`、`smooth.py` 不再各自维护同一套基础算法。
- `processing` 与 `extensions` 之间的共享基础能力方向正确：
  - 中性模块向上提供
  - `extensions` 不再成为 `processing` 的事实基础层

建议验证：

- `tests/test_backend.py -k "pipeline or processing"`
- `tests/test_extension_runtime.py`

## 验收标准

- 至少一条共享处理基础链路完成正确方向的单源收口，而不是把去重建立在错误依赖上。
- plot extension 类型/phase 的循环依赖被消除，并有窄测或导入验证覆盖。
- `process_page` bootstrap 与其他页面支持模块一致。
- 本阶段验证保持窄范围，不扩张为全量回归。

## 提交检查点

- 检查点 1：低风险清理与 `process_page` bootstrap 收口完成。
- 检查点 2：extension type boundary 与循环依赖修复完成。
- 检查点 3：shared processing foundation 首轮抽取完成。
- 检查点 4：兼容桥收口与阶段验收完成。

## 风险与回退办法

风险：

- 去重时若直接复用错误层次，会把短期收益变成长期耦合债务。
- 循环依赖修复可能误伤历史导入路径。
- 平滑/插值/对齐 helper 收口可能引入边缘数值行为差异。

回退办法：

- 若共享 helper 抽取后边界更乱，优先退回到“中性薄模块 + 明确 importer”，不要退回多份复制实现。
- 若导入路径收口引发回归，先保留受控兼容导出，不恢复循环依赖。
- 若某类算法复用收益不足，允许保留薄适配层，但不允许保留整段重复算法。

## 延后到后续阶段的问题

- 表达式执行与 `eval` 安全边界
- `_as_float` 等参数解析 helper 的系统性统一
- `ProjectManager` 与 `ai.command_layer` 的大体量编排拆分
- `DataPage` / `chart_page` / `digitize_page` 等剩余 monolith 完成拆分
- 大工作区和超大曲线场景的进一步性能与虚拟化优化
