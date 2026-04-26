# ALine 优化计划 Pro v1

## 目标

本计划用于收口 ALine 当前阶段的核心质量问题：曲线协议统一、扩展接口稳定、内置扩展可测试、文档可执行、UI 回归可定位。软件尚未发布，因此不保留旧协议兼容；既有功能不删减，只做协议收口、公共工具抽象、测试补强和文档完善。

## 当前基线

- backend 测试：`238 passed`。
- 扩展协议：四类扩展统一到严格签名。
- 曲线协议：扩展边界统一为 point-list：`line = [[x, y], ...]`。
- 新增转换底层接口：`processing.extension_tools.line_from_xy(xs, ys)`。
- UI 全量测试：`572 passed, 1 warning in 2982.24s (0:49:42)`。

## 高优先级计划

### P1. 曲线协议彻底收口

状态：已执行。

措施：

- 将 `processing.extension_tools.normalize_line` 改为只接受 point-list。
- 新增 `line_from_xy(xs, ys)`，集中完成长度、数值、有限性检查。
- 统一 `line_xy(line)`，禁止扩展直接把 `line[0]` / `line[1]` 解释为 x/y 列。
- 删除未使用的旧 `line_payloads_from_lines` 桥接路径。
- 处理扩展输出严格为 `line`，不返回 dict、warnings 或多条结果。
- 数字化扩展输出严格为 `line`，页面统一通过 `line_xy` 转换为预览点。

验证：

- `tests/test_backend.py::test_line_protocol_uses_point_list_and_validates_xy_conversion`。
- 全量 backend：`238 passed`。
- 残留搜索：未发现旧桥接函数、旧 line payload helper 或直接 `first[1]`/`second[1]` 语义残留。

### P2. 扩展接口一致性

状态：已执行。

措施：

- `ProcessingExtension`：`(lines, params) -> line`。
- `AnalysisExtension`：`(lines, params) -> dict`。
- `PlotExtension`：`(lines, params) -> None`。
- `DigitizeExtension`：`(figure, params) -> line`。
- 绘图扩展调用边界内部统一命名为 `params`。
- 分析占位符严格使用 `{{token}}` 形式。
- 扩展加载状态统计改为基于最近一次扫描详情，避免全局 registry 残留污染报告。

验证：

- `tests/test_backend.py::test_interface_contract_extensions_load_and_execute`。
- `tests/test_backend.py::test_extension_load_details_are_available_by_category`。
- `tests/test_backend.py::test_placeholder_list_includes_declared_extension_fields_before_run`。

### P3. 内置扩展示例与回归入口

状态：已执行。

措施：

- 新增 `extensions/processing/interface_contract_processing.py`。
- 新增 `extensions/analysis/interface_contract_analysis.py`。
- 新增 `extensions/plot/interface_contract_plot.py`。
- 新增 `extensions/digitize/interface_contract_digitize.py`。
- 四个扩展覆盖常见参数字段、输入类型和输出类型，并可正常加载和执行。

验证：

- 后端测试会加载并调用四类接口示例扩展。
- 扩展 README 中记录这些扩展作为开发者参考与测试入口。

### P4. UI 回归定位

状态：已执行。

措施：

- 跑全量 UI 测试并按首个失败逐步回归定位。
- 对协议相关 UI 优先修复：数字化页自动取点、设置页扩展面板、项目树专注模式、绘图扩展参数传递。
- 修复分析页预览摘要同步、数字化页右侧“曲线数据”布局顺序、主窗口共享树面板按钮可见性回归。
- 对用户已有 UI 改动保持保护，不回退首页、图标、快捷键等未授权修改。

验证：

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui.py::TestMainWindow::test_tree_panel_data_actions_visible_only_on_data_page -q`。
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui.py::TestMainWindow -q --maxfail=1`。
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui.py::TestDigitizePage -q --maxfail=1`。
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_ui.py -q --maxfail=1`，结果为 `572 passed, 1 warning in 2982.24s (0:49:42)`。

## 中优先级计划

### P5. 内部处理流水线维护性

状态：已执行首轮优化。

措施：

- 多曲线重采样内部对齐时，先将项目内 dict 曲线转换为 point-list，再调用公共网格构建逻辑。
- `align_lines_to_common_x` 统一处理 point-list，返回 point-list。
- 项目内存储仍保留 `x` / `y` dict payload，但扩展边界只暴露 point-list。

后续建议：

- 将项目内 dict payload 与扩展 line 的转换集中到少数桥接函数，减少页面层散落转换。
- 给大曲线场景增加性能基准：10k、100k、1M 点处理流水线。

### P6. 文档与开发者体验

状态：已执行。

措施：

- 重写 `extensions/README.md`，改为扩展作者指南结构。
- 新增根目录 `README.md`，覆盖页面介绍、功能介绍、扩展介绍和接口入口。
- 更新 `DESIGN.md` 中的协议描述，明确 point-list、`line_from_xy` 和稳定底层接口。

后续建议：

- 在发布前补充截图和完整用户教程。
- 为外部扩展开发者补充“调试扩展”和“扩展打包发布”章节。

## 低优先级计划

### P7. 性能与可观测性

状态：待执行。

建议：

- 对扩展扫描、项目树构建、曲线重采样和绘图刷新做基准测试。
- 给长耗时扩展调用增加运行时耗时记录。
- 对大数据处理增加可取消任务或后台执行机制。

### P8. 测试覆盖扩展

状态：部分执行。

建议：

- 增加所有内置扩展的最小输入执行矩阵。
- 增加 UI 协议回归窄测集合：数字化自动取点、处理扩展执行、分析报告占位符、绘图扩展 after_plot。
- 增加 README 示例代码导入测试，避免文档与实现再次漂移。

## 已执行优化清单

- point-list line 协议落地。
- `line_from_xy` 转换与合法性检查落地。
- 处理、分析、绘图、数字化扩展签名统一。
- 多曲线处理、分析、绘图扩展迁移到 `line_xy`。
- 数字化页自动取点接入 point-list 返回值。
- 移除旧 line payload 桥接函数与未使用的旧 plot context 探测函数。
- 新增四类接口示例扩展。
- 重写扩展开发文档。
- 新增软件总 README。
- 修复项目树根节点顺序。
- 修复分析页预览摘要同步。
- 修复数字化页右侧布局顺序。
- 修复主窗口共享树面板按钮可见性回归。
- 后端全量测试通过。
- UI 全量测试通过。

## 验收标准

- backend 全量通过。
- 协议残留搜索无旧正式接口路径。
- 四类接口示例扩展能够加载和执行。
- 文档与实现一致。
- UI 协议相关窄测通过。
- UI 全量测试通过。
