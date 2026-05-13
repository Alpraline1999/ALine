# Phase 22：ProjectManager 拆分

## 目标与完成定义

**目标**：将 2708 行的 `ProjectManager` 按职责拆分为 4 个独立模块，每个模块职责单一、可独立测试。

**完成定义**：
- `ProjectSerializer` 独立负责 `.aline`/`.pyline` 文件的读写、版本兼容、迁移
- `TreeManager` 独立负责 `ProjectTree` 节点的增删改查、排序、移动、清理
- `DataFileManager` 独立负责 `DataFile`/`DataSeries`/`SourceFileAsset` 的导入、删除、查找
- `AnalysisManager` 独立负责 `AnalysisResult` 的 CRUD
- `ProjectManager` 保留为 Facade，提供向后兼容的委托调用
- 所有现有测试通过，不改变任何对外行为

## 当前代码现状

- `core/project_manager.py` — 2708 行，涵盖：序列化、树管理、数据集 CRUD、分析管理、文件导入、兼容性迁移等完全不相关的职责
- 所有页面和核心模块通过 `from core.project_manager import project_manager` 引入全局单例
- 方法命名以 `_` 和公共方法混合，内部状态字段 20+ 个

## 优化方案

### 1. 提取 ProjectSerializer

当前 `_save_project()` / `_load_project()` / `_migrate_project_v2()` / `_upgrade_*` 等方法全部移入新模块。

接口设计：
```python
class ProjectSerializer:
    def save(project: Project, path: str) -> None: ...
    def load(path: str) -> Project: ...
    def migrate_if_needed(project: Project) -> Project: ...
    def export(project: Project, format: str) -> str: ...
```

### 2. 提取 TreeManager

当前 `_ensure_tree()` / `_add_folder()` / `_delete_node()` / `_move_node()` / `_cleanup_empty_folders()` / 所有 `_ensure_group_*` 方法移入。

接口设计：
```python
class TreeManager:
    def ensure_root_groups(self, project: Project) -> None: ...
    def add_node( ... ) -> TreeNodeUnion: ...
    def delete_node( ... ) -> bool: ...
    def move_node( ... ) -> bool: ...
    def cleanup_empty_folders( ... ) -> int: ...
    # 所有 group_type 的 ensure/create/find 方法
```

### 3. 提取 DataFileManager

当前 `import_data_file()` / `add_dataset()` / `add_series_to_dataset()` / `delete_data_file()` / `find_series_in_project()` / 等移入。

接口设计：
```python
class DataFileManager:
    def import_file(path: str, target: str) -> DataFile: ...
    def add_series( ... ) -> DataSeries: ...
    def delete_series( ... ) -> bool: ...
    def find_series_in_project(project, series_id) -> Optional[DataSeries]: ...
```

### 4. 提取 AnalysisManager

当前 `create_analysis()` / `delete_analysis()` / `find_analysis()` 等移入。

### 5. ProjectManager Facade

原 `ProjectManager` 保留为 Facade，内部持有上述四个 manager 实例，所有公共方法委托调用。后续逐步迁移调用方直接使用子 manager。

## 迁移策略

1. 先提取新模块（不删旧代码），让旧方法委托调用新模块
2. 为每个新模块补充单元测试
3. 逐步将页面和 core 中的调用方迁移到直接使用子 manager
4. 最后移除 `ProjectManager` 中的重复逻辑

## 验收要点

- 每个新模块的单元测试覆盖率达到 80%+ 核心路径
- 现有 `test_backend.py` 和 `test_ui.py` 全量通过
- `project_manager` 全局单例仍可正常使用（Facade 模式）
- 新模块方法签名清晰，不暴露内部状态

## 边界与约束

- 不改变项目文件格式
- 不改变全局单例引用模式（Phase 26 再处理）
- 不改变 `Project` 模型
- 拆分过程中保持向后兼容，不允许出现 API 断裂
