# Phase 22 Task 1: 抽取 ProjectSerializer

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `start`，阶段 `Phase 22`，验证范围 `测试全量通过`

## 目标

从 2708 行的 `core/project_manager.py` 中提取项目文件序列化/反序列化逻辑为独立的 `core/project_serializer.py` 模块。只做代码移动+委托调用，不改变任何外部行为。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/project_manager.py` | 移除 `_save_project`, `_load_project`, `_migrate_project_v2`, `_upgrade_*` 等方法；改为委托 `ProjectSerializer` |
| `core/project_serializer.py` | **新建**：`ProjectSerializer` 类 |
| `tests/test_backend.py` | 补充 `ProjectSerializer` 的单元测试 |

## 详细实施步骤

### Step 1: 识别需要移动的方法

从 `ProjectManager` 中找出所有序列化/反序列化相关方法：

```python
# 需要移动的方法清单（约 15-20 个）:
_project_path()          # 项目文件路径解析
_save_project(path)      # 保存完整项目
_save_project_inner()    # 实际写入逻辑
_load_project(path)      # 加载项目文件
_migrate_project_v2()    # v1 → v2 迁移
_upgrade_project_tree()  # 树结构升级
_ensure_backup()         # 备份
_migrate_old_curve_refs() # 旧曲线引用迁移
_convert_*()             # 各种格式转换
```

精确位置确认：在 `project_manager.py` 中搜索 `def _save`, `def _load`, `def _migrate`, `def _upgrade`, `def _convert` 等模式。

### Step 2: 新建 ProjectSerializer 类

```python
# core/project_serializer.py
"""项目文件序列化层 — 读写 .pyline / .aline 文件，处理版本迁移"""

from __future__ import annotations
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.schemas import Project


class ProjectSerializer:
    """项目文件序列化器。
    
    职责：
    - 将 Project 对象写入 .pyline 文件
    - 从 .pyline 文件加载 Project 对象
    - 处理旧版本格式迁移（v1 → v2 → v3）
    - 写时备份防止数据丢失
    """
    
    SUFFIX = ".aline"
    
    @staticmethod
    def save(project: Project, path: str) -> None:
        """将 project 序列化到 path。写入临时文件后原子 rename。"""
        ...
    
    @staticmethod
    def load(path: str) -> Project:
        """从 path 加载 Project，自动检测版本并迁移。"""
        ...
    
    @staticmethod
    def detect_format(path: str) -> str:
        """检测文件格式: 'pyline_v1' | 'pyline_v2' | 'aline_v3'"""
        ...
    
    @staticmethod
    def migrate(project: Project, target_version: str) -> Project:
        """将 project 迁移到目标格式版本。"""
        ...
```

关键实现细节：

`save()` 的原子写入模式：
```python
temp_path = path + ".tmp"
try:
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(project.model_dump(), f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, path)  # 原子替换
except:
    if os.path.exists(temp_path):
        os.remove(temp_path)
    raise
```

`load()` 的版本检测+迁移链：
```python
format_ = cls.detect_format(path)
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

project = Project(**data)
if project.aline_version is None:
    project = cls._migrate_v1_to_v2(project)
if project.aline_version and project.aline_version < "0.3":
    project = cls._migrate_v2_to_v3(project)
return project
```

### Step 3: 在 ProjectManager 中替换

```python
# core/project_manager.py 顶部
from core.project_serializer import ProjectSerializer

class ProjectManager:
    def __init__(self):
        self._serializer = ProjectSerializer()  # 实例化替代直接方法
    
    def _save_project(self, path: str) -> bool:
        try:
            self._serializer.save(self.current_project, path)
            return True
        except Exception as e:
            self._last_operation_error = str(e)
            return False
    
    def _load_project(self, path: str) -> Optional[Project]:
        try:
            return self._serializer.load(path)
        except Exception as e:
            self._last_operation_error = str(e)
            return None
    
    # _migrate_* 方法全部委托到 self._serializer
```

注意：`_save_project_inner` 和 `_project_path` 这类被内部调用的方法也要一并委托。检查所有调用点。

### Step 4: 补充单元测试

在 `tests/test_backend.py` 中追加 `TestProjectSerializer` 类：

```python
class TestProjectSerializer(unittest.TestCase):
    def setUp(self):
        self.serializer = ProjectSerializer()
        self.tmpdir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir)
    
    def test_save_and_load_roundtrip(self):
        """保存再加载，所有字段一致"""
        project = Project.create_new("test")
        path = os.path.join(self.tmpdir, "test.aline")
        self.serializer.save(project, path)
        loaded = self.serializer.load(path)
        self.assertEqual(loaded.name, "test")
        self.assertEqual(loaded.aline_version, "0.3")
    
    def test_load_pyline_v2_auto_migrate(self):
        """加载旧格式自动迁移"""
        # 构造一个 v2 格式的 .pyline 文件（无 aline_version 等字段）
        ...
    
    def test_save_atomic_crash_safe(self):
        """保存中断不破坏原文件"""
        ...
    
    def test_load_nonexistent_file_returns_none(self):
        """路径不存在时返回 None 而非抛异常"""
        ...
    
    def test_load_corrupted_json_returns_none(self):
        """损坏的 JSON 返回 None"""
        ...
```

## 边界情况与错误处理

| 场景 | 预期行为 |
|---|---|
| 路径不存在 | `load()` 返回 `None`，不抛异常 |
| JSON 解析失败 | 返回 `None`，`get_last_error_message()` 返回原因 |
| 字段缺失（旧格式） | Pydantic 取默认值，不崩溃 |
| 保存时磁盘满 | `save()` 返回 False，原文件完整 |
| 并发保存 | 不支持（项目级单线程访问） |

## 验证清单

- [ ] `python -m pytest tests/test_backend.py -k TestProjectSerializer -q` 全部通过
- [ ] 打开一个真实 `.pyline` 项目，功能正常
- [ ] 新建项目→添加数据→保存→关闭→重新打开，数据一致
- [ ] 保存过程中 `kill -9` 进程，原文件不受影响

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，提交范围 `core/project_serializer.py + project_manager.py` 修改
