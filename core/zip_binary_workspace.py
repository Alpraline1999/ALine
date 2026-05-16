"""二进制文件暂存区 — ZipBinaryWorkspace

在 .aline ZIP 内的 files/* 条目与会话临时目录之间建立桥梁：

- 会话期间所有二进制文件操作（导入/重命名/移动/删除）在临时目录中进行
- resolve() 按需从 ZIP 懒提取文件到临时目录
- save 时 pack_to_zip() 将修改过的文件写回 ZIP
- 关闭项目时 cleanup() 清理临时目录
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Set


class ZipBinaryWorkspace:
    """按需懒提取的二进制文件暂存区。

    每个打开的项目对应一个 workspace，包装一个临时目录。
    ZIP 中的 files/* 条目仅在实际被访问时才提取到临时目录。
    """

    def __init__(self, project_path: str) -> None:
        self._project_path = project_path
        self._temp_dir = Path(tempfile.mkdtemp(prefix="aline_ws_"))
        # 记录哪些路径是"新"的（ZIP 中不存在的，通过 store 创建的）
        self._new_paths: Set[str] = set()
        # 记录哪些路径已从暂存区移除（重命名/删除），保存时需从 ZIP 排除
        self._removed_paths: Set[str] = set()

    # ── 属性 ────────────────────────────────────────────────────

    @property
    def temp_dir(self) -> Path:
        return self._temp_dir

    @property
    def project_path(self) -> str:
        return self._project_path

    # ── 路径解析与懒提取 ────────────────────────────────────────

    def resolve(self, relative_path: str) -> str:
        """返回暂存区中的绝对路径。

        若文件不在暂存区但 ZIP 中有对应条目，则自动懒提取。
        """
        abs_path = self._temp_dir / relative_path
        if abs_path.exists():
            return str(abs_path)

        if self._exists_in_zip(relative_path):
            self._extract_one(relative_path)

        return str(abs_path)

    def ensure_dir(self, relative_dir: str) -> Path:
        """确保暂存区中存在某目录，返回 Path。"""
        target = self._temp_dir / relative_dir
        target.mkdir(parents=True, exist_ok=True)
        return target

    # ── 文件操作 ────────────────────────────────────────────────

    def store(self, source_path: str, target_rel: str) -> str:
        """复制外部文件到暂存区，返回暂存区绝对路径。"""
        target = self._temp_dir / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        self._new_paths.add(target_rel)
        return str(target)

    def remove(self, relative_path: str) -> None:
        """从暂存区删除文件。"""
        target = self._temp_dir / relative_path
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
        self._removed_paths.add(relative_path)
        self._new_paths.discard(relative_path)

    def move(self, old_rel: str, new_rel: str) -> None:
        """在暂存区内移动/重命名文件。"""
        self._removed_paths.add(old_rel)
        old_path = self._temp_dir / old_rel
        new_path = self._temp_dir / new_rel
        if not old_path.exists():
            return
        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))
        if old_rel in self._new_paths:
            self._new_paths.discard(old_rel)
            self._new_paths.add(new_rel)

    def exists_in_zip(self, relative_path: str) -> bool:
        """判断路径在 ZIP 中是否存在。"""
        return self._exists_in_zip(relative_path)

    # ── 修改追踪与打包 ──────────────────────────────────────────

    def modified_paths(self) -> Set[str]:
        """返回暂存区中相对于 ZIP 有变化的路径集合。"""
        result: Set[str] = set()
        base = self._temp_dir
        for path in base.rglob("*"):
            if path.is_file():
                rel = str(path.relative_to(base))
                rel = rel.replace("\\", "/")
                result.add(rel)
        return result

    def removed_paths(self) -> Set[str]:
        """返回已从暂存区移除的路径集合（保存时需从 ZIP 排除）。"""
        return set(self._removed_paths)

    def pack_to_zip(
        self, zf: zipfile.ZipFile, modified_paths: Set[str]
    ) -> None:
        """将 modified_paths 中的文件从暂存区写入 ZIP。"""
        base = self._temp_dir
        for rel_path in sorted(modified_paths):
            abs_path = base / rel_path
            if abs_path.is_file():
                zf.write(str(abs_path), rel_path)

    def cleanup(self) -> None:
        """删除临时目录。"""
        try:
            shutil.rmtree(str(self._temp_dir), ignore_errors=True)
        except OSError:
            pass
        self._new_paths.clear()
        self._removed_paths.clear()    # ── 内部辅助 ────────────────────────────────────────────────

    def _exists_in_zip(self, relative_path: str) -> bool:
        if not self._project_path or not Path(self._project_path).exists():
            return False
        try:
            with zipfile.ZipFile(self._project_path, "r") as zf:
                return relative_path in zf.namelist()
        except (zipfile.BadZipFile, FileNotFoundError):
            return False

    def _extract_one(self, relative_path: str) -> None:
        """从 ZIP 中提取单个 files/* 条目到暂存区。"""
        if not self._project_path or not Path(self._project_path).exists():
            return
        try:
            with zipfile.ZipFile(self._project_path, "r") as zf:
                if relative_path in zf.namelist():
                    zf.extract(relative_path, str(self._temp_dir))
        except (zipfile.BadZipFile, KeyError, FileNotFoundError):
            pass
