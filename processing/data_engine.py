"""
数据处理引擎 — 非破坏性操作管道

每个操作用 dict 描述:
  {"type": "smooth",     "params": {"method": "savgol", "window": 11, "poly": 3}}
  {"type": "crop",       "params": {"x_min": 0.0, "x_max": 10.0}}
  {"type": "normalize",  "params": {"mode": "minmax"}}   # "minmax" | "zscore"
    {"type": "resample",   "params": {"mode": "spacing", "spacing_mode": "point", "n": 200}}
    {"type": "resample",   "params": {"mode": "spacing", "spacing_mode": "coord", "step": 0.1}}
    {"type": "resample",   "params": {"mode": "align", "target_line": 1, "algorithm": "linear"}}
  {"type": "fft",        "params": {"output": "amplitude", "detrend": True}}
  {"type": "derivative", "params": {}}
  {"type": "integral",   "params": {"cumulative": True}}
  {"type": "transform",  "params": {"x_expr": "", "y_expr": "y * 1.0"}}
    {"type": "filter",     "params": {"cutoff": 0.1, "order": 4, "mode": "low"}}
    {"type": "pairwise_compute",
     "params": {"primary_index": 1, "secondary_index": 2,
                            "x_expr": "x1", "y_expr": "y1 - y2",
                            "align_mode": "auto", "resample_mode": "count", "n": 200}}

apply_pipeline(xs, ys, ops) → (xs_new, ys_new)
apply_pipeline_to_lines(lines, ops, *, selected_lines=None) → (processed_lines, warnings)

执行语义：
- pipeline 中至多 1 个"双/多曲线"算子（例如声明了 lines_number 且上限大于 1 的扩展）。
- 无此算子：对每条 lines 广播单曲线算子，输出数量 == 输入。
- 存在此算子时：上游单曲线算子对算子引用的输入子集做参数共享的广播，
    中间由双/多曲线算子消费并输出，随后下游算子对输出做常规广播。
- selected_lines 提供完整"已选择列表"池，用于多曲线扩展的 lines_list，
    以及 resample mode=align 的 target_line 查表。
"""
from __future__ import annotations

import cmath
import contextvars
import copy
import math
from typing import Any, Dict, List, Optional, Tuple

from core.extension_api import (
    extension_lines_number,
    extension_registry,
    invoke_processing_extension_handler,
    normalize_extension_lines_list,
)


# 当前 pipeline 执行期间的 "已选择列表" 池，供 _op_resample(mode=align) 等使用。
_pipeline_pool: contextvars.ContextVar = contextvars.ContextVar("_pipeline_pool", default=[])


XY = Tuple[List[float], List[float]]
PipelineLine = Dict[str, Any]
PipelineResult = Tuple[List[PipelineLine], List[str]]


def apply_pipeline(xs: List[float], ys: List[float], ops: List[Dict[str, Any]]) -> XY:
    """按顺序执行操作列表，返回新的 (xs, ys)；原始数据不变。"""
    lines, _warnings = apply_pipeline_to_lines([
        {"x": list(xs), "y": list(ys), "name": ""},
    ], ops)
    if not lines:
        return [], []
    return list(lines[0].get("x", []) or []), list(lines[0].get("y", []) or [])


def apply_operation(xs: List[float], ys: List[float], op: Dict[str, Any]) -> XY:
    lines, _warnings = apply_operation_to_lines([
        {"x": list(xs), "y": list(ys), "name": ""},
    ], op)
    if not lines:
        return [], []
    return list(lines[0].get("x", []) or []), list(lines[0].get("y", []) or [])


def apply_pipeline_to_lines(
    lines: List[PipelineLine],
    ops: List[Dict[str, Any]],
    *,
    selected_lines: Optional[List[PipelineLine]] = None,
) -> PipelineResult:
    """执行 pipeline。见模块文档开头的执行语义说明。

    lines           : 活动集（通常是"已选择列表"中被勾选的那些曲线）。
    selected_lines  : 完整"已选择列表"池；不传时等同 lines。
    """
    active = _normalize_pipeline_lines(lines)
    pool = _normalize_pipeline_lines(selected_lines) if selected_lines is not None else [copy.deepcopy(line) for line in active]

    pairing = _find_single_pairing_op(ops)

    warnings: List[str] = []
    token = _pipeline_pool.set(pool)
    try:
        if pairing is None:
            working = list(active)
            for op in ops or []:
                working, op_warnings = apply_operation_to_lines(working, op)
                warnings.extend(op_warnings)
            return working, warnings

        pairing_index, pairing_op = pairing
        pair_inputs = _resolve_pairing_inputs(pairing_op, pool)
        pre = list(pair_inputs)
        for op in (ops or [])[:pairing_index]:
            if str(op.get("type", "") or "") == "resample" and len(pre) > 1:
                pre, op_warnings = _apply_resample_to_lines(pre, dict(op.get("params", {}) or {}))
            else:
                pre, op_warnings = apply_operation_to_lines(pre, op)
            warnings.extend(op_warnings)

        mid, mid_warnings = _execute_pairing_op(pairing_op, pre)
        warnings.extend(mid_warnings)

        post = list(mid)
        for op in (ops or [])[pairing_index + 1:]:
            post, op_warnings = apply_operation_to_lines(post, op)
            warnings.extend(op_warnings)
        return post, warnings
    finally:
        _pipeline_pool.reset(token)


