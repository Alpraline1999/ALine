#!/usr/bin/env python
"""
ALine 打包脚本
==============
自动检测平台，安装 PyInstaller，执行打包，并生成压缩发布包。

使用方式：
    python build.py                   # 标准打包
    python build.py --clean           # 清理后重新打包
    python build.py --no-compress     # 不压缩，直接输出目录
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from aline_metadata import APP_NAME, APP_VERSION


ROOT = Path(__file__).parent.resolve()
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
VENV_PY = ROOT / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "python"


def run(cmd: list[str], **kwargs) -> int:
    """运行子进程，实时输出日志。"""
    print(f"\n▶ {' '.join(str(c) for c in cmd)}\n{'─' * 60}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"\n✖ 命令失败（退出码 {result.returncode}）")
        sys.exit(result.returncode)
    return result.returncode


def get_python() -> str:
    """优先使用虚拟环境中的 Python。"""
    if VENV_PY.exists():
        return str(VENV_PY)
    return sys.executable


def ensure_pyinstaller(python: str) -> None:
    """确保 PyInstaller 已安装。"""
    try:
        subprocess.run(
            [python, "-c", "import PyInstaller"],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        print("ℹ PyInstaller 未安装，自动安装...")
        run([python, "-m", "pip", "install", "pyinstaller"])


def clean() -> None:
    """清理旧的构建产物。"""
    for d in (DIST_DIR, BUILD_DIR):
        if d.exists():
            print(f"  删除 {d}")
            shutil.rmtree(d)


def run_tests(python: str) -> None:
    """运行测试套件，全通过才继续打包。"""
    print("\n═══ 运行测试套件 ═══")
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    subprocess.run(
        [python, "-m", "unittest", "tests.test_backend", "-v"],
        check=True, cwd=ROOT, env=env,
    )


def build(python: str) -> None:
    """执行 PyInstaller 打包。"""
    print("\n═══ 开始打包 ═══")
    run([
        python, "-m", "PyInstaller",
        "--noconfirm",
        str(ROOT / "aline.spec"),
    ], cwd=ROOT)


def make_archive() -> Path:
    """将 dist/ALine 目录压缩为 zip，便于分发。"""
    app_dir = DIST_DIR / APP_NAME
    if not app_dir.exists():
        print(f"✖ 未找到输出目录: {app_dir}")
        sys.exit(1)

    plat = platform.system().lower()
    machine = platform.machine().lower()
    archive_name = f"{APP_NAME}-{APP_VERSION}-{plat}-{machine}.zip"
    archive_path = DIST_DIR / archive_name

    print(f"\n═══ 打包为 {archive_name} ═══")
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in sorted(app_dir.rglob("*")):
            if file.is_file():
                arcname = Path(APP_NAME) / file.relative_to(app_dir)
                zf.write(file, arcname)

    size_mb = archive_path.stat().st_size / 1024 / 1024
    print(f"  ✔ {archive_path}  ({size_mb:.1f} MB)")
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description="ALine 打包脚本")
    parser.add_argument("--clean",       action="store_true", help="打包前清理旧产物")
    parser.add_argument("--no-compress", action="store_true", help="不生成 zip 压缩包")
    parser.add_argument("--skip-tests",  action="store_true", help="跳过测试（不推荐）")
    args = parser.parse_args()

    python = get_python()
    print(f"Python: {python}")
    print(f"平台:   {platform.system()} {platform.machine()}")
    print(f"根目录: {ROOT}\n")

    ensure_pyinstaller(python)

    if args.clean:
        clean()

    if not args.skip_tests:
        try:
            run_tests(python)
        except subprocess.CalledProcessError:
            print("\n✖ 测试失败，终止打包")
            sys.exit(1)
    else:
        print("\n⚠ 已跳过测试")

    build(python)

    if not args.no_compress:
        archive = make_archive()
        print(f"\n✔ 打包完成 → {archive}")
    else:
        print(f"\n✔ 打包完成 → {DIST_DIR / APP_NAME}")


if __name__ == "__main__":
    main()
