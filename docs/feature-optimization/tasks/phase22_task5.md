# Phase 22 Task 5: ProjectManager Facade 收口 + 调用方迁移

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 22`

## 目标

在 Task 1-4 完成后，将 `ProjectManager` 收口为纯 Facade，逐步迁移全部调用方直接使用子管理器。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/project_manager.py` | 所有方法替换为委托，移除重复逻辑 |
| `ui/widgets/project_tree.py` | 使用 `TreeManager` 替代 |
| `ui/pages/data_page.py` | 使用 `DataFileManager` 替代 |
| `ui/pages/analysis_page.py` | 使用 `AnalysisManager` 替代 |
| `ui/pages/digitize_page.py` | 更新引用 |
| `ui/pages/process_page.py` | 更新引用 |
| `core/exporter.py` | 更新引用 |
| `tests/test_backend.py` | 补充 Facade 测试 |

## 实施步骤

### Step 1: ProjectManager 收口

```python
# core/project_manager.py 最终结构
class ProjectManager:
    """项目管理器（Facade）。"""
    
    def __init__(self):
        self._serializer = ProjectSerializer()
        self._tree_manager = TreeManager()
        self._data_file_manager = DataFileManager(self)
        self._analysis_manager = AnalysisManager(self)
    
    # 核心生命周期（仍保留）
    def new_project(self, name): ...
    def open_project(self, path): ...
    def save_project(self): ...
    def close_project(self): ...
    
    # 子管理器属性（新代码推荐使用）
    @property
    def tree(self):
        return self._tree_manager
    
    @property
    def data_files(self):
        return self._data_file_manager
    
    @property
    def analysis(self):
        return self._analysis_manager
    
    # 旧 API 兼容委托（标记 deprecated）
    def add_folder(self, name, parent_id=None):
        return self._tree_manager.add_folder(self.current_project, name, parent_id)
    
    def delete_node(self, node_id):
        return self._tree_manager.delete_node(self.current_project, node_id)
    
    def import_data_file(self, path, target_data_file_id=None):
        return self._data_file_manager.import_data_file(path, target_data_file_id)
    
    def create_analysis(self, *args, **kwargs):
        return self._analysis_manager.create_analysis(*args, **kwargs)
```

### Step 2: 迁移调用方

| 文件 | 使用方法 | 迁移目标 |
|---|---|---|
| `ui/widgets/project_tree.py` | `project_manager.add_folder()` | `TreeManager.add_folder(project, ...)` |
| `ui/pages/data_page.py` | `project_manager.import_data_file()` | `DataFileManager(...).import_data_file()` |
| `ui/pages/analysis_page.py` | `project_manager.create_analysis()` | `AnalysisManager(...).create_analysis()` |

## 验证清单

- [ ] 旧 API 全部可用（无 AttributeError）
- [ ] 新 API 在项目文件中通过
- [ ] 全量测试成功

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `end`
