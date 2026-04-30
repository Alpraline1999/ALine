# Phase 24：多曲线处理性能与数值基础收口

## 目标与完成定义

目标：

- 针对多曲线处理链路建立第二轮性能硬化，重点处理 `multi_curve_mean`、`pairwise_compute`、共享对齐和重复数值转换。
- 把“逐点重复 `line_xy()` / 重复 point-list 物化 / 重复插值实现”这类隐藏成本收口到共享 primitive，而不是继续散落在扩展里。
- 为大曲线、多输入处理扩展建立明确的性能 guardrail。

完成定义：

- 至少一条多曲线处理热路径完成共享数值 primitive 收口，并有性能窄基线。
- `multi_curve_mean`、`pairwise_compute`、共享对齐 helper 中不再保留明显的点位级重复视图构造。
- `processing/smoother.py` 与 `core.line_tools.py` 中重复的插值 / 重采样 primitive 有明确唯一来源或明确拆分理由。

## 进入前提

- `Phase 23` 已完成运行时回归与契约护栏修补。
- 以 `2026-05-01` 的性能证据进入本阶段：
  - 修复前，`multi_curve_mean` 在 `4 条 × 20000 点` 窄样本上超过 15 秒仍未返回。
  - 临时热修后，同样样本约 `0.153s`，说明主要问题来自重复视图重建而非算法目标本身。

## 本阶段纳入的状态与边界

- 纳入：
  - `extensions/processing/multi_curve_mean.py`
  - `extensions/processing/pairwise_compute.py`
  - `core.line_tools.py`
  - `processing/data_engine.py`
  - `processing/smoother.py`
  - 相关 perf sample / benchmark / 窄测
- 不纳入：
  - 全仓 list-to-numpy 重写
  - 项目文件格式变更
  - UI 大拆分

## 本阶段禁止改动的区域

- 禁止因为局部性能收益就把所有处理扩展全面数组化。
- 禁止把共享 primitive 收口扩张成 `processing` / `core` 的大规模层次重写。
- 禁止只凭体感调优，不固定样本和前后对比。

## 目标接口/类型/运行时对象

- `align_lines_to_common_x`
- `build_alignment_grid`
- `RenderDecimationPolicy`
- `CurveBuffer`
- `SeriesArrayView`
- `PipelineCopyBudget`

## 实施顺序

1. 固定多曲线处理样本和前后性能阈值。
2. 收口 `multi_curve_mean` / `pairwise_compute` 的重复视图与点位级循环。
3. 清理共享插值 / 重采样 primitive 的重复实现。
4. 评估 `data_engine` 多曲线路径中的复制预算与结果物化策略。
5. 增加性能 guardrail 窄测。

## 核心问题清单

- 多曲线扩展目前仍可能在循环中反复执行 `line_xy()`、`normalize_line()` 或 point-list 重建。
- `processing/smoother.py` 与 `core.line_tools.py` 之间存在重复插值/重采样基础实现，既影响维护也妨碍后续优化。
- `data_engine` 多输入路径仍保留一些 `copy.deepcopy` 与重复 `list()` 物化热点，可能抵消前面阶段的数组化收益。
- 当前大曲线性能 guardrail 更偏向图表与导出，对多曲线处理链路仍不够完整。

## 子阶段建议

### 24.1 Multiline Hot Path Benchmarking

目标：

- 固定多曲线处理的最小性能样本与前后阈值。

验收要点：

- 至少一条 `multi_curve_mean` 或 `pairwise_compute` 热路径有固定样本。
- 能清楚描述点数、曲线数和耗时阈值。

### 24.2 Shared Numeric Primitive Consolidation

目标：

- 统一插值、对齐、均值化等共享数值 primitive 的唯一来源。

验收要点：

- 至少一组重复 primitive 被删除或转发到共享实现。
- 不再出现同类算法在 `core` / `processing` 双份演进。

### 24.3 Copy Budget Hardening

目标：

- 收口 `data_engine` 多曲线路径中的不必要复制与物化。

验收要点：

- 至少一条多输入处理链路的复制次数或临时对象数量明显下降。
- 保持结果一致性与窄测稳定。

## 验收标准

- 多曲线处理性能优化有可重复样本和前后对比。
- 不通过“全局 numpy 化”逃避热点分析。
- 共享数值 primitive 的重复实现得到实质性收口。

## 提交检查点

- 检查点 1：多曲线处理性能样本与阈值建立完成。
- 检查点 2：`multi_curve_mean` / `pairwise_compute` 热路径首轮优化完成。
- 检查点 3：重复数值 primitive 与 copy budget 收口完成。
- 检查点 4：阶段验收提交完成。

## 风险与回退办法

风险：

- 共享 primitive 收口若边界不清，可能引发 `processing` 与 `core` 的层次反转。
- 性能优化若绕开一致性验证，容易引入隐蔽数值偏差。

回退办法：

- 若某个 primitive 暂时无法单源化，先保留唯一调用入口，再延后底层迁移。
- 若优化收益不稳定，保留 benchmark 与 guardrail，不强推实现。

## 延后到后续阶段的问题

- 导入预览增量解析和更深层 pipeline 流式执行。
- 更大范围的扩展原生数组输入协议。
- GPU / 专用数值后端探索。
