# Phase 27：性能优化

## 目标与完成定义

**目标**：解决大曲线（>10k points）、大项目（>500 节点）场景下的 UI 卡顿和渲染性能问题。

**完成定义**：
- 项目树支持虚拟滚动，展开/滚动 500+ 节点无卡顿
- matplotlib 曲线渲染超过 10k 点时自动降采样，渲染时间 <100ms
- 批量处理/分析操作异步化，UI 不阻塞
- 大批量文件导入时显示进度条，不冻结 UI

## 当前代码现状

- 项目树（`ProjectTreeWidget`）使用 `QTreeWidget`，全部节点一次性加载，大数据集展开/折叠卡顿
- matplotlib 渲染大曲线时无自动降采样，渲染时间与点数成正比
- pipeline 执行（`data_engine.apply_pipeline_to_lines`）同步阻塞，UI 线程等待
- 分析引擎（`core/analysis_engine.py`）同步执行，大输入时冻结 UI
- 大数据文件导入无进度反馈

## 优化方案

### 1. 项目树虚拟滚动

现状：`QTreeWidget` 默认加载所有节点，大数据集展开时创建大量 `QTreeWidgetItem`

方案：
- 使用 `QTreeView` + 自定义 `QAbstractItemModel` 模型，实现按需加载
- 对超过 200 个直接子节点的文件夹启用懒加载
- 节点数据的模型层从 `ProjectTree.nodes` 直接读取，避免创建冗余 item 对象
- 搜索/过滤可沿用当前模式，但仅在展开数据子集上操作

### 2. 曲线渲染自动降采样

方案：
- 在 `matplotlib_preview.py` 中引入统一的降采样 Helper
- 策略：超过 10k 点时使用 LTTB（Largest Triangle Three Buckets）算法
- 降采样后的数据只用于渲染，不修改原始数据
- 导出/分析使用全量数据

```python
def downsample_for_rendering(x: NDArray, y: NDArray, max_points: int = 10000) -> Tuple[NDArray, NDArray]:
    """LTTB 降采样，保留视觉特征"""
```

### 3. 批量处理/分析异步化

方案：
- 引入 `QThread` / `QThreadPool` 后台执行长时间任务
- 使用 `QMetaObject.invokeMethod` 或信号将结果回传主线程
- 处理页和分析页在执行期间显示进度条和取消按钮
- Pipeline 执行支持中途取消

```python
class AsyncPipelineRunner(QObject):
    progress = Signal(int, str)  # 进度百分比 + 当前操作描述
    finished = Signal(object)
    cancelled = Signal()

    def run(self, lines, ops): ...  # 在后台线程执行
    def cancel(self): ...
```

### 4. 大文件导入进度反馈

方案：
- `import_csv()` / `import_excel()` 支持回调报告进度
- 导入对话框显示进度条和当前解析的行数
- 大批量文件批量导入时排队按序处理

## 验收要点

- 500 节点的项目树展开/折叠无感知延迟（<16ms per frame）
- 100k 点的曲线渲染 <100ms（从 1s+ 优化）
- Pipeline 执行大输入时 UI 可操作，有进度反馈
- 批量导入 10 个 100MB CSV 文件时 UI 不冻结

## 边界与约束

- 不改变数据处理结果的精度（降采样仅用于预览渲染）
- 异步执行不改变 Pipeline 的确定性（相同输入 → 相同输出）
- 仅在必要时启用虚拟滚动（小项目保持当前行为）
