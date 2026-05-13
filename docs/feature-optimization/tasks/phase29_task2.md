# Phase 29 Task 2: 加载时版本兼容性检查

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 29`

## 目标

在扩展加载时校验 `aline_api_version` 与当前 ALine 版本的兼容性，不兼容时给出警告或禁用。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_validator.py` | 实现 `check_compatibility` |
| `core/extension_loader.py` | 加载后调用兼容性检查 |
| `core/extension_registry.py` | 注册时可选校验 |

## 兼容性检查

```python
# core/extension_validator.py 追加
from packaging.specifiers import SpecifierSet
from packaging.version import Version

# 如果不想引入 packaging，用简单实现：

def check_api_compatibility(
    aline_api_version: str,
    aline_version: str,
) -> str:
    """检查扩展声明的 API 版本是否兼容。
    
    Returns:
        "compatible" | "warning" | "incompatible"
    """
    if not aline_api_version:
        return "compatible"  # 未声明 = 不检查
    
    # 解析当前版本
    current = tuple(int(x) for x in aline_version.split("."))
    
    try:
        # 处理 ">=0.3"
        if aline_api_version.startswith(">="):
            required_str = aline_api_version[2:].strip()
            required = tuple(int(x) for x in required_str.split("."))
            if current < required:
                return "incompatible"
        
        # 处理 ">=0.3,<0.5"
        elif "," in aline_api_version:
            parts = aline_api_version.split(",")
            for part in parts:
                part = part.strip()
                if part.startswith(">="):
                    req = tuple(int(x) for x in part[2:].strip().split("."))
                    if current < req:
                        return "incompatible"
                elif part.startswith("<"):
                    req = tuple(int(x) for x in part[1:].strip().split("."))
                    if current >= req:
                        return "incompatible"
        
        # 精确匹配 "0.3"
        else:
            exact = tuple(int(x) for x in aline_api_version.split("."))
            if current != exact:
                return "incompatible"
    
    except (ValueError, IndexError):
        return "warning"  # 解析失败 → 警告但不阻止
    
    return "compatible"
```

## 集成到加载流程

```python
# core/extension_loader.py
from core.extension_validator import check_api_compatibility
from core import __version__  # 需要定义版本常量

# ALINE_VERSION = "0.3.0"  # 在 core/__init__.py 中定义

def _call_register_function(module, registry):
    errors = []
    try:
        module.register_extensions(registry)
    except Exception as e:
        errors.append(str(e))
        return errors
    
    # 检查所有已注册扩展的版本兼容性
    for ext_type in ["processing", "analysis", "plot", "digitize"]:
        ext_dict = getattr(registry, f"_{ext_type}", {})
        for type_, ext in ext_dict.items():
            api_version = getattr(ext, "aline_api_version", "")
            result = check_api_compatibility(api_version, ALINE_VERSION)
            if result == "incompatible":
                errors.append(
                    f"扩展 '{ext.name}' 需要 ALine {api_version}，"
                    f"当前版本 {ALINE_VERSION}，已禁用"
                )
                # 从注册表中移除
                ext_dict.pop(type_, None)
            elif result == "warning":
                errors.append(
                    f"扩展 '{ext.name}' 版本声明解析失败: {api_version}"
                )
    
    return errors
```

## 单元测试

```python
class TestVersionCompatibility(unittest.TestCase):
    def test_compatible_exact(self):
        self.assertEqual(
            check_api_compatibility("0.3", "0.3.0"), "compatible")
    
    def test_compatible_minimum(self):
        self.assertEqual(
            check_api_compatibility(">=0.3", "0.3.0"), "compatible")
        self.assertEqual(
            check_api_compatibility(">=0.2", "0.3.0"), "compatible")
    
    def test_incompatible_too_new(self):
        self.assertEqual(
            check_api_compatibility(">=0.5", "0.3.0"), "incompatible")
    
    def test_incompatible_wrong_exact(self):
        self.assertEqual(
            check_api_compatibility("0.4", "0.3.0"), "incompatible")
    
    def test_no_declaration(self):
        self.assertEqual(
            check_api_compatibility("", "0.3.0"), "compatible")
    
    def test_range(self):
        self.assertEqual(
            check_api_compatibility(">=0.3,<0.5", "0.3.0"), "compatible")
        self.assertEqual(
            check_api_compatibility(">=0.3,<0.5", "0.5.0"), "incompatible")
```

## 验证清单

- [ ] 版本兼容检查在加载时自动运行
- [ ] 不兼容扩展不加载且在加载报告中显示错误
- [ ] 未声明版本的扩展正常加载
- [ ] 测试全部通过

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
