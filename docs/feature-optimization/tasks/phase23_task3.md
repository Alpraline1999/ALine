# Phase 23 Task 3: 提取 ExtensionLoader 模块

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 23`

## 目标

从 `core/extension_api.py` 中提取扩展扫描、加载、重载逻辑到独立的 `core/extension_loader.py` 模块。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_api.py` | 移除加载相关函数，改为重导出 |
| `core/extension_loader.py` | **新建** |
| `main.py` | `import` 路径更新 |
| `ui/pages/settings_page.py` | `import` 路径更新 |
| `ui/widgets/extension_panel.py` | `import` 路径更新 |

## 需要移动的内容

```python
# 从 extension_api.py 中提取:

# 加载入口
load_configured_extensions(builtin_dir, external_dirs) -> LoadReport
reload_extensions(builtin_dir, external_dirs) -> LoadReport
get_extension_load_status() -> dict

# 内部辅助
scan_directory(directory) -> List[str]
_import_extension_module(filepath) -> Optional[ModuleType]
_call_register_function(module, registry) -> List[str]
_path_is_within(path, parent) -> bool
_PATH_CACHE  # 路径缓存

# LoadReport 结构
# {
#   "success": [...],
#   "errors": [...],
#   "total_loaded": int,
#   "total_failed": int,
# }
```

### extension_loader.py 的完整接口

```python
# core/extension_loader.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional
from types import ModuleType

from core.extension_registry import extension_registry


class LoadReport:
    """扩展加载报告。"""
    def __init__(self):
        self.success: List[Dict] = []
        self.errors: List[str] = []
    
    @property
    def total_loaded(self) -> int:
        return len(self.success)
    
    @property
    def total_failed(self) -> int:
        return len(self.errors)


def load_configured_extensions(
    builtin_dir: str,
    external_dirs: Optional[List[str]] = None,
) -> LoadReport:
    """扫描并加载所有扩展。
    
    1. 重置注册表（清除旧扩展）
    2. 扫描 builtin_dir 目录
    3. 扫描 external_dirs 中的每个目录
    4. 对每个合法模块调用 register_extensions(registry)
    5. 生成加载报告
    """
    report = LoadReport()
    
    # 加载内置扩展
    _load_from_directory(builtin_dir, source_kind="builtin", register_fn=None, report=report)
    
    # 加载外部扩展
    for ext_dir in (external_dirs or []):
        _load_from_directory(ext_dir, source_kind="external", register_fn=None, report=report)
    
    return report


def reload_extensions(builtin_dir: str, external_dirs: Optional[List[str]] = None) -> LoadReport:
    """重载所有扩展（先清空注册表）。"""
    # 重置
    extension_registry._processing.clear()
    extension_registry._analysis.clear()
    extension_registry._plot.clear()
    extension_registry._digitize.clear()
    return load_configured_extensions(builtin_dir, external_dirs)


def scan_directory(directory: str) -> List[str]:
    """扫描目录，返回所有可加载的 Python 文件路径。
    
    规则：
    - 只扫描 .py 文件
    - 跳过 __init__.py
    - 跳过 _ 开头的文件
    - 跳过 extension_tools.py 等非扩展文件
    返回绝对路径列表。
    """
    ...


def _load_from_directory(
    directory: str,
    source_kind: str,
    report: LoadReport,
) -> None:
    """扫描并加载单个目录下的所有扩展文件。"""
    for filepath in scan_directory(directory):
        module = _import_extension_module(filepath)
        if module is None:
            report.errors.append(f"无法导入模块: {filepath}")
            continue
        errors = _call_register_function(module, extension_registry)
        for err in errors:
            report.errors.append(f"{filepath}: {err}")
        if not errors:
            report.success.append({
                "file": filepath,
                "module": module.__name__,
                "source_kind": source_kind,
            })


def _import_extension_module(filepath: str) -> Optional[ModuleType]:
    """动态导入一个扩展 Python 文件。"""
    import importlib.util
    import sys
    
    module_name = Path(filepath).stem
    # 避免重复导入
    if module_name in sys.modules:
        del sys.modules[module_name]
    
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        return None
    
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        return None


def _call_register_function(module: ModuleType, registry) -> List[str]:
    """调用模块的 register_extensions(registry)。"""
    errors = []
    if not hasattr(module, "register_extensions"):
        errors.append("模块未提供 register_extensions(registry)")
        return errors
    try:
        module.register_extensions(registry)
    except Exception as e:
        errors.append(f"register_extensions 执行失败: {e}")
    return errors
```

