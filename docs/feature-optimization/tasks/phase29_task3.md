# Phase 29 Task 3: 外部扩展沙箱执行

> **进入前**: 执行 `disciplined-commit` skill，节点类型 `checkpoint`，阶段 `Phase 29`

## 目标

为 `source_kind="external"` 的扩展提供 subprocess 沙箱执行选项，隔离崩溃和无限循环，保护主进程。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `core/extension_sandbox.py` | **新建** |
| `core/extension_loader.py` | 可选标记扩展为沙箱模式 |
| `ui/pages/settings_page.py` | 沙箱模式开关 |

## 沙箱设计

```python
# core/extension_sandbox.py
from __future__ import annotations
import multiprocessing
import pickle
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

# 曲线点类型
Point = Tuple[float, float]
Line = List[Point]


def _sandbox_target(handler_pickle: bytes, lines_pickle: bytes, params_pickle: bytes,
                    result_queue, timeout: int):
    """在子进程中执行扩展 handler。"""
    try:
        import pickle
        handler = pickle.loads(handler_pickle)
        lines = pickle.loads(lines_pickle)
        params = pickle.loads(params_pickle)
        
        result = handler(lines, params)
        result_queue.put({"success": True, "result": result}, timeout=5)
    except Exception as e:
        result_queue.put({
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }, timeout=5)


class SandboxedExtensionRunner:
    """在 subprocess 中执行扩展 handler。"""
    
    DEFAULT_TIMEOUT = 30  # 秒
    
    @staticmethod
    def run(
        handler: Callable,
        lines: List[Line],
        params: Dict[str, Any],
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """在子进程中运行 handler 并返回结果。
        
        Returns:
            成功: {"success": True, "result": line}
            失败: {"success": False, "error": str, "traceback": str}
            超时: {"success": False, "error": "Timeout"}
        """
        import multiprocessing
        ctx = multiprocessing.get_context("spawn")
        queue = ctx.Queue()
        
        proc = ctx.Process(
            target=_sandbox_target,
            args=(
                pickle.dumps(handler),
                pickle.dumps(lines),
                pickle.dumps(params),
                queue,
                timeout,
            ),
        )
        
        proc.start()
        proc.join(timeout=timeout)
        
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            return {"success": False, "error": "扩展执行超时，已强制终止"}
        
        try:
            result = queue.get_nowait()
            return result
        except Exception:
            return {"success": False, "error": "无法获取执行结果"}
```

## 集成到扩展注册

```python
# core/extension_loader.py 加载外部扩展时
if ext.source_kind == "external" and sandbox_enabled:
    # 在 handler 外包装沙箱
    original_handler = ext.handler
    def sandbox_wrapper(lines, params):
        return SandboxedExtensionRunner.run(
            original_handler, lines, params, timeout=30
        )
    object.__setattr__(ext, "handler", sandbox_wrapper)
```

## 限制

- 通信开销：每次调用序列化/反序列化参数和结果
- 仅支持 `ProcessingExtension`、`AnalysisExtension`、`DigitizeExtension`
- 不支持 `PlotExtension`（需要操作主进程的 matplotlib figure）
- 不支持依赖全局状态的扩展

## 设置页控制

```python
# 设置页增加开关
"external_extension_sandbox": {
    "type": "boolean",
    "default": False,  # 默认不启用（兼容现有行为）
    "label": "外部扩展沙箱模式",
    "description": "在独立进程中执行外部扩展，崩溃不影响主应用",
}
```

## 验证清单

- [ ] 沙箱模式下扩展正确执行并返回结果
- [ ] 扩展崩溃（如 `1/0`）不影响主进程
- [ ] 扩展超时（死循环）被自动终止（默认 30s）
- [ ] 沙箱开关在设置页生效
- [ ] 绘图扩展不支持沙箱模式（应给出提示）

> **完成后**: 执行 `disciplined-commit` skill，节点类型 `end`
