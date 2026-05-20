from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional, Tuple

from core.extension_api import extension_registry
from core.extension_settings import (
    get_external_extensions_directories,
    get_builtin_extension_settings,
    set_builtin_extension_settings,
)


_EXTENSION_DIR_MAP = {
    "processing": "processing",
    "analysis": "analysis",
    "plot": "plot",
    "digitize": "digitize",
}


def parse_extension_code(code: str) -> Tuple[Optional[str], Optional[str], str]:
    """解析 AI 生成的扩展代码，提取 type、分类和合法性。

    Returns:
        (ext_type, category, error_msg)
        ext_type 和 category 为 None 时表示解析失败，error_msg 说明原因。
    """
    # 提取代码块（处理 AI 回复包裹在 ```python ... ``` 中的情况）
    code_block = code
    match = re.search(r"```(?:python)?\s*\n(.*?)\n```", code, re.DOTALL)
    if match:
        code_block = match.group(1).strip()

    # 检查语法
    try:
        tree = ast.parse(code_block)
    except SyntaxError as e:
        return None, None, f"语法错误: {e}"

    # 查找 register_extensions 函数调用，提取 type
    ext_type = None
    category = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            if func_name in ("register_processing", "register_analysis", "register_plot", "register_digitize"):
                category_map = {
                    "register_processing": "processing",
                    "register_analysis": "analysis",
                    "register_plot": "plot",
                    "register_digitize": "digitize",
                }
                category = category_map[func_name]
                if node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Call):
                        for kw in first_arg.keywords:
                            if kw.arg == "type" and isinstance(kw.value, ast.Constant):
                                ext_type = kw.value.value

    if not ext_type:
        return None, None, "无法解析扩展 type，请确保 register_extensions 中声明了 type 字段"
    if not category:
        return None, None, "无法识别扩展分类"

    # 检查 type 是否已存在
    existing = _check_existing_type(ext_type)
    if existing:
        return None, None, f"扩展 type '{ext_type}' 已存在（{existing}），请使用不同的 type 名称"

    return ext_type, category, ""


def _check_existing_type(ext_type: str) -> Optional[str]:
    """检查 type 是否已被注册。"""
    if extension_registry.get_processing(ext_type):
        return "处理扩展"
    if extension_registry.get_analysis(ext_type):
        return "分析扩展"
    if extension_registry.get_plot(ext_type):
        return "绘图扩展"
    if extension_registry.get_digitize(ext_type):
        return "数字化扩展"
    return None


def save_extension(code: str, category: str, ext_type: str) -> Tuple[bool, str]:
    """将扩展代码保存到外部扩展目录。

    Returns:
        (success, message)
    """
    # 提取纯净代码（去除 markdown 包裹）
    clean_code = code
    match = re.search(r"```(?:python)?\s*\n(.*?)\n```", code, re.DOTALL)
    if match:
        clean_code = match.group(1).strip()

    # 确定目标目录
    sub_dir = _EXTENSION_DIR_MAP.get(category)
    if not sub_dir:
        return False, f"未知的扩展分类: {category}"

    dirs = get_external_extensions_directories()
    if not dirs:
        return False, "未配置外部扩展目录，请先在设置页中添加外部扩展目录"

    target_dir = dirs[0] / sub_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    # 写入文件
    filename = f"{ext_type}.py"
    filepath = target_dir / filename

    if filepath.exists():
        return False, f"文件已存在: {filepath}，请先删除或重命名再保存"

    try:
        filepath.write_text(clean_code, encoding="utf-8")
    except OSError as e:
        return False, f"写入文件失败: {e}"

    return True, str(filepath)
