# Phase 23：ExtensionAPI 拆分

## 目标与完成定义

**目标**：将 1814 行的 `extension_api.py` 按职责拆分为 4 个独立模块，消除"上帝模块"问题。

**完成定义**：
- `ExtensionDefinition` 模块：所有扩展 dataclass 定义、类型系统、配置字段类型
- `ExtensionRegistry` 模块：注册表、查询、迭代、冲突检测、来源管理
- `ExtensionLoader` 模块：文件扫描、import hook、加载报告、外部目录管理
- `ExtensionValidator` 模块：contract validation、版本检查、参数校验、lines_number 校验
- 兼容入口保留，确保现有扩展和测试不修改即可使用

## 当前代码现状

- `core/extension_api.py` — 1814 行，Dataclass 定义、注册、加载、验证、UI 适配 完全混合
- 被加载函数、UI 页面、设置页、`data_engine.py`、`analysis_engine.py` 等多处 import
- 模块级全局 `extension_registry` 单例隐式附加在此模块中
- 文件头部密集的 `normalize_*` 函数群（约 100 行）属于验证逻辑

## 优化方案

### 1. 提取 ExtensionDefinition

```python
# core/extension_definition.py
@dataclass(frozen=True)
class ExtensionConfigField: ...  # 已定义
@dataclass(frozen=True)
class ProcessingExtension: ...
@dataclass(frozen=True)
class AnalysisExtension: ...
@dataclass(frozen=True)
class PlotExtension: ...
@dataclass(frozen=True)
class DigitizeExtension: ...
@dataclass
class PlotExtensionContext: ...
@dataclass(frozen=True)
class PlotStyleExtension: ...
@dataclass(frozen=True)
class CurveStyleExtension: ...

# 类型系统
def normalize_extension_field_type(field_type, *, key=None, choices=None) -> str: ...
def normalize_extension_version(version, *, default=None) -> str: ...
# 其他 normalize 函数
```

### 2. 提取 ExtensionRegistry

```python
# core/extension_registry.py
class ExtensionRegistry:
    def register_processing(self, ext: ProcessingExtension) -> None: ...
    def register_analysis(self, ext: AnalysisExtension) -> None: ...
    def register_plot(self, ext: PlotExtension) -> None: ...
    def register_digitize(self, ext: DigitizeExtension) -> None: ...
    def get_processing(self, type_: str) -> Optional[ProcessingExtension]: ...
    def get_analysis(self, type_: str) -> Optional[AnalysisExtension]: ...
    def iter_extensions(self, category: str) -> Iterator: ...
    def detect_conflicts(self) -> List[str]: ...
    def get_categories(self) -> Dict[str, List]: ...

extension_registry = ExtensionRegistry()  # 全局单例
```

### 3. 提取 ExtensionLoader

```python
# core/extension_loader.py
def load_configured_extensions(dirs: List[str]) -> LoadReport: ...
def scan_directory(directory: str) -> List[str]: ...
def reload_extensions() -> LoadReport: ...
def get_extension_load_status() -> dict: ...
```

### 4. 提取 ExtensionValidator

```python
# core/extension_validator.py
def validate_extension(ext) -> List[str]: ...
def validate_lines_number(raw) -> Optional[Tuple[int, int]]: ...
def validate_lines_list(value, lines_number, *, present) -> List[int]: ...
def validate_version(version) -> bool: ...
def check_compatibility(ext, aline_version) -> List[str]: ...
```

### 5. extension_api.py 保留为兼容入口

```python
# core/extension_api.py — 仅重导出
from core.extension_definition import *  # noqa
from core.extension_registry import extension_registry  # noqa
from core.extension_loader import load_configured_extensions  # noqa
# ... 其他重导出
```

## 迁移策略

1. 创建 4 个新模块，从现有 `extension_api.py` 逐块复制代码
2. 每复制一块，在 `extension_api.py` 中改为重导出
3. 运行全量测试确保无断裂
4. 逐步迁移 import 路径
5. 最后清理 `extension_api.py` 使其成为纯重导出层

## 验收要点

- 4 个新模块各职责明确，无交叉依赖
- 所有现有扩展正常加载和执行
- 所有现有测试通过
- `extension_api.py` 最终成为纯重导出层（<50 行）

## 边界与约束

- 不改变扩展注册/调用的外部行为
- 不改变扩展文件格式和注册函数签名
- 不改变 `extension_registry` 全局单例的存在方式
