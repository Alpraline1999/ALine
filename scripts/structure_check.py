#!/usr/bin/env python3
"""
轻量级结构检查脚本 — 用于重构阶段验收与功能优化前的门禁。

检查项：
  1. 首次方文件体量预算（超过阈值警告）
  2. project_manager._* 私有 API 泄漏
  3. 重复 command surface 检测
  4. 超大测试文件警告
"""
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def check_file_size():
    """检查首次方文件体量。"""
    print("=" * 60)
    print("[1/4] 首次方文件体量检查")
    print("=" * 60)
    over_limit = []
    dirs = [
        REPO_ROOT / "core",
        REPO_ROOT / "ui",
        REPO_ROOT / "ai",
        REPO_ROOT / "app",
    ]
    for d in dirs:
        if not d.exists():
            continue
        for py_file in sorted(d.rglob("*.py")):
            if "/." in str(py_file) or "/__pycache__/" in str(py_file):
                continue
            lines = len(py_file.read_text().splitlines())
            if lines > 2000:
                over_limit.append((str(py_file.relative_to(REPO_ROOT)), lines))
    if over_limit:
        print(f"  !!  {len(over_limit)} 个文件超过 2000 行预算:")
        for path, lines in sorted(over_limit, key=lambda x: -x[1]):
            print(f"    - {path} ({lines} 行)")
    else:
        print("  OK 所有文件均在预算内")
    print()


def check_private_api_leak():
    """检查 project_manager._* 跨模块访问。"""
    print("=" * 60)
    print("[2/4] 私有 API 泄漏检查 (project_manager._*)")
    print("=" * 60)
    leaks = []
    for root, _dirs, files in os.walk(REPO_ROOT / "ui"):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(root) / f
            for i, line in enumerate(path.read_text().splitlines(), 1):
                if "project_manager._" in line and not line.strip().startswith("#"):
                    leaks.append((str(path.relative_to(REPO_ROOT)), i, line.strip()))
    for root, _dirs, files in os.walk(REPO_ROOT / "app"):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = Path(root) / f
            for i, line in enumerate(path.read_text().splitlines(), 1):
                if "project_manager._" in line and not line.strip().startswith("#"):
                    leaks.append((str(path.relative_to(REPO_ROOT)), i, line.strip()))
    if leaks:
        print(f"  !!  发现 {len(leaks)} 处私有 API 泄漏:")
        for path, line_no, code in leaks:
            print(f"    - {path}:{line_no}  {code}")
    else:
        print("  OK 未发现 project_manager._* 跨模块访问")
    print()


def check_command_duplication():
    """检查 command_layer 与 command_registry 的重复（def cmd_* + COMMANDS schema + class）。"""
    print("=" * 60)
    print("[3/4] 重复 Command Surface 检查")
    print("=" * 60)
    layer_path = REPO_ROOT / "ai" / "command_layer.py"
    reg_path = REPO_ROOT / "ai" / "command_registry.py"
    if not layer_path.exists() or not reg_path.exists():
        print("  - ai/command_layer.py 或 ai/command_registry.py 不存在，跳过")
        print()
        return

    layer_text = layer_path.read_text()
    reg_text = reg_path.read_text()

    # 检查 1: def cmd_* 函数定义
    layer_defs = {line for line in layer_text.splitlines() if line.startswith("def cmd_")}
    reg_defs = {line for line in reg_text.splitlines() if line.startswith("def cmd_")}

    # 检查 2: class CommandResult / CommandDef（非 Dispatcher）
    layer_classes = {line.strip() for line in layer_text.splitlines()
                     if line.strip().startswith("class ") and line.strip() in ("class CommandResult:", "class CommandDef:")}
    reg_classes = {line.strip() for line in reg_text.splitlines()
                   if line.strip().startswith("class ") and line.strip() in ("class CommandResult:", "class CommandDef:")}

    # 检查 3: COMMANDS 字典键
    layer_keys = _extract_commands_keys(layer_text)
    reg_keys = _extract_commands_keys(reg_text)

    errors = []

    # 报告 def cmd_*
    in_layer_only = layer_defs - reg_defs
    if in_layer_only:
        errors.append(f"command_layer.py 有 {len(in_layer_only)} 个独有 cmd_* 定义")

    # 报告 class 定义
    layer_only_classes = layer_classes - reg_classes
    if layer_only_classes:
        errors.append(f"command_layer.py 有独立 class 定义: {', '.join(sorted(layer_only_classes))}")

    # 报告 COMMANDS schema
    if layer_keys and reg_keys:
        only_in_layer = layer_keys - reg_keys
        only_in_reg = reg_keys - layer_keys
        if only_in_layer:
            errors.append(f"command_layer.py 的 COMMANDS 有 {len(only_in_layer)} 个独有键: {', '.join(sorted(only_in_layer)[:5])}")
        if only_in_reg:
            errors.append(f"command_registry.py 的 COMMANDS 有 {len(only_in_reg)} 个独有键: {', '.join(sorted(only_in_reg)[:5])}")

    if errors:
        print(f"  !!  发现 {len(errors)} 项重复问题:")
        for err in errors:
            print(f"    - {err}")
    elif not layer_defs and not layer_classes and not layer_keys:
        print("  OK command_layer.py 已无独立命令定义（全部从 registry 导入）")
    else:
        print("  OK command_layer.py 与 command_registry.py 定义一致")


def _extract_commands_keys(text: str) -> set[str]:
    """从 COMMANDS 字典文本中提取键名。"""
    import re
    keys: set[str] = set()
    in_commands = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "COMMANDS: Dict[str, CommandDef] = {" or stripped == "COMMANDS = {" or stripped == "COMMANDS: Dict[str, \"CommandDef\"] = {":
            in_commands = True
            continue
        if in_commands:
            if stripped == "}":
                break
            m = re.match(r'\s*"([^"]+)":\s*CommandDef\(', stripped)
            if m:
                keys.add(m.group(1))
    return keys


def check_test_file_size():
    """检查超大测试文件（包括子目录）。"""
    print("=" * 60)
    print("[4/4] 超大测试文件检查")
    print("=" * 60)
    tests_dir = REPO_ROOT / "tests"
    if not tests_dir.exists():
        print("  - tests/ 目录不存在，跳过")
        print()
        return
    checked = 0
    for py_file in sorted(tests_dir.rglob("test_*.py")):
        lines = len(py_file.read_text().splitlines())
        checked += 1
        if lines > 3000:
            print(f"  !!  {py_file.relative_to(REPO_ROOT)} ({lines} 行) 超过 3000 行预算")
    print(f"  - 共检查 {checked} 个测试文件")
    print()


if __name__ == "__main__":
    check_file_size()
    check_private_api_leak()
    check_command_duplication()
    check_test_file_size()
    print("=" * 60)
    print("结构检查完成")
    print("=" * 60)
