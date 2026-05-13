# Phase 23 Task 4: 提取 ExtensionValidator 模块

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 23`

## 目标

从 `core/extension_api.py` 中提取所有扩展校验逻辑到独立的 `core/extension_validator.py` 模块。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_api.py` | 移除校验函数，改为重导出 |
| `core/extension_validator.py` | **新建** |
| `core/extension_loader.py` | 加载过程中调用 validator |
| `ui/widgets/extension_panel.py` | 迁移 import |
| `tests/test_extension_validator.py` | **新建** |

## 需要移动的内容

```python
# 从 extension_api.py 中提取所有 validate 函数：

# lines 校验
validate_extension_lines_list(value, lines_number, *, present) -> List[int]
validate_extension_lines_number(raw) -> Tuple[int, int]  # 已有 normalize，validate 包装

# version 校验  
validate_extension_version(version) -> bool

# 扩展完整性校验
validate_extension(ext) -> List[str]
  # 检查: type 非空, name 非空, handler 可调用, version 合法,
  #       source_kind 在允许集合中, config_fields 字段合法

# 兼容性校验
check_extension_compatibility(ext, aline_version: str) -> List[str]

# source_kind 校验
validate_source_kind(kind) -> bool
```

## ExtensionValidator 接口设计

```python
# core/extension_validator.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from core.extension_definition import (
    ProcessingExtension, AnalysisExtension, PlotExtension, DigitizeExtension,
    normalize_extension_version, normalize_extension_source_kind,
    normalize_extension_tool_tier, normalize_extension_lines_number,
)


class ExtensionValidator:
    """扩展校验器 — 对注册的扩展做完整性、兼容性和参数校验。"""
    
    @staticmethod
    def validate_extension(ext: Any) -> List[str]:
        """对单个扩展做完整校验，返回错误列表（空 = 通过）。"""
        errors = []
        
        # 1. 基础字段
        if not getattr(ext, "type", None):
            errors.append("扩展缺少 type")
        if not getattr(ext, "name", None):
            errors.append("扩展缺少 name")
        if not callable(getattr(ext, "handler", None)):
            errors.append("扩展 handler 不可调用")
        
        # 2. 版本
        version = getattr(ext, "version", None)
        if version:
            try:
                normalize_extension_version(version)
            except ValueError as e:
                errors.append(f"版本格式错误: {e}")
        
        # 3. source_kind
        try:
            normalize_extension_source_kind(getattr(ext, "source_kind", None))
        except ValueError as e:
            errors.append(f"source_kind 无效: {e}")
        
        # 4. lines_number（处理/分析扩展）
        if hasattr(ext, "lines_number") and getattr(ext, "lines_number", None) is not None:
            try:
                normalize_extension_lines_number(getattr(ext, "lines_number"))
            except ValueError as e:
                errors.append(f"lines_number 无效: {e}")
        
        # 5. config_fields
        config_fields = getattr(ext, "config_fields", None) or []
        for i, field in enumerate(config_fields):
            if not getattr(field, "key", None):
                errors.append(f"config_fields[{i}] 缺少 key")
            if not getattr(field, "label", None):
                errors.append(f"config_fields[{i}] 缺少 label")
        
        return errors
    
    @staticmethod
    def check_compatibility(ext: Any, aline_version: str) -> List[str]:
        """检查扩展声明的兼容版本与当前 ALine 版本是否匹配。"""
        api_version = getattr(ext, "aline_api_version", None)
        if not api_version:
            return []  # 未声明 = 不检查
        
        warnings = []
        # 简单版本比较（v0.3+）
        current = tuple(int(x) for x in aline_version.split("."))
        required = tuple(int(x) for x in api_version.lstrip(">=").split("."))
        
        if api_version.startswith(">=") and current < required:
            warnings.append(f"需要 ALine {api_version}，当前版本 {aline_version}")
        elif api_version.startswith("<") and current >= required:
            warnings.append(f"不支持 ALine {api_version} 以上版本")
        
        return warnings
    
    @staticmethod
    def validate_param_value(key: str, value: Any, field_def) -> Optional[str]:
        """校验单个参数值是否符合字段定义。"""
        field_type = getattr(field_def, "field_type", "string")
        
        if field_type == "integer":
            if not isinstance(value, int):
                return f"{key} 应为整数"
            min_v = getattr(field_def, "min_value", None)
            max_v = getattr(field_def, "max_value", None)
            if min_v is not None and value < min_v:
                return f"{key} 不能小于 {min_v}"
            if max_v is not None and value > max_v:
                return f"{key} 不能大于 {max_v}"
        
        elif field_type == "number":
            try:
                val = float(value)
            except (TypeError, ValueError):
                return f"{key} 应为数值"
            min_v = getattr(field_def, "min_value", None)
            max_v = getattr(field_def, "max_value", None)
            if min_v is not None and val < min_v:
                return f"{key} 不能小于 {min_v}"
            if max_v is not None and val > max_v:
                return f"{key} 不能大于 {max_v}"
        
        elif field_type == "selective":
            choices = getattr(field_def, "choices", [])
            if choices and value not in choices:
                return f"{key} 的值不在可选范围内"
        
        elif field_type == "boolean":
            if not isinstance(value, bool):
                return f"{key} 应为布尔值"
        
        return None
```