def apply_operation_to_lines(lines: List[PipelineLine], op: Dict[str, Any]) -> PipelineResult:
    working_lines = _normalize_pipeline_lines(lines)
    if not working_lines:
        return [], []

    t = op.get("type", "")
    p = dict(op.get("params", {}) or {})
    if t == "pairwise_compute":
        return _op_pairwise_compute(working_lines, p)
    if t == "resample" and len(working_lines) > 1:
        return _apply_resample_to_lines(working_lines, p)

    custom_op = extension_registry.get_processing(t)
    if custom_op is not None:
        if _is_multi_line_processing_op(custom_op, op):
            _validate_multiline_processing_extension(custom_op, working_lines)
            return _apply_multiline_processing_extension(custom_op, working_lines, p)

        processed_lines: List[PipelineLine] = []
        for line in working_lines:
            nx, ny = invoke_processing_extension_handler(
                custom_op.handler,
                list(line.get("x", []) or []),
                list(line.get("y", []) or []),
                p,
                working_lines,
            )
            processed_lines.append(_merge_line_payload(line, {"x": nx, "y": ny}))
        return processed_lines, []

    processed_lines = []
    for line in working_lines:
        nx, ny = _apply_builtin_operation(list(line.get("x", []) or []), list(line.get("y", []) or []), t, p)
        processed_lines.append(_merge_line_payload(line, {"x": nx, "y": ny}))
    return processed_lines, []


def _apply_builtin_operation(xs: List[float], ys: List[float], t: str, p: Dict[str, Any]) -> XY:
    if t == "crop":
        return _op_crop(xs, ys, p)
    if t == "smooth":
        return _op_smooth(xs, ys, p)
    if t == "normalize":
        return _op_normalize(xs, ys, p)
    if t == "resample":
        return _op_resample(xs, ys, p)
    if t == "fft":
        return _op_fft(xs, ys, p)
    if t == "derivative":
        return _op_derivative(xs, ys, p)
    if t == "integral":
        return _op_integral(xs, ys, p)
    if t == "transform":
        return _op_transform(xs, ys, p)
    if t == "filter":
        return _op_filter(xs, ys, p)
    return xs, ys


def _normalize_pipeline_lines(lines: List[PipelineLine]) -> List[PipelineLine]:
    normalized: List[PipelineLine] = []
    for index, item in enumerate(lines or []):
        if isinstance(item, dict):
            payload = dict(item)
            xs = list(payload.get("x", []) or [])
            ys = list(payload.get("y", []) or [])
            payload["x"] = xs
            payload["y"] = ys
            payload["name"] = str(payload.get("name", f"line_{index + 1}") or f"line_{index + 1}")
        else:
            xs = list(getattr(item, "x", []) or [])
            ys = list(getattr(item, "y", []) or [])
            payload = {
                "name": str(getattr(item, "name", f"line_{index + 1}") or f"line_{index + 1}"),
                "x": xs,
                "y": ys,
            }
        normalized.append(payload)
    return normalized


def _merge_line_payload(base: PipelineLine, update: Dict[str, Any]) -> PipelineLine:
    merged = dict(base or {})
    for key, value in dict(update or {}).items():
        if key in {"warnings", "lines"}:
            continue
        merged[key] = value
    merged["x"] = list(merged.get("x", []) or [])
    merged["y"] = list(merged.get("y", []) or [])
    merged["name"] = str(merged.get("name", "") or "")
    return merged


def _op_lines_list(op: Dict[str, Any]) -> Tuple[List[int], bool]:
    params = dict(op.get("params", {}) or {})
    if "lines_list" in params:
        return normalize_extension_lines_list(params.get("lines_list")), True
    legacy_cfg = params.get("lines")
    if isinstance(legacy_cfg, dict) and "lines_list" in legacy_cfg:
        return normalize_extension_lines_list(legacy_cfg.get("lines_list")), True
    return [], False


def _is_multi_line_processing_op(extension: Any, op: Dict[str, Any]) -> bool:
    del op
    lines_number = extension_lines_number(extension)
    if lines_number is None:
        return False
    _lower, upper = lines_number
    return upper == -1 or upper > 1


def _is_pairing_op(op: Dict[str, Any]) -> bool:
    extension = extension_registry.get_processing(str(op.get("type", "") or ""))
    if extension is None:
        return False
    return _is_multi_line_processing_op(extension, op)