## 关键细节

### 扫描规则

`scan_directory()` 需要精确匹配原有行为：
- 递归扫描所有子目录
- 文件名 `_` 开头 → 跳过
- 文件名匹配 `_NON_EXTENSION_MODULE_FILENAMES` → 跳过
- `__init__.py` → 跳过（除非特意支持）
- `extension_tools.py` → 跳过（不是扩展）

### Load Report

需确保与现有 `get_extension_load_status()` 和 UI 中的加载报告兼容。旧接口调用链：
- `main.py:146` → `load_configured_extensions`
- `settings_page.py` → `get_extension_load_status`
- `extension_panel.py` → `show_extension_load_report_dialog`

## 单元测试

```python
class TestExtensionLoader(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.tmpdir)
    
    def test_scan_directory_finds_py_files(self):
        """扫描目录找到 .py 文件"""
        Path(self.tmpdir, "test_ext.py").write_text("")
        files = scan_directory(self.tmpdir)
        self.assertTrue(any(f.endswith("test_ext.py") for f in files))
    
    def test_scan_directory_skips_underscore_files(self):
        """跳过 _ 开头的文件"""
        Path(self.tmpdir, "_private.py").write_text("")
        files = scan_directory(self.tmpdir)
        self.assertFalse(any(f.endswith("_private.py") for f in files))
    
    def test_scan_directory_skips_extension_tools(self):
        """跳过 extension_tools.py"""
        Path(self.tmpdir, "extension_tools.py").write_text("")
        files = scan_directory(self.tmpdir)
        self.assertFalse(any(f.endswith("extension_tools.py") for f in files))
    
    def test_load_extension_with_register(self):
        """有 register_extensions 的模块正常加载"""
        code = """
from core.extension_definition import ProcessingExtension

def handler(lines, params):
    return lines[0]

def register_extensions(registry):
    registry.register_processing(ProcessingExtension(
        type="test_loader", name="Test", handler=handler, source_kind="builtin"
    ))
"""
        Path(self.tmpdir, "test_loader_ext.py").write_text(code)
        report = load_configured_extensions(self.tmpdir)
        self.assertEqual(report.total_loaded, 1)
    
    def test_load_extension_without_register(self):
        """无 register_extensions 的模块不加载但报错"""
        Path(self.tmpdir, "no_register.py").write_text("x = 1")
        report = load_configured_extensions(self.tmpdir)
        self.assertGreater(len(report.errors), 0)
    
    def test_reload_clears_and_reloads(self):
        """重载清空注册表后重新加载"""
        # 先加载一个
        code = """
from core.extension_definition import ProcessingExtension
def handler(l, p): return l[0]
def register_extensions(reg):
    reg.register_processing(ProcessingExtension(type="t", name="T", handler=handler, source_kind="builtin"))
"""
        Path(self.tmpdir, "reload_test.py").write_text(code)
        load_configured_extensions(self.tmpdir)
        self.assertIsNotNone(extension_registry.get_processing("t"))
        
        # 重载（无扩展目录）
        reload_extensions(self.tmpdir)
        # 原有扩展应该被清空
```

## 验证清单

- [ ] `TestExtensionLoader` 全部通过
- [ ] 应用启动时扩展正常加载（`main.py` 路径）
- [ ] 设置页"重载扩展"按钮正常
- [ ] 无效扩展文件报错不影响整体加载
- [ ] 加载报告在 UI 中正常显示

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
