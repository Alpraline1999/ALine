"""应用上下文 — 核心服务的显式依赖容器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from core.analysis_manager import AnalysisManager
    from core.data_file_manager import DataFileManager
    from core.extension_registry import ExtensionRegistry
    from core.global_assets import GlobalAssetManager
    from core.project_manager import ProjectManager
    from core.shortcut_manager import ShortcutManager
    from core.tree_manager import TreeManager


@dataclass
class AppContext:
    """应用级依赖容器。

    所有核心服务通过此容器访问，而非模块级 import。
    测试时可通过 set_app_context() 替换为 mock 实例。
    """

    project_manager: Optional[ProjectManager] = None
    tree_manager: Optional[TreeManager] = None
    data_file_manager: Optional[DataFileManager] = None
    analysis_manager: Optional[AnalysisManager] = None
    extension_registry: Optional[ExtensionRegistry] = None
    global_assets: Optional[GlobalAssetManager] = None
    shortcut_manager: Optional[ShortcutManager] = None


# 全局 context 实例（模块级单例，但可通过 set_app_context 切换）
_context: AppContext = AppContext()


def get_app_context() -> AppContext:
    """获取当前应用上下文。"""
    return _context


def set_app_context(ctx: AppContext) -> None:
    """设置应用上下文（测试用）。"""
    global _context
    _context = ctx


def reset_app_context() -> None:
    """重置应用上下文为默认空容器。"""
    set_app_context(AppContext())