def _find_single_pairing_op(ops: List[Dict[str, Any]]) -> Optional[Tuple[int, Dict[str, Any]]]:
    found: List[Tuple[int, Dict[str, Any]]] = []
    for index, op in enumerate(ops or []):
        if _is_pairing_op(op):
            found.append((index, op))
    if len(found) > 1:
        raise ValueError("pipeline 中不应有超过一个双曲线处理工具或多曲线处理扩展")
    return found[0] if found else None


def _pick_from_pool(pool: List[PipelineLine], index_1based: Any) -> PipelineLine:
    try:
        index = int(index_1based)
    except (TypeError, ValueError):
        raise ValueError(f"无效的曲线下标: {index_1based!r}")
    if index < 1 or index > len(pool):
        raise ValueError(f"曲线下标 {index} 超出已选择列表范围 (共 {len(pool)} 条)")
    return pool[index - 1]


def _normalize_lines_list(raw: Any, pool_size: int) -> List[int]:
    normalized = normalize_extension_lines_list(raw)
    if normalized:
        return normalized
    return list(range(1, pool_size + 1))


def _resolve_pairing_inputs(op: Dict[str, Any], pool: List[PipelineLine]) -> List[PipelineLine]:
    t = str(op.get("type", "") or "")
    extension = extension_registry.get_processing(t)
    lines_number = extension_lines_number(extension) if extension is not None else None
    indices, present = _op_lines_list(op)
    if extension is not None and lines_number is not None and not present:
        raise ValueError(f"{extension.name} 需要显式选择输入曲线")
    chosen = [copy.deepcopy(_pick_from_pool(pool, idx)) for idx in indices]
    if extension is not None:
        _validate_multiline_processing_extension(extension, chosen)
    return chosen


def _execute_pairing_op(op: Dict[str, Any], lines: List[PipelineLine]) -> PipelineResult:
    t = str(op.get("type", "") or "")
    p = dict(op.get("params", {}) or {})
    if t == "pairwise_compute":
        return _op_pairwise_compute(lines, p)
    extension = extension_registry.get_processing(t)
    if extension is None:
        raise ValueError(f"未知的多曲线处理算子: {t}")
    _validate_multiline_processing_extension(extension, lines)
    return _apply_multiline_processing_extension(extension, lines, p)


def _validate_pipeline_multiline_conflicts(lines: List[PipelineLine], ops: List[Dict[str, Any]]) -> None:
    _find_single_pairing_op(ops)


def _validate_multiline_processing_extension(extension: Any, lines: List[PipelineLine]) -> None:
    count = len(lines)
    lines_number = extension_lines_number(extension)
    if lines_number is None:
        return
    min_lines, max_lines = lines_number
    if count < min_lines:
        raise ValueError(f"{extension.name} 至少需要 {min_lines} 条输入曲线")
    if max_lines != -1 and count > max_lines:
        raise ValueError(f"{extension.name} 最多支持 {max_lines} 条输入曲线")


def _apply_multiline_processing_extension(
    extension: Any,
    lines: List[PipelineLine],
    params: Dict[str, Any],
) -> PipelineResult:
    primary = lines[0]
    result = invoke_processing_extension_handler(
        extension.handler,
        list(primary.get("x", []) or []),
        list(primary.get("y", []) or []),
        params,
        lines,
    )
    return _normalize_multiline_extension_result(result, primary)


def _normalize_multiline_extension_result(result: Any, template_line: PipelineLine) -> PipelineResult:
    warnings: List[str] = []
    payload = result
    if isinstance(result, dict) and "lines" in result:
        warnings = _normalize_warning_messages(result.get("warnings", []))
        payload = result.get("lines", [])
    elif isinstance(result, dict):
        warnings = _normalize_warning_messages(result.get("warnings", []))
        payload = [
            {
                key: value
                for key, value in result.items()
                if key not in {"warnings", "lines"}
            }
        ]
    return _normalize_processing_output_lines(payload, template_line), warnings


def _normalize_processing_output_lines(payload: Any, template_line: PipelineLine) -> List[PipelineLine]:
    if _looks_like_xy(payload):
        xs, ys = payload
        return [_merge_line_payload(template_line, {"x": list(xs), "y": list(ys)})]

    if isinstance(payload, list):
        normalized_lines: List[PipelineLine] = []
        for index, item in enumerate(payload):
            base = template_line if index == 0 else {"name": f"{template_line.get('name', 'result')}#{index + 1}"}
            if _looks_like_xy(item):
                xs, ys = item
                normalized_lines.append(_merge_line_payload(base, {"x": list(xs), "y": list(ys)}))
                continue
            if isinstance(item, dict):
                normalized_lines.append(_merge_line_payload(base, item))
                continue
            raise ValueError("多曲线处理扩展返回结果格式无效")
        return normalized_lines

    raise ValueError("多曲线处理扩展返回结果格式无效")


def _normalize_warning_messages(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw).strip()
    return [text] if text else []