## 集成到加载流程

在 `ExtensionLoader._call_register_function` 中增加校验：

```python
# extension_loader.py
from core.extension_validator import ExtensionValidator

def _call_register_function(module, registry):
    errors = []
    # 先注册
    try:
        module.register_extensions(registry)
    except Exception as e:
        errors.append(f"register_extensions 执行失败: {e}")
        return errors
    
    # 再校验全部已注册扩展
    validator = ExtensionValidator()
    for cat_name in ["processing", "analysis", "plot", "digitize"]:
        cat_exts = getattr(registry, f"_" + cat_name, {})
        for type_, ext in cat_exts.items():
            ext_errors = validator.validate_extension(ext)
            for err in ext_errors:
                errors.append(f"{cat_name}/{type_}: {err}")
    
    return errors
```

## 单元测试

```python
class TestExtensionValidator(unittest.TestCase):
    def setUp(self):
        self.validator = ExtensionValidator()
    
    def test_validate_valid_extension(self):
        ext = ProcessingExtension(
            type="valid", name="Valid", handler=lambda l, p: l[0],
            version="1.0.0", source_kind="builtin",
        )
        errors = self.validator.validate_extension(ext)
        self.assertEqual(errors, [])
    
    def test_validate_missing_type(self):
        ext = ProcessingExtension(type="", name="", handler=None, source_kind="")
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("type" in e for e in errors))
        self.assertTrue(any("name" in e for e in errors))
        self.assertTrue(any("handler" in e for e in errors))
    
    def test_validate_bad_version(self):
        ext = ProcessingExtension(
            type="v", name="V", handler=lambda l, p: l[0],
            version="bad", source_kind="builtin",
        )
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("版本" in e for e in errors))
    
    def test_validate_config_fields(self):
        from core.extension_definition import ExtensionConfigField
        ext = ProcessingExtension(
            type="cf", name="CF", handler=lambda l, p: l[0],
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(key="", label=""),  # 缺 key
            ]
        )
        errors = self.validator.validate_extension(ext)
        self.assertTrue(any("key" in e for e in errors))
    
    def test_check_compatibility_ok(self):
        ext = ProcessingExtension(
            type="c", name="C", handler=lambda l, p: l[0],
            source_kind="builtin", aline_api_version=">=0.3",
        )
        warnings = self.validator.check_compatibility(ext, "0.3.0")
        self.assertEqual(warnings, [])
    
    def test_check_compatibility_too_new(self):
        ext = ProcessingExtension(
            type="c2", name="C2", handler=lambda l, p: l[0],
            source_kind="builtin", aline_api_version=">=0.5",
        )
        warnings = self.validator.check_compatibility(ext, "0.3.0")
        self.assertTrue(any("0.5" in w for w in warnings))
```

## 验证清单

- [ ] `TestExtensionValidator` 全部通过
- [ ] 合法扩展正常加载，无警告
- [ ] 非法扩展（缺 type、坏 version 等）在加载报告中出现明确错误
- [ ] 参数校验在 UI 上正确显示错误
- [ ] 向后兼容：无 aline_api_version 的扩展不会被拒绝

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`
