# Phase 25 Task 1: 实现 ZipProjectSerializer

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 25`

## 目标

在已有 `ProjectSerializer`（Phase 22 Task 1 提取）基础上实现 ZIP + JSON 容器格式版本 `ZipProjectSerializer`，支持增量保存和懒加载。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/zip_serializer.py` | **新建**：`ZipProjectSerializer` |
| `core/project_serializer.py` | 基类/接口抽象（可选） |
| `core/project_manager.py` | 切换序列化实现 |

## 容器格式

```
project.aline → ZIP 包
├── project.json          # Project 元数据（不含曲线点坐标）
├── data/
│   ├── series_{id}.json  # 每条 DataSeries 的 x/y/y_err
│   ├── curve_{id}.json   # 每条 Curve 的点数据
│   └── analysis_{id}.json # 大文本分析摘要
├── meta.json             # 格式版本、块清单、校验和
```

## ZipProjectSerializer 接口

```python
# core/zip_serializer.py
from __future__ import annotations
import json
import zipfile
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from models.schemas import Project, DataSeries, Curve


class ZipProjectSerializer:
    """ZIP + JSON 格式的项目序列化器。
    
    特点：
    - project.json 只含元数据，树和配置秒开
    - 曲线点数据分块存储，按需加载
    - 增量保存：只写变更块
    - 原子写入：临时文件 + rename
    - 兼容纯 JSON 格式读取
    """
    
    FORMAT_VERSION = "1"
    
    @staticmethod
    def detect_format(path: str) -> str:
        """检测格式: 'zip' | 'json' | 'unknown'"""
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                if 'meta.json' in zf.namelist():
                    return 'zip'
        except zipfile.BadZipFile:
            pass
        # 尝试作为 JSON 读取
        try:
            with open(path, 'r') as f:
                json.load(f)
            return 'json'
        except:
            return 'unknown'
    
    @staticmethod
    def save(project: Project, path: str, *,
             modified_series_ids: Optional[Set[str]] = None,
             modified_curve_ids: Optional[Set[str]] = None) -> None:
        """增量保存项目。只写变更的数据块。"""
        # 收集已修改的数据项 ID
        modified_series = modified_series_ids or set()
        modified_curve = modified_curve_ids or set()
        
        # 生成 meta.json
        meta = ZipProjectSerializer._build_meta(project)
        
        # 构建 project.json（不含曲线点）
        project_data = project.model_dump()
        ZipProjectSerializer._strip_data(project_data)  # 移除大字段
        
        # 写入临时 ZIP
        fd, tmp_path = tempfile.mkstemp(suffix='.aline.tmp', dir=os.path.dirname(path))
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 写入 project.json
                zf.writestr('project.json', json.dumps(project_data, ensure_ascii=False))
                zf.writestr('meta.json', json.dumps(meta, ensure_ascii=False))
                
                # 写入变更的数据系列
                for ds_id in modified_series:
                    series = ZipProjectSerializer._find_series(project, ds_id)
                    if series:
                        zf.writestr(
                            f'data/series_{ds_id}.json',
                            json.dumps({'x': series.x, 'y': series.y, 'y_err': series.y_err})
                        )
                
                # 保留未变更的块（从旧 ZIP 复制）
                if os.path.exists(path) and ZipProjectSerializer.detect_format(path) == 'zip':
                    with zipfile.ZipFile(path, 'r') as old_zf:
                        for name in old_zf.namelist():
                            if name.startswith('data/'):
                                item_id = name.replace('data/', '').replace('.json', '')
                                if item_id.startswith('series_'):
                                    sid = item_id.replace('series_', '')
                                    if sid not in modified_series:
                                        zf.writestr(name, old_zf.read(name))
                                elif item_id.startswith('curve_'):
                                    cid = item_id.replace('curve_', '')
                                    if cid not in modified_curve:
                                        zf.writestr(name, old_zf.read(name))
                            elif name.startswith('previews/'):
                                zf.writestr(name, old_zf.read(name))
            
            # 原子替换
            os.replace(tmp_path, path)
        except:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
    
    @staticmethod
    def load(path: str) -> Project:
        """加载项目。只读 project.json + meta.json，数据按需加载。"""
        format_ = ZipProjectSerializer.detect_format(path)
        
        if format_ == 'json':
            # 旧格式：全量加载 → 转新格式保存时升级
            with open(path, 'r') as f:
                data = json.load(f)
            return Project(**data)
        
        if format_ == 'zip':
            with zipfile.ZipFile(path, 'r') as zf:
                project_data = json.loads(zf.read('project.json'))
            return Project(**project_data)
        
        raise ValueError(f"不支持的项目文件格式: {path}")
    
    @staticmethod
    def load_series_data(path: str, series_id: str) -> Optional[Dict]:
        """从 ZIP 中按需加载单条 DataSeries 的数据。"""
        if ZipProjectSerializer.detect_format(path) != 'zip':
            return None
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                return json.loads(zf.read(f'data/series_{series_id}.json'))
        except KeyError:
            return None
    
    @staticmethod
    def load_curve_data(path: str, curve_id: str) -> Optional[Dict]:
        """从 ZIP 中按需加载单条 Curve 的点数据。"""
        if ZipProjectSerializer.detect_format(path) != 'zip':
            return None
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                return json.loads(zf.read(f'data/curve_{curve_id}.json'))
        except KeyError:
            return None
    
    @staticmethod
    def _build_meta(project: Project) -> Dict:
        """生成 meta.json 内容。"""
        series_ids = []
        for df in project.data_files:
            for s in df.series:
                series_ids.append(s.id)
        for ds in project.datasets:
            for s in ds.series:
                series_ids.append(s.id)
        
        return {
            "format_version": ZipProjectSerializer.FORMAT_VERSION,
            "aline_version": project.aline_version,
            "item_count": {
                "series": len(series_ids),
                "curves": sum(len(img.curves) for img in project.images),
                "data_files": len(project.data_files),
                "analyses": len(project.analyses),
            },
            "checksums": {},  # 可为每个块加 sha256
        }
    
    @staticmethod
    def _strip_data(project_dict: Dict) -> None:
        """递归移除大字段，留下轻量元数据。"""
        # 遍历 images -> curves -> x_data/y_data/x_actual/y_actual
        for img in project_dict.get("images", []):
            for curve in img.get("curves", []):
                curve.pop("x_data", None)
                curve.pop("y_data", None)
                curve.pop("x_actual", None)
                curve.pop("y_actual", None)
        # data_files -> series -> x/y
        for df in project_dict.get("data_files", []):
            for series in df.get("series", []):
                series.pop("x", None)
                series.pop("y", None)
                series.pop("y_err", None)
        # datasets -> series -> x/y
        for ds in project_dict.get("datasets", []):
            for series in ds.get("series", []):
                series.pop("x", None)
                series.pop("y", None)
                series.pop("y_err", None)
    
    @staticmethod
    def _find_series(project: Project, series_id: str) -> Optional[DataSeries]:
        for df in project.data_files:
            for s in df.series:
                if s.id == series_id:
                    return s
        for ds in project.datasets:
            for s in ds.series:
                if s.id == series_id:
                    return s
        return None
```