def _looks_like_xy(payload: Any) -> bool:
    return (
        isinstance(payload, (list, tuple))
        and len(payload) == 2
        and not isinstance(payload[0], dict)
        and not isinstance(payload[1], dict)
    )


def align_lines_to_common_x(
    lines: List[PipelineLine],
    params: Optional[Dict[str, Any]] = None,
) -> PipelineResult:
    prepared_lines = [_sorted_line_payload(line) for line in _normalize_pipeline_lines(lines)]
    if len(prepared_lines) < 2:
        return prepared_lines, []
    if _lines_share_same_x(prepared_lines):
        return prepared_lines, []

    options = dict(params or {})
    align_mode = str(options.get("align_mode", "auto") or "auto").strip().lower()
    if align_mode == "strict":
        raise ValueError("输入曲线 X 坐标未对齐，需进行坐标间距重采样")

    grid = _build_alignment_grid(prepared_lines, options)
    aligned_lines = []
    for line in prepared_lines:
        aligned_lines.append(_merge_line_payload(line, {
            "x": list(grid),
            "y": [_interp_linear(x_value, list(line.get("x", []) or []), list(line.get("y", []) or [])) for x_value in grid],
        }))

    description = _describe_alignment_mode(options, len(grid))
    warnings = [
        "需进行坐标间距重采样",
        f"输入曲线 X 坐标未对齐，已在重叠区间内按{description}自动重采样。",
    ]
    return aligned_lines, warnings


def _sorted_line_payload(line: PipelineLine) -> PipelineLine:
    xs, ys = _sorted_unique_xy(list(line.get("x", []) or []), list(line.get("y", []) or []))
    return _merge_line_payload(line, {"x": xs, "y": ys})


def _lines_share_same_x(lines: List[PipelineLine]) -> bool:
    if len(lines) < 2:
        return True
    base_x = list(lines[0].get("x", []) or [])
    for line in lines[1:]:
        current_x = list(line.get("x", []) or [])
        if len(current_x) != len(base_x):
            return False
        for left, right in zip(base_x, current_x):
            if not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9):
                return False
    return True


def _build_alignment_grid(lines: List[PipelineLine], params: Dict[str, Any]) -> List[float]:
    starts = [float(line["x"][0]) for line in lines if len(line.get("x", []) or []) >= 2]
    ends = [float(line["x"][-1]) for line in lines if len(line.get("x", []) or []) >= 2]
    if not starts or not ends:
        raise ValueError("自动对齐至少需要每条曲线包含两个有效采样点")
    x_start = max(starts)
    x_end = min(ends)
    if x_end - x_start <= 1e-12:
        raise ValueError("输入曲线没有足够的重叠区间，无法执行自动对齐")

    resample_mode = str(params.get("resample_mode", params.get("mode", "count")) or "count").strip().lower()
    if resample_mode == "spacing":
        step = float(params.get("step", params.get("spacing", 0.0)) or 0.0)
        if step <= 0:
            step = _recommended_alignment_spacing(lines)
        if step <= 0:
            raise ValueError("无法推断有效的自动对齐重采样间距")
        grid = [x_start]
        next_x = x_start + step
        while next_x < x_end - 1e-12:
            grid.append(next_x)
            next_x += step
        if not math.isclose(grid[-1], x_end, rel_tol=0.0, abs_tol=1e-12):
            grid.append(x_end)
        return grid

    n_points = int(params.get("n", 0) or 0)
    if n_points < 2:
        n_points = max(len(line.get("x", []) or []) for line in lines)
    n_points = max(2, n_points)
    return [x_start + index * (x_end - x_start) / (n_points - 1) for index in range(n_points)]


def _recommended_alignment_spacing(lines: List[PipelineLine]) -> float:
    spacings = [
        spacing
        for line in lines
        for spacing in [_estimate_sample_spacing(list(line.get("x", []) or []))]
        if spacing is not None and spacing > 0
    ]
    return min(spacings) if spacings else 0.0


def _describe_alignment_mode(params: Dict[str, Any], point_count: int) -> str:
    resample_mode = str(params.get("resample_mode", params.get("mode", "count")) or "count").strip().lower()
    if resample_mode == "spacing":
        step = float(params.get("step", params.get("spacing", 0.0)) or 0.0)
        return f"固定间距({step:g})"
    return f"固定点数({point_count}点)"


def _interp_linear(x_value: float, xs: List[float], ys: List[float]) -> float:
    if not xs:
        return 0.0
    if x_value <= xs[0]:
        return ys[0]
    if x_value >= xs[-1]:
        return ys[-1]
    lo, hi = 0, len(xs) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if xs[mid] <= x_value:
            lo = mid
        else:
            hi = mid
    span = xs[hi] - xs[lo]
    if not span:
        return ys[lo]
    ratio = (x_value - xs[lo]) / span
    return ys[lo] + ratio * (ys[hi] - ys[lo])


