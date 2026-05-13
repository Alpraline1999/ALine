# Phase 22 Task 3: 抽取 DataFileManager

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 22`

## 目标

从 `core/project_manager.py` 中提取与 `DataFile`/`DataSeries`/`SourceFileAsset` 相关的管理方法为独立的 `core/data_file_manager.py` 模块。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/project_manager.py` | 移除文件/系列导入管理方法，改为委托 |
| `core/data_file_manager.py` | **新建** |
| `ui/pages/data_page.py` | 逐步迁移引用 |
| `tests/test_backend.py` | 补充 `TestDataFileManager` |

## 需要提取的方法

```python
# 从 ProjectManager 中提取:
import_data_file(path, target_data_file_id) -> DataFile
import_source_file(path) -> SourceFileAsset
delete_data_file(data_file_id) -> bool
delete_source_file(source_file_id) -> bool

add_dataset(name, parent_id) -> Dataset
add_series_to_dataset(dataset_id, series) -> DataSeries
remove_series_from_dataset(dataset_id, series_id) -> bool

find_series_in_project(project, series_id) -> Optional[DataSeries]
find_data_file(data_file_id) -> Optional[DataFile]
find_source_file(source_file_id) -> Optional[SourceFileAsset]
iter_all_series(project) -> Iterator[DataSeries]
```

## DataFileManager 接口设计

```python
# core/data_file_manager.py
class DataFileManager:
    """DataFile/DataSeries/SourceFileAsset 的导入、删除、查找。
    
    需要 project_manager.current_project 获取当前项目。
    初始化后绑定到 project_manager 实例。
    """

    def __init__(self, project_manager):
        self._pm = project_manager

    @property
    def _project(self):
        return self._pm.current_project

    def import_data_file(self, path: str, target_data_file_id: Optional[str] = None,
                         create_dataset: bool = False) -> DataFile:
        """导入数据文件。
        
        1. 检测文件格式（CSV/Excel/JSON/NumPy）
        2. 解析为 List[DataSeries]
        3. 创建或追加到 DataFile
        4. 注册到项目树的 data_file 组
        5. 返回创建的 DataFile
        """
        from core.data_operations import import_csv, import_excel, import_json  # 延迟导入
        ...

    def import_source_file(self, path: str) -> SourceFileAsset:
        """复制源文件到项目目录并注册。"""
        ...

    def delete_data_file(self, data_file_id: str) -> bool:
        """删除 DataFile 及其在树中的节点。"""
        ...

    def delete_source_file(self, source_file_id: str) -> bool:
        """删除 SourceFileAsset 及其在树中的节点。"""
        ...

    def add_series_to_data_file(self, data_file_id: str, series: DataSeries) -> DataSeries:
        """向已存在的 DataFile 追加 DataSeries。"""
        ...

    def find_series(self, series_id: str) -> Optional[DataSeries]:
        """在所有 DataFile 中查找 DataSeries。"""
        for df in self._project.data_files:
            for s in df.series:
                if s.id == series_id:
                    return s
        return None

    def iter_all_series(self) -> Iterator[DataSeries]:
        """遍历所有 DataFile 下的所有 DataSeries。（页面列表用）"""
        ...

    def get_data_file(self, data_file_id: str) -> Optional[DataFile]:
        for df in self._project.data_files:
            if df.id == data_file_id:
                return df
        return None
```

## 关键实现细节

### import_data_file 完整流程

```python
def import_data_file(self, path, target_data_file_id=None, create_dataset=False):
    # 1. 判断文件格式
    ext = Path(path).suffix.lower()
    if ext in ('.csv', '.txt', '.dat', '.tsv'):
        series_list = import_csv(path)
    elif ext in ('.xls', '.xlsx'):
        series_list = import_excel(path)
    elif ext == '.json':
        series_list = import_json(path)
    elif ext == '.npy':
        series_list = import_numpy(path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")
    
    # 2. 检查 series 非空
    if not series_list:
        raise ValueError("文件中没有可导入的数据列")
    
    # 3. 创建或查找目标 DataFile
    if target_data_file_id:
        data_file = self.get_data_file(target_data_file_id)
        if not data_file:
            raise ValueError(f"目标 DataFile 不存在: {target_data_file_id}")
        data_file.series.extend(series_list)
    else:
        data_file = DataFile(
            name=Path(path).stem,
            source_path=os.path.abspath(path),
            series=series_list,
        )
        self._project.data_files.append(data_file)
    
    # 4. 更新项目树
    from core.tree_manager import TreeManager
    tm = TreeManager()
    tm.ensure_tree(self._project)
    tm.ensure_root_groups(self._project)
    
    # 查找或创建 datasets 组
    datasets_group = tm.ensure_group(self._project, "datasets", "数据集")
    tm.add_node(self._project, DataFileNode(
        name=data_file.name, data_file_id=data_file.id
    ), parent_id=datasets_group.id)
    
    return data_file
```

## 单元测试

```python
class TestDataFileManager(unittest.TestCase):
    def setUp(self):
        self.project = Project.create_new("test")
        self.pm = MagicMock()
        self.pm.current_project = self.project
        self.mgr = DataFileManager(self.pm)
    
    def test_import_csv_creates_data_file(self):
        """导入 CSV 后 project.data_files 增加"""
        path = write_temp_csv("x,y\n1,2\n3,4\n")
        df = self.mgr.import_data_file(path)
        self.assertEqual(len(self.project.data_files), 1)
        self.assertEqual(len(df.series), 1)
    
    def test_import_csv_no_valid_data_raises(self):
        """空文件抛 ValueError"""
        path = write_temp_csv("")
        with self.assertRaises(ValueError):
            self.mgr.import_data_file(path)
    
    def test_find_series_by_id(self):
        path = write_temp_csv("x,y\n1,2\n3,4\n")
        df = self.mgr.import_data_file(path)
        found = self.mgr.find_series(df.series[0].id)
        self.assertIsNotNone(found)
    
    def test_find_series_not_found_returns_none(self):
        self.assertIsNone(self.mgr.find_series("nonexistent"))
    
    def test_delete_data_file_removes_from_project(self):
        path = write_temp_csv("x,y\n1,2\n")
        df = self.mgr.import_data_file(path)
        self.mgr.delete_data_file(df.id)
        self.assertEqual(len(self.project.data_files), 0)
```

## 边界情况

| 场景 | 预期 |
|---|---|
| CSV 文件不存在 | `FileNotFoundError` |
| CSV 全是非法数字 | 空的 DataFile，series 为空列表 |
| 重复导入同一文件 | 每次都创建新的 DataFile（文件内容可不同） |
| 删除 DataFile 后树节点同步删除 | TreeManager.delete_node 会被调用 |

## 验证清单

- [ ] `TestDataFileManager` 全部通过
- [ ] 在 UI 中导入 CSV 文件，数据正确出现在项目树中
- [ ] 删除 DataFile 后树节点同步移除
- [ ] 查找系列通过 ID 和名称都能匹配

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