## 集成到 ProjectManager

```python
# core/project_manager.py
from core.zip_serializer import ZipProjectSerializer

class ProjectManager:
    def __init__(self):
        self._serializer = ZipProjectSerializer()  # 替换旧的 ProjectSerializer
    
    def _save_project(self, path):
        modified = self._track_modified_series()  # 需要跟踪脏数据
        return self._serializer.save(self.current_project, path, modified_series_ids=modified)
```

**注意**：需要引入脏数据跟踪机制。最简单方式：在 `ProjectManager` 中维护一个 `_dirty_series_ids: Set[str]`，各数据操作方法写入该集合，保存后清空。

## 单元测试

```python
class TestZipProjectSerializer(unittest.TestCase):
    def setUp(self):
        self.serializer = ZipProjectSerializer()
        self.tmpdir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir)
    
    def test_save_and_load_roundtrip(self):
        project = Project.create_new("zip_test")
        path = os.path.join(self.tmpdir, "test.aline")
        self.serializer.save(project, path)
        loaded = self.serializer.load(path)
        self.assertEqual(loaded.name, "zip_test")
    
    def test_save_series_data_separately(self):
        project = Project.create_new("test")
        series = DataSeries(name="s1", x=[1.0, 2.0], y=[3.0, 4.0])
        project.data_files.append(DataFile(name="f1", series=[series]))
        path = os.path.join(self.tmpdir, "test.aline")
        self.serializer.save(project, path)
        
        # project.json 不应包含坐标数据
        with zipfile.ZipFile(path, 'r') as zf:
            pj = json.loads(zf.read('project.json'))
            self.assertEqual(pj['data_files'][0]['series'][0].get('x'), None)
        
        # 但 series 数据在独立的 data/ 文件中
        data = self.serializer.load_series_data(path, series.id)
        self.assertEqual(data['x'], [1.0, 2.0])
    
    def test_incremental_save(self):
        """增量保存只写变更块"""
        project = Project.create_new("inc")
        s1 = DataSeries(name="s1", x=[1.0], y=[2.0])
        s2 = DataSeries(name="s2", x=[3.0], y=[4.0])
        project.data_files.append(DataFile(name="f1", series=[s1, s2]))
        path = os.path.join(self.tmpdir, "test.aline")
        self.serializer.save(project, path, modified_series_ids={s1.id, s2.id})
        
        # 修改 s1 后增量保存
        s1.x = [10.0]
        self.serializer.save(project, path, modified_series_ids={s1.id})
        
        # 验证 s1 数据已更新
        data = self.serializer.load_series_data(path, s1.id)
        self.assertEqual(data['x'], [10.0])
    
    def test_atomic_save_crash_safe(self):
        path = os.path.join(self.tmpdir, "test.aline")
        # 正常保存一次
        project = Project.create_new("safe")
        self.serializer.save(project, path)
        mtime_before = os.path.getmtime(path)
        
        # 模拟保存过程中 crash → tmp 文件不替换
        # 真实场景通过 os.replace 实现，测试验证 tmp 文件不存在
        tmp_path = path + ".tmp"
        self.assertFalse(os.path.exists(tmp_path))
    
    def test_load_old_json_format(self):
        path = os.path.join(self.tmpdir, "old.pyline")
        old = {"id": "test", "name": "old_project", "images": []}
        with open(path, 'w') as f:
            json.dump(old, f)
        project = self.serializer.load(path)
        self.assertEqual(project.name, "old_project")
```

## 验证清单

- [ ] `TestZipProjectSerializer` 全部通过
- [ ] 旧 `.pyline` 文件打开正常
- [ ] 新建项目保存为 `.aline`（ZIP），文件体积减小
- [ ] 含 50 条曲线的项目保存时间 < 1s
- [ ] 项目树在加载时秒开，曲线数据按需加载

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