def _op_pairwise_compute(lines: List[PipelineLine], p: Dict[str, Any]) -> PipelineResult:
    if len(lines) != 2:
        raise ValueError("双曲线计算需要恰好选择两条输入曲线")

    aligned_lines, _warnings = align_lines_to_common_x(lines, {"align_mode": "strict"})
    primary, secondary = aligned_lines
    x1 = list(primary.get("x", []) or [])
    y1 = list(primary.get("y", []) or [])
    x2 = list(secondary.get("x", []) or [])
    y2 = list(secondary.get("y", []) or [])

    x_expr, y_expr = _resolve_pairwise_expressions(p)
    new_x, new_y = _evaluate_pairwise_expression(x_expr, y_expr, x1, y1, x2, y2)

    default_name = f"{primary.get('name', '主曲线')} ⊕ {secondary.get('name', '副曲线')}"
    result_name = str(p.get("result_name", "") or "").strip() or default_name
    result_line = _merge_line_payload(primary, {
        "name": result_name,
        "x": list(new_x),
        "y": list(new_y),
    })
    return [result_line], []


def _resolve_pairwise_expressions(p: Dict[str, Any]) -> Tuple[str, str]:
    x_expr = str(p.get("x_expr", "") or "").strip()
    y_expr = str(p.get("y_expr", "") or "").strip()
    if x_expr and y_expr:
        return x_expr, y_expr
    operator = str(p.get("operator", "") or "").strip().lower()
    fallback_y = {
        "add": "y1 + y2",
        "subtract": "y1 - y2",
        "multiply": "y1 * y2",
        "divide": "y1 / y2 if y2 != 0 else 0.0",
        "abs_diff": "abs(y1 - y2)",
    }.get(operator)
    if y_expr == "":
        y_expr = fallback_y or "y1 - y2"
    if x_expr == "":
        x_expr = "x1"
    return x_expr, y_expr


def _evaluate_pairwise_expression(
    x_expr: str,
    y_expr: str,
    x1: List[float],
    y1: List[float],
    x2: List[float],
    y2: List[float],
) -> Tuple[List[float], List[float]]:
    import math as _math

    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore

    safe_globals = {
        "__builtins__": {},
        "math": _math,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "sqrt": _math.sqrt,
        "log": _math.log,
        "log10": _math.log10,
        "exp": _math.exp,
        "sin": _math.sin,
        "cos": _math.cos,
        "tan": _math.tan,
        "pi": _math.pi,
        "e": _math.e,
    }
    if np is not None:
        safe_globals["np"] = np
        for name in ("sqrt", "log", "log10", "exp", "sin", "cos", "tan", "abs", "minimum", "maximum"):
            if hasattr(np, name):
                safe_globals[name] = getattr(np, name)
        try:
            a1 = np.asarray(x1, dtype=float)
            b1 = np.asarray(y1, dtype=float)
            a2 = np.asarray(x2, dtype=float)
            b2 = np.asarray(y2, dtype=float)
            ctx = {"x1": a1, "y1": b1, "x2": a2, "y2": b2}
            nx = eval(x_expr, safe_globals, ctx)  # noqa: S307
            ny = eval(y_expr, safe_globals, ctx)  # noqa: S307
            return np.asarray(nx, dtype=float).tolist(), np.asarray(ny, dtype=float).tolist()
        except Exception:
            pass

    nx_list: List[float] = []
    ny_list: List[float] = []
    for left_x, left_y, right_x, right_y in zip(x1, y1, x2, y2):
        ctx = {"x1": float(left_x), "y1": float(left_y), "x2": float(right_x), "y2": float(right_y)}
        nx_list.append(float(eval(x_expr, safe_globals, ctx)))  # noqa: S307
        ny_list.append(float(eval(y_expr, safe_globals, ctx)))  # noqa: S307
    return nx_list, ny_list


def _x_values_equal(a: List[float], b: List[float]) -> bool:
    if len(a) != len(b):
        return False
    for left, right in zip(a, b):
        if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12):
            return False
    return True


def _pairwise_result_name(primary: PipelineLine, secondary: PipelineLine, operator: str) -> str:
    left_name = str(primary.get("name", "主曲线") or "主曲线")
    right_name = str(secondary.get("name", "副曲线") or "副曲线")
    symbols = {
        "add": "+",
        "subtract": "-",
        "multiply": "*",
        "divide": "/",
        "abs_diff": "|Δ|",
    }
    symbol = symbols.get(operator, operator)
    return f"{left_name} {symbol} {right_name}"


def _op_crop(xs: List[float], ys: List[float], p: dict) -> XY:
    x_min = p.get("x_min", -math.inf)
    x_max = p.get("x_max", math.inf)
    try:
        import numpy as np

        ax = np.asarray(xs, dtype=float)
        ay = np.asarray(ys, dtype=float)
        mask = (ax >= x_min) & (ax <= x_max)
        return ax[mask].tolist(), ay[mask].tolist()
    except ImportError:
        pairs = [(x, y) for x, y in zip(xs, ys) if x_min <= x <= x_max]
        if not pairs:
            return [], []
        nx, ny = zip(*pairs)
        return list(nx), list(ny)


