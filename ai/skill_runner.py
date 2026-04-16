"""
AISkill 沙箱执行器

在受限命名空间中执行用户编写的 Python 代码片段（AISkill），
提供对 project_manager、analysis_engine、data_engine 的只读访问。
"""
from __future__ import annotations

import traceback
from typing import Any, Dict, Optional


# 允许 skill 访问的模块白名单
_ALLOWED_IMPORTS = frozenset([
    "math", "statistics", "json", "re", "datetime",
    "numpy", "scipy", "pandas",
    "core.analysis_engine", "processing.data_engine",
])


def _make_safe_globals(extra: Optional[Dict[str, Any]] = None) -> dict:
    """构造受限全局命名空间。"""
    import math
    import json
    import re
    from datetime import datetime

    safe = {
        "__builtins__": {
            # 安全的内置函数
            "abs": abs, "all": all, "any": any, "bool": bool,
            "dict": dict, "dir": dir, "enumerate": enumerate,
            "filter": filter, "float": float, "format": format,
            "getattr": getattr, "hasattr": hasattr,
            "int": int, "isinstance": isinstance, "issubclass": issubclass,
            "iter": iter, "len": len, "list": list, "map": map,
            "max": max, "min": min, "next": next,
            "print": print, "range": range, "repr": repr,
            "reversed": reversed, "round": round, "set": set,
            "slice": slice, "sorted": sorted, "str": str, "sum": sum,
            "tuple": tuple, "type": type, "zip": zip,
            "True": True, "False": False, "None": None,
        },
        "math": math,
        "json": json,
        "re": re,
        "datetime": datetime,
    }

    # 尝试注入可选科学计算库
    try:
        import numpy as np
        safe["np"] = np
        safe["numpy"] = np
    except ImportError:
        pass
    try:
        import pandas as pd
        safe["pd"] = pd
        safe["pandas"] = pd
    except ImportError:
        pass

    # 注入 project_manager（只读友好）
    try:
        from core.project_manager import project_manager
        safe["project_manager"] = project_manager
    except Exception:
        pass

    # 注入分析引擎函数
    try:
        from core.analysis_engine import (
            fit_curve, detect_peaks, compute_statistics, compute_correlation,
        )
        safe["fit_curve"] = fit_curve
        safe["detect_peaks"] = detect_peaks
        safe["compute_statistics"] = compute_statistics
        safe["compute_correlation"] = compute_correlation
    except Exception:
        pass

    # 注入数据处理函数
    try:
        from processing.data_engine import apply_pipeline
        safe["apply_pipeline"] = apply_pipeline
    except Exception:
        pass

    if extra:
        safe.update(extra)
    return safe


class SkillRunResult:
    """Skill 执行结果。"""

    def __init__(self, success: bool, output: Any = None, error: str = ""):
        self.success = success
        self.output = output      # 最后赋值给 result 变量的值
        self.error = error
        self.stdout: str = ""     # print() 捕获的输出

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "stdout": self.stdout,
        }


class SkillRunner:
    """在沙箱中执行 AISkill 代码。

    使用约定：
    - skill 代码可以通过 print() 输出信息
    - skill 代码将结果赋值给名为 `result` 的变量
    - skill 代码可访问：project_manager, np, pd, fit_curve, detect_peaks,
      compute_statistics, compute_correlation, apply_pipeline
    - 禁止：open(), os, sys, subprocess, exec(), eval() 等危险操作
    """

    MAX_EXECUTION_TIME = 30  # 秒

    def run(
        self,
        code: str,
        extra_vars: Optional[Dict[str, Any]] = None,
    ) -> SkillRunResult:
        """执行 skill 代码并返回结果。"""
        import io
        import sys

        safe_globals = _make_safe_globals(extra_vars)
        local_vars: Dict[str, Any] = {}

        # 捕获 stdout
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured

        try:
            exec(compile(code, "<skill>", "exec"), safe_globals, local_vars)  # noqa: S102
            result_val = local_vars.get("result")
            r = SkillRunResult(success=True, output=result_val)
        except Exception:
            r = SkillRunResult(success=False, error=traceback.format_exc())
        finally:
            sys.stdout = old_stdout
            r.stdout = captured.getvalue()

        return r


# 模块级单例
skill_runner = SkillRunner()
