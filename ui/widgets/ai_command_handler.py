from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

_EXTENSIONS_README_PATH = Path(__file__).resolve().parent.parent.parent / "extensions" / "README.md"

# ── 命令注册表 ─────────────────────────────────────────────

_COMMANDS: Dict[str, dict] = {}


def register_command(
    name: str,
    description: str,
    label: str,
    category: str = "default",
    aliases: Optional[List[str]] = None,
) -> Callable:
    """装饰器：注册 AI 面板命令。"""
    def decorator(func: Callable) -> Callable:
        _COMMANDS[name] = {
            "name": name,
            "description": description,
            "label": label,
            "category": category,
            "aliases": aliases or [],
            "handler": func,
        }
        return func
    return decorator


def get_command_list() -> List[str]:
    """返回所有命令的 / 前缀列表（用于 QCompleter）。"""
    result = []
    for cmd_name, cmd_info in _COMMANDS.items():
        result.append(f"/{cmd_name}  — {cmd_info['description']}")
        for alias in cmd_info.get("aliases", []):
            result.append(f"/{alias}")
    return result


def get_command_suggestions(prefix: str) -> List[str]:
    """返回匹配前缀的命令提示列表（用于 SearchLineEdit 自动补全）。"""
    if not prefix.startswith("/"):
        return []
    partial = prefix[1:].lower()
    suggestions = []
    for cmd_name, cmd_info in _COMMANDS.items():
        if cmd_name.startswith(partial):
            suggestions.append(f"/{cmd_name}  — {cmd_info['description']}")
            continue
        for alias in cmd_info.get("aliases", []):
            if alias.startswith(partial):
                suggestions.append(f"/{cmd_name}  — {cmd_info['description']}")
                break
    return suggestions


def detect_command(text: str) -> Optional[Tuple[str, str, str]]:
    """检测文本是否包含命令。返回 (command_name, action_label, args) 或 None。"""
    match = re.match(r"^/(\w+)\s*(.*)", text.strip())
    if not match:
        return None
    cmd_name = match.group(1).lower()
    args = match.group(2).strip()
    cmd_info = _COMMANDS.get(cmd_name)
    if cmd_info is None:
        # 检查别名
        for cname, cinfo in _COMMANDS.items():
            if cmd_name in cinfo.get("aliases", []):
                return cname, cinfo["label"], args
        return None
    return cmd_name, cmd_info["label"], args


def execute_command(cmd_name: str, args: str) -> Tuple[str, List[dict]]:
    """执行命令，返回 (system_prompt_addition, extra_messages)。"""
    cmd_info = _COMMANDS.get(cmd_name)
    if cmd_info is None:
        return "", []
    return cmd_info["handler"](args)


# ── 内置命令 ───────────────────────────────────────────────


@register_command(
    name="extension",
    description="AI 辅助生成 ALine 扩展代码（自动参考扩展开发指南）",
    label="扩展生成",
    category="dev",
    aliases=["ext", "plugin"],
)
def _handle_extension(args: str) -> Tuple[str, List[dict]]:
    """加载 extensions/README.md 作为系统提示上下文。"""
    readme_text = ""
    if _EXTENSIONS_README_PATH.exists():
        readme_text = _EXTENSIONS_README_PATH.read_text(encoding="utf-8")
    else:
        readme_text = "（未找到 extensions/README.md）"

    prompt = (
        "## ALine 扩展开发规范\n\n"
        f"{readme_text}\n\n"
        "---\n"
        "请严格按照上述规范生成扩展代码。\n"
        "要求：\n"
        "1. handler 签名必须匹配对应扩展类型的 Protocol\n"
        "2. 曲线数据使用 point-list 格式\n"
        "3. 提供完整的 register_extensions(registry) 函数\n"
        "4. type 名称用 snake_case，全局唯一\n"
        "5. 代码用 ```python 代码块包裹\n\n"
        f"用户需求：{args}"
    )
    return prompt, []


@register_command(
    name="help",
    description="显示所有可用命令",
    label="帮助",
    category="system",
    aliases=["h", "commands"],
)
def _handle_help(args: str) -> Tuple[str, List[dict]]:
    lines = ["## AI 助手命令\n", "输入以下命令获取专项帮助：\n"]
    categories: Dict[str, List[str]] = {}
    for cmd_name, cmd_info in _COMMANDS.items():
        cat = cmd_info.get("category", "default")
        if cat not in categories:
            categories[cat] = []
        aliases_str = ""
        if cmd_info.get("aliases"):
            aliases_str = f" (别名: {'/'.join(cmd_info['aliases'])})"
        categories[cat].append(f"- `/{cmd_name}`{aliases_str}：{cmd_info['description']}")

    for cat, items in categories.items():
        lines.append(f"\n**{cat}**\n")
        lines.extend(items)

    return "\n".join(lines), []