def _op_smooth(xs: List[float], ys: List[float], p: dict) -> XY:
    method = p.get("method", "savgol")
    if method == "savgol":
        window = int(p.get("window", 11))
        poly = int(p.get("poly", 3))
        from processing.smoother import smooth_savgol

        return smooth_savgol(xs, ys, window, poly)
    if method == "moving_avg":
        window = int(p.get("window", 5))
        from processing.smoother import smooth_moving_average

        return smooth_moving_average(xs, ys, window)
    return list(xs), list(ys)


def _op_normalize(xs: List[float], ys: List[float], p: dict) -> XY:
    mode = p.get("mode", "minmax")
    if not ys:
        return xs, ys
    try:
        import numpy as np

        ay = np.asarray(ys, dtype=float)
        if mode == "minmax":
            mn, mx = ay.min(), ay.max()
            ny = ((ay - mn) / (mx - mn or 1.0)).tolist()
        elif mode == "zscore":
            std = ay.std() or 1.0
            ny = ((ay - ay.mean()) / std).tolist()
        else:
            ny = list(ys)
    except ImportError:
        n = len(ys)
        if mode == "minmax":
            mn, mx = min(ys), max(ys)
            rng = mx - mn or 1.0
            ny = [(value - mn) / rng for value in ys]
        elif mode == "zscore":
            mean = sum(ys) / n
            std = math.sqrt(sum((value - mean) ** 2 for value in ys) / n) or 1.0
            ny = [(value - mean) / std for value in ys]
        else:
            ny = list(ys)
    return list(xs), ny


def _op_resample(xs: List[float], ys: List[float], p: dict) -> XY:
    from processing.smoother import resample_uniform, resample_uniform_spacing

    x_sorted, y_sorted = _sorted_unique_xy(xs, ys)
    if len(x_sorted) < 2:
        return list(xs), list(ys)

    mode = str(p.get("mode", "spacing") or "spacing").strip().lower()

    if mode == "align":
        pool = list(_pipeline_pool.get() or [])
        if not pool:
            return x_sorted, y_sorted
        target_idx = p.get("target_line", p.get("target_index", 1))
        try:
            target = _pick_from_pool(pool, target_idx)
        except (ValueError, IndexError):
            return x_sorted, y_sorted
        target_x = list(target.get("x", []) or [])
        if not target_x or _x_values_equal(x_sorted, target_x):
            return x_sorted, y_sorted
        algorithm = str(p.get("algorithm", "linear") or "linear").strip().lower()
        new_y = _resample_to_grid(x_sorted, y_sorted, target_x, algorithm)
        return list(target_x), new_y

    if mode == "spacing":
        spacing_mode = str(p.get("spacing_mode", "") or "").strip().lower()
        if not spacing_mode:
            spacing_mode = "coord" if ("step" in p or "spacing" in p) else "point"
        if spacing_mode == "coord":
            spacing = float(p.get("step", p.get("spacing", 0.0)) or 0.0)
            if spacing <= 0:
                raise ValueError("坐标间距必须大于 0")
            return resample_uniform_spacing(x_sorted, y_sorted, spacing)
        n = max(2, int(p.get("n", 200)))
        return resample_uniform(x_sorted, y_sorted, n)

    if mode == "count":
        n = max(2, int(p.get("n", 200)))
        return resample_uniform(x_sorted, y_sorted, n)

    n = max(2, int(p.get("n", 200)))
    return resample_uniform(x_sorted, y_sorted, n)


def _apply_resample_to_lines(lines: List[PipelineLine], params: Dict[str, Any]) -> PipelineResult:
    working_lines = [_sorted_line_payload(line) for line in _normalize_pipeline_lines(lines)]
    if not working_lines:
        return [], []
    if len(working_lines) == 1:
        xs, ys = _op_resample(list(working_lines[0].get("x", []) or []), list(working_lines[0].get("y", []) or []), params)
        return [_merge_line_payload(working_lines[0], {"x": xs, "y": ys})], []

    mode = str(params.get("mode", "spacing") or "spacing").strip().lower()
    if mode == "align":
        rebuilt: List[PipelineLine] = []
        for line in working_lines:
            xs, ys = _op_resample(list(line.get("x", []) or []), list(line.get("y", []) or []), params)
            rebuilt.append(_merge_line_payload(line, {"x": xs, "y": ys}))
        return rebuilt, []

    spacing_mode = str(params.get("spacing_mode", "") or "").strip().lower()
    if not spacing_mode:
        spacing_mode = "coord" if ("step" in params or "spacing" in params) else "point"
    grid_params = dict(params)
    if spacing_mode == "coord":
        step = float(params.get("step", params.get("spacing", 0.0)) or 0.0)
        if step <= 0:
            raise ValueError("坐标间距必须大于 0")
        grid_params["mode"] = "spacing"
        grid_params["resample_mode"] = "spacing"
        grid_params["step"] = step
    else:
        grid_params["mode"] = "count"
        grid_params["resample_mode"] = "count"
        grid_params["n"] = max(2, int(params.get("n", 200) or 200))

    grid = _build_alignment_grid(working_lines, grid_params)
    algorithm = str(params.get("algorithm", "linear") or "linear").strip().lower()
    rebuilt = [
        _merge_line_payload(line, {
            "x": list(grid),
            "y": _resample_to_grid(list(line.get("x", []) or []), list(line.get("y", []) or []), grid, algorithm),
        })
        for line in working_lines
    ]
    return rebuilt, []


