from __future__ import annotations

"""外部扩展沙箱执行器。

为 source_kind='external' 的扩展提供 subprocess 沙箱执行选项，
隔离崩溃和超时，保护主进程。
"""

import multiprocessing
import pickle
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.extension_definition import Line, Point


def _sandbox_target(
    handler_pickle: bytes,
    lines_pickle: bytes,
    params_pickle: bytes,
    result_queue: multiprocessing.Queue[dict[str, Any]],
) -> None:
    """在子进程中执行扩展 handler。

    Args:
        handler_pickle: pickled handler callable
        lines_pickle: pickled lines input
        params_pickle: pickled params dict
        result_queue: multiprocessing.Queue for returning result
    """
    try:
        import pickle as _pickle
        handler = _pickle.loads(handler_pickle)
        lines = _pickle.loads(lines_pickle)
        params = _pickle.loads(params_pickle)
        result = handler(lines, params)
        result_queue.put({"success": True, "result": result})
    except Exception as e:
        result_queue.put({
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        })


class SandboxedExtensionRunner:
    """在 subprocess 中执行扩展 handler。

    通过 multiprocessing (spawn) 启动子进程运行 handler，
    实现进程级崩溃隔离和超时终止。

    限制：
      - 仅支持 ProcessingExtension / AnalysisExtension / DigitizeExtension
      - 不支持 PlotExtension（需要操作主进程 matplotlib figure）
      - 通信开销：每次调用需序列化/反序列化参数和结果
    """

    DEFAULT_TIMEOUT = 30  # 秒

    @staticmethod
    def run(
        handler: Callable[..., Any],
        lines: List[Line],
        params: Dict[str, Any],
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """在子进程中运行 handler 并返回结果。

        Args:
            handler: 扩展处理函数
            lines: 输入曲线列表
            params: 扩展参数
            timeout: 超时秒数（默认 30）

        Returns:
            dict with keys:
                success (bool): 执行是否成功
                result (Any): 成功时的返回值
                error (str): 失败/超时时的错误信息
                traceback (str): 失败时的调用栈
        """
        ctx = multiprocessing.get_context("spawn")
        queue: multiprocessing.Queue[dict[str, Any]] = ctx.Queue()

        proc = ctx.Process(
            target=_sandbox_target,
            args=(
                pickle.dumps(handler),
                pickle.dumps(lines),
                pickle.dumps(params),
                queue,
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
