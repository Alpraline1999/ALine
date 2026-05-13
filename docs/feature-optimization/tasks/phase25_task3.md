# Phase 25 Task 3: 旧格式向后兼容与迁移测试

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 25`

## 目标

确保旧 `.pyline` 文件和纯 JSON 格式的旧 `.aline` 文件在 ZIP 容器格式下可正常加载，并在首次保存时自动升级。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/zip_serializer.py` | 实现 `migrate_from_json()` |
| `tests/test_backend.py` | 补充兼容性测试 |

## 兼容性检测

```python
# core/zip_serializer.py
@staticmethod
def detect_format(path: str) -> str:
    """检测文件格式。
    
    Returns:
        'zip'     — 新版 ZIP 容器
        'json'    — 旧版纯 JSON
        'unknown' — 无法识别
    """
    # 先试 ZIP
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            if 'project.json' in zf.namelist():
                return 'zip'
    except zipfile.BadZipFile:
        pass
    
    # 再试 JSON
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'aline_version' in data or 'name' in data:
                return 'json'
    except:
        pass
    
    return 'unknown'

@staticmethod  
def migrate_from_json(json_path: str, zip_path: str) -> None:
    """将旧 JSON 格式迁移为 ZIP 容器格式。"""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    project = Project(**data)
    ZipProjectSerializer.save(project, zip_path)
```

## 集成到 ProjectManager

```python
# project_manager.open_project() 中
format_ = self._serializer.detect_format(path)
if format_ == 'json':
    project = self._serializer.load(path)  # 旧格式加载
    # 标记下次保存时升级
    self._upgrade_on_save = True
elif format_ == 'zip':
    project = self._serializer.load(path)  # 新格式加载
```

## 单元测试

```python
class TestBackwardCompatibility(unittest.TestCase):
    def setUp(self):
        self.serializer = ZipProjectSerializer()
        self.tmpdir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir)
    
    def test_detect_json_format(self):
        path = os.path.join(self.tmpdir, "old.pyline")
        with open(path, 'w') as f:
            json.dump({"name": "test", "aline_version": None}, f)
        self.assertEqual(self.serializer.detect_format(path), 'json')
    
    def test_detect_zip_format(self):
        path = os.path.join(self.tmpdir, "new.aline")
        project = Project.create_new("test")
        self.serializer.save(project, path)
        self.assertEqual(self.serializer.detect_format(path), 'zip')
    
    def test_load_json_format(self):
        path = os.path.join(self.tmpdir, "old.pyline")
        old = {"id": "test-id", "name": "old", "images": [], "aline_version": None}
        with open(path, 'w') as f:
            json.dump(old, f)
        project = self.serializer.load(path)
        self.assertEqual(project.name, "old")
    
    def test_migrate_json_to_zip(self):
        json_path = os.path.join(self.tmpdir, "old.pyline")
        zip_path = os.path.join(self.tmpdir, "new.aline")
        with open(json_path, 'w') as f:
            json.dump({"name": "migrated", "aline_version": None}, f)
        self.serializer.migrate_from_json(json_path, zip_path)
        self.assertEqual(self.serializer.detect_format(zip_path), 'zip')
    
    def test_load_json_with_curves(self):
        """含实际曲线数据的旧格式正确加载"""
        curve = {"id": "c1", "name": "curve1", 
                 "x_data": [1.0, 2.0], "y_data": [3.0, 4.0]}
        old = {"name": "test", "images": [{
            "id": "img1", "name": "img",
            "image_path": "", "curves": [curve]
        }]}
        path = os.path.join(self.tmpdir, "old.pyline")
        with open(path, 'w') as f:
            json.dump(old, f)
        project = self.serializer.load(path)
        self.assertEqual(len(project.images[0].curves[0].x_data), 2)
```

## 验证清单

- [ ] 旧 `.pyline` 文件可用新序列化器打开
- [ ] 旧格式保存后升级为新 ZIP 格式
- [ ] 含曲线数据的旧文件数据完整
- [ ] `detect_format` 正确区分三种格式

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