def _resample_to_grid(
    xs: List[float],
    ys: List[float],
    target_x: List[float],
    algorithm: str,
) -> List[float]:
    algorithm = str(algorithm or "linear").strip().lower()
    if algorithm == "nearest":
        return [_nearest_value(float(value), xs, ys) for value in target_x]
    if algorithm == "cubic":
        try:
            import numpy as np
            from scipy.interpolate import CubicSpline

            spline = CubicSpline(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float), extrapolate=False)
            values = spline(np.asarray(target_x, dtype=float))
            result: List[float] = []
            for raw, fallback_x in zip(values.tolist(), target_x):
                if raw is None or (isinstance(raw, float) and math.isnan(raw)):
                    result.append(_interp_linear(float(fallback_x), xs, ys))
                else:
                    result.append(float(raw))
            return result
        except Exception:
            pass
    return [_interp_linear(float(value), xs, ys) for value in target_x]


def _nearest_value(x_value: float, xs: List[float], ys: List[float]) -> float:
    if not xs:
        return 0.0
    best_index = 0
    best_distance = abs(xs[0] - x_value)
    for index in range(1, len(xs)):
        distance = abs(xs[index] - x_value)
        if distance < best_distance:
            best_distance = distance
            best_index = index
    return float(ys[best_index])


def _op_fft(xs: List[float], ys: List[float], p: dict) -> XY:
    n = len(ys)
    if n < 2:
        return list(xs), list(ys)

    output = p.get("output", "amplitude")
    detrend = bool(p.get("detrend", True))
    sample_rate = _resolve_sample_rate(xs, p)
    try:
        import numpy as np

        y_arr = np.asarray(ys, dtype=float)
        if detrend:
            y_arr = y_arr - y_arr.mean()

        step = 1.0 / sample_rate if sample_rate and sample_rate > 0 else 1.0

        freq = np.fft.rfftfreq(n, d=step)
        spec = np.fft.rfft(y_arr)
        if output == "power":
            values = (np.abs(spec) ** 2 / max(1, n)).tolist()
        else:
            values = (np.abs(spec) / max(1, n)).tolist()
        return freq.tolist(), values
    except ImportError:
        step = 1.0 / sample_rate if sample_rate and sample_rate > 0 else 1.0
        sig = list(ys)
        if detrend:
            mean = sum(sig) / len(sig)
            sig = [value - mean for value in sig]
        half = n // 2
        freq = []
        values = []
        for k in range(half + 1):
            total = 0j
            for index, sample in enumerate(sig):
                total += sample * cmath.exp(-2j * math.pi * k * index / n)
            amp = abs(total) / max(1, n)
            freq.append(k / (n * step))
            values.append(amp * amp if output == "power" else amp)
        return freq, values


def _op_derivative(xs: List[float], ys: List[float], p: dict) -> XY:
    n = len(xs)
    if n < 2:
        return xs, ys
    try:
        import numpy as np

        dy = np.gradient(np.array(ys), np.array(xs)).tolist()
    except ImportError:
        dy = [0.0] * n
        for index in range(1, n - 1):
            dx = xs[index + 1] - xs[index - 1]
            dy[index] = (ys[index + 1] - ys[index - 1]) / dx if dx else 0.0
        dy[0] = (ys[1] - ys[0]) / (xs[1] - xs[0]) if xs[1] != xs[0] else 0.0
        dy[-1] = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2]) if xs[-1] != xs[-2] else 0.0
    return list(xs), dy


def _op_integral(xs: List[float], ys: List[float], p: dict) -> XY:
    cumulative = p.get("cumulative", True)
    n = len(xs)
    if n < 2:
        return xs, ys
    try:
        import numpy as np
        from scipy.integrate import cumulative_trapezoid

        cum = cumulative_trapezoid(np.array(ys), np.array(xs), initial=0.0).tolist()
        if not cumulative:
            return list(xs), [cum[-1]] * n
        return list(xs), cum
    except ImportError:
        acc = 0.0
        result = [0.0]
        for index in range(1, n):
            acc += (ys[index] + ys[index - 1]) * (xs[index] - xs[index - 1]) / 2
            result.append(acc)
        if not cumulative:
            return list(xs), [result[-1]] * n
        return list(xs), result


