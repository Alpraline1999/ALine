# Phase 29：扩展版本管理与沙箱

## 目标与完成定义

**目标**：补齐外部扩展的版本声明、ALine API 兼容性检查和运行时安全沙箱。

**完成定义**：
- 扩展声明自身兼容的 ALine API 版本范围
- 加载时自动校验版本兼容性，不兼容时给出警告/禁用
- 外部扩展可选择在 subprocess 沙箱中执行，隔离崩溃和无限循环
- 扩展依赖关系可声明、可检查

## 当前代码现状

- 扩展版本字段已存在（`version` 字段，x.y.z 格式）
- 无 API 版本声明：扩展不知道它兼容哪个 ALine 版本
- 无兼容性检查：加载时即使版本不匹配也不会警告
- 无沙箱：外部扩展与主进程共享内存，崩溃或死循环会拖垮整个应用
- 无依赖声明：扩展无法声明对其他扩展或 Python 包的依赖

## 优化方案

### 1. 扩展 API 版本声明

在 `ExtensionConfigField`/`ExtensionDefinition` 中增加 `aline_api_version` 字段：

```python
class ProcessingExtension:
    # ... 现有字段 ...
    aline_api_version: str = ">=0.3"  # 兼容版本范围
```

版本范围格式（参考 PEP 440）：
- `"0.3"` — 精确匹配
- `">=0.3"` — 最低版本
- `">=0.3,<0.5"` — 版本范围

### 2. 加载时兼容性检查

在 `ExtensionValidator`（Phase 23）中增加检查逻辑：

```python
def check_api_compatibility(ext_version: str, aline_version: str) -> CompatibilityResult:
    """检查扩展声明的 API 版本与当前 ALine 版本是否兼容"""
    # 使用 packaging.specifiers 或简单实现
```

检查结果分类：
- `compatible` — 正常加载
- `warning` — 可加载但建议升级扩展
- `incompatible` — 禁用扩展并给出明确错误提示

### 3. 沙箱执行（subprocess）

对声明为 `source_kind="external"` 的扩展，提供沙箱执行选项：

```python
class SandboxedExtensionRunner:
    def run_handler(self, handler_path: str, lines, params, timeout: int = 30):
        """在 subprocess 中执行扩展 handler"""
        # 使用 multiprocessing 或 subprocess + pickle 通信
        # 设置超时，超时自动 kill
```

执行策略：
- 内置扩展（`source_kind="builtin"`）：当前进程执行，无沙箱
- 外部扩展（`source_kind="external"`）：可选沙箱模式
- 用户可在设置页选择：始终沙箱/从不沙箱/每次询问

### 4. 依赖声明

```python
class ProcessingExtension:
    depends_on: List[str] = []  # ["extension_a>=1.0", "numpy>=1.20"]
```

加载时检查：
- 其他扩展依赖是否存在且版本匹配
- Python 包依赖是否已安装

## 验收要点

- 声明 `">=0.3"` 的扩展在 ALine 0.3.x 上正常加载
- 声明 `">=0.5"` 的扩展在当前 0.3 版本上被禁用并给出明确提示
- 沙箱模式下扩展崩溃不影响主进程
- 沙箱模式下扩展超时被自动终止（默认 30s）

## 边界与约束

- 版本声明为可选字段，不声明时默认"无兼容性保证"
- 沙箱模式为可选特性，不影响现有扩展的加载和执行路径
- 沙箱通信开销需评估（仅对 CPU 密集型外部扩展启用）
- 不引入重量级容器化方案