def _op_transform(xs: List[float], ys: List[float], p: dict) -> XY:
    x_expr = p.get("x_expr", "").strip()
    y_expr = p.get("y_expr", "").strip()
    try:
        import math as _math

        try:
            import numpy as np
        except ImportError:
            np = None
        safe_globals = {
            "__builtins__": {}, "math": _math, "abs": abs,
            "min": min, "max": max, "round": round, "sqrt": _math.sqrt,
            "log": _math.log, "log10": _math.log10, "exp": _math.exp,
            "sin": _math.sin, "cos": _math.cos, "tan": _math.tan,
            "pi": _math.pi, "e": _math.e,
        }
        if np is not None:
            safe_globals["np"] = np
            try:
                x_arr = np.asarray(xs, dtype=float)
                y_arr = np.asarray(ys, dtype=float)
                ctx = {"x": x_arr, "y": y_arr}
                for fn in ("sqrt", "log", "log10", "exp", "sin", "cos", "tan", "abs"):
                    safe_globals[fn] = getattr(np, fn)
                nx = eval(x_expr, safe_globals, ctx) if x_expr else x_arr  # noqa: S307
                ny = eval(y_expr, safe_globals, ctx) if y_expr else y_arr  # noqa: S307
                return np.asarray(nx, dtype=float).tolist(), np.asarray(ny, dtype=float).tolist()
            except Exception:
                pass
        new_xs, new_ys = [], []
        for x, y in zip(xs, ys):
            ctx = {"x": x, "y": y}
            nx = eval(x_expr, safe_globals, ctx) if x_expr else x  # noqa: S307
            ny = eval(y_expr, safe_globals, ctx) if y_expr else y  # noqa: S307
            new_xs.append(float(nx))
            new_ys.append(float(ny))
        return new_xs, new_ys
    except Exception:
        return list(xs), list(ys)


def _op_filter(xs: List[float], ys: List[float], p: dict) -> XY:
    cutoff = float(p.get("cutoff", 0.1))
    order = int(p.get("order", 4))
    mode = p.get("mode", "low")
    cutoff_mode = str(p.get("cutoff_mode", "normalized") or "normalized").strip().lower()
    sample_rate = _resolve_sample_rate(xs, p)
    if cutoff_mode == "actual":
        if sample_rate is None or sample_rate <= 0:
            return list(xs), list(ys)
        nyquist = sample_rate / 2.0
        if nyquist <= 0:
            return list(xs), list(ys)
        cutoff = cutoff / nyquist
    cutoff = max(0.001, min(0.999, cutoff))
    try:
        import numpy as np
        from scipy.signal import butter, filtfilt

        btype = "high" if mode == "high" else "low"
        coeffs = butter(order, cutoff, btype=btype, analog=False)
        if coeffs is None or len(coeffs) < 2:
            return list(xs), list(ys)
        b, a = coeffs[0], coeffs[1]
        y_filt = filtfilt(b, a, np.array(ys)).tolist()
        return list(xs), y_filt
    except ImportError:
        return list(xs), list(ys)


def _sorted_unique_xy(xs: List[float], ys: List[float]) -> XY:
    pairs = []
    for x_value, y_value in zip(xs, ys):
        try:
            x_float = float(x_value)
            y_float = float(y_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(x_float) or not math.isfinite(y_float):
            continue
        pairs.append((x_float, y_float))
    if len(pairs) < 2:
        return list(xs), list(ys)

    pairs.sort(key=lambda item: item[0])
    unique_x: List[float] = []
    unique_y: List[float] = []
    for x_value, y_value in pairs:
        if unique_x and math.isclose(x_value, unique_x[-1], rel_tol=0.0, abs_tol=1e-12):
            unique_y[-1] = y_value
            continue
        unique_x.append(x_value)
        unique_y.append(y_value)
    return unique_x, unique_y


def _estimate_sample_spacing(xs: List[float]) -> Optional[float]:
    x_sorted, _ = _sorted_unique_xy(xs, xs)
    if len(x_sorted) < 2:
        return None
    diffs = [x_sorted[index + 1] - x_sorted[index] for index in range(len(x_sorted) - 1)]
    diffs = [abs(diff) for diff in diffs if diff and math.isfinite(diff)]
    if not diffs:
        return None
    diffs.sort()
    return diffs[len(diffs) // 2]


def _resolve_sample_rate(xs: List[float], p: dict) -> Optional[float]:
    raw_sample_rate = p.get("sampling_rate")
    try:
        sample_rate = float(raw_sample_rate)
    except (TypeError, ValueError):
        sample_rate = 0.0
    if sample_rate > 0:
        return sample_rate
    step = _estimate_sample_spacing(xs)
    if step is None or step <= 0:
        return None
    return 1.0 / step
