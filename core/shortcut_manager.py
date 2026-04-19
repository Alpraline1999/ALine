"""快捷键管理器 - 管理全局键盘快捷键的定义、持久化与页面绑定。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut


@dataclass(frozen=True)
class ShortcutDefinition:
    action: str
    label: str
    default: str = ""
    category: str = "通用"
    tags: Tuple[str, ...] = field(default_factory=tuple)


_BUILTIN_SHORTCUTS: Tuple[ShortcutDefinition, ...] = (
    ShortcutDefinition("new_project", "新建项目", "Ctrl+N", "项目", ("文件",)),
    ShortcutDefinition("open_project", "打开项目", "Ctrl+O", "项目", ("文件",)),
    ShortcutDefinition("save", "保存项目", "Ctrl+S", "项目", ("文件",)),
    ShortcutDefinition("close_project", "关闭项目", "Ctrl+W", "项目", ("文件",)),
    ShortcutDefinition("data_add_dataset", "新建数据集", "Ctrl+Alt+D", "数据管理", ("共享树", "项目")),
    ShortcutDefinition("data_import_file", "导入文件", "Ctrl+Alt+I", "数据管理", ("共享树", "项目")),
    ShortcutDefinition("data_copy_curve_to_series", "复制为数据集", "Ctrl+Shift+C", "数据管理", ("曲线", "数据")),
    ShortcutDefinition("data_delete_selected", "删除选中数据", "Delete", "数据管理", ("编辑",)),
    ShortcutDefinition("data_apply_rename", "应用节点重命名", "F2", "数据管理", ("编辑", "节点")),
    ShortcutDefinition("data_duplicate_to_file", "复制为数据文件", "Ctrl+Shift+D", "数据管理", ("编辑", "节点")),
    ShortcutDefinition("data_delete_node", "删除当前节点", "Shift+Delete", "数据管理", ("编辑", "节点")),
    ShortcutDefinition("chart_save_template", "保存绘图模板", "Ctrl+Alt+T", "数据可视化", ("模板",)),
    ShortcutDefinition("chart_save_curve_style_template", "保存曲线样式模板", "Ctrl+Alt+Y", "数据可视化", ("模板", "曲线")),
    ShortcutDefinition("chart_export_picture", "导出到图片集", "Ctrl+E", "数据可视化", ("导出", "图片")),
    ShortcutDefinition("process_add_op", "添加处理操作", "Ctrl+Alt+A", "数据处理", ("管道",)),
    ShortcutDefinition("process_clear_ops", "清空处理链", "Ctrl+Shift+Delete", "数据处理", ("管道", "清理")),
    ShortcutDefinition("process_remove_op", "移除处理操作", "Delete", "数据处理", ("管道", "编辑")),
    ShortcutDefinition("process_move_op_up", "上移处理操作", "Ctrl+Up", "数据处理", ("管道", "排序")),
    ShortcutDefinition("process_move_op_down", "下移处理操作", "Ctrl+Down", "数据处理", ("管道", "排序")),
    ShortcutDefinition("process_run_pipeline", "运行处理链", "Ctrl+Shift+Return", "数据处理", ("执行",)),
    ShortcutDefinition("analysis_run", "运行分析", "Ctrl+Return", "数据分析", ("执行",)),
    ShortcutDefinition("analysis_save_result", "保存分析结果", "Ctrl+Shift+S", "数据分析", ("结果",)),
    ShortcutDefinition("analysis_export_result", "导出结果数据", "Ctrl+Shift+E", "数据分析", ("结果", "导出")),
    ShortcutDefinition("analysis_clear_inputs", "清空分析输入", "Ctrl+Alt+Delete", "数据分析", ("输入", "清理")),
    ShortcutDefinition("analysis_remove_selected_input", "移除选中输入", "Delete", "数据分析", ("输入", "编辑")),
    ShortcutDefinition("analysis_generate_report", "生成报告预览", "Ctrl+Alt+R", "数据分析", ("报告",)),
    ShortcutDefinition("analysis_save_report_template", "另存为报告模板", "Ctrl+Alt+S", "数据分析", ("报告", "模板")),
    ShortcutDefinition("analysis_export_report", "导出报告", "Ctrl+Alt+E", "数据分析", ("报告", "导出")),
    ShortcutDefinition("undo", "撤销", "Ctrl+Z", "图片数据化", ("编辑",)),
    ShortcutDefinition("redo", "重做", "Ctrl+Y", "图片数据化", ("编辑",)),
    ShortcutDefinition("add_image", "添加图片", "Ctrl+I", "图片数据化", ("导入",)),
    ShortcutDefinition("add_curve", "添加曲线", "Ctrl+Shift+N", "图片数据化", ("曲线",)),
    ShortcutDefinition("extract", "手动提取模式", "Q", "图片数据化", ("工具",)),
    ShortcutDefinition("calibrate", "校准模式", "C", "图片数据化", ("工具",)),
    ShortcutDefinition("eraser", "橡皮擦模式", "E", "图片数据化", ("工具",)),
    ShortcutDefinition("auto_detect", "自动检测", "A", "图片数据化", ("工具",)),
    ShortcutDefinition("apply_auto", "应用检测结果", "Ctrl+Return", "图片数据化", ("工具",)),
    ShortcutDefinition("clear_points", "清除所有点", "Ctrl+Delete", "图片数据化", ("清理",)),
    ShortcutDefinition("clear_masks", "清除蒙版", "Ctrl+Shift+Delete", "图片数据化", ("清理",)),
    ShortcutDefinition("escape_tool", "取消当前工具", "Escape", "图片数据化", ("工具",)),
    ShortcutDefinition("zoom_in", "放大", "Ctrl+=", "图片数据化", ("缩放", "视图")),
    ShortcutDefinition("zoom_out", "缩小", "Ctrl+-", "图片数据化", ("缩放", "视图")),
    ShortcutDefinition("zoom_fit", "适合窗口", "Ctrl+0", "图片数据化", ("缩放", "视图")),
    ShortcutDefinition("delete_rows", "删除数据行", "Delete", "图片数据化", ("表格", "编辑")),
)


class ShortcutBindingSet:
    """在页面或窗口上注册并维护一组 QShortcut。"""

    def __init__(self) -> None:
        self._shortcuts: Dict[str, QShortcut] = {}

    def bind(
        self,
        action: str,
        parent,
        callback,
        *,
        context: Optional[Qt.ShortcutContext] = None,
    ) -> QShortcut:
        shortcut = self._shortcuts.get(action)
        if shortcut is None:
            shortcut = QShortcut(QKeySequence(shortcut_manager.get(action)), parent)
            shortcut.activated.connect(callback)
            self._shortcuts[action] = shortcut
        else:
            shortcut.setKey(QKeySequence(shortcut_manager.get(action)))
        if context is not None:
            shortcut.setContext(context)
        return shortcut

    def apply(self) -> None:
        for action, shortcut in self._shortcuts.items():
            shortcut.setKey(QKeySequence(shortcut_manager.get(action)))


class ShortcutManager(QObject):
    """单例快捷键管理器，支持注册动作、加载/保存用户自定义快捷键。"""

    shortcuts_changed = Signal()
    _CONFIG_FILE = Path.home() / ".config" / "pyline" / "shortcuts.json"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._definitions: Dict[str, ShortcutDefinition] = {}
        self.DEFAULTS: Dict[str, str] = {}
        self.LABELS: Dict[str, str] = {}
        self._shortcuts: Dict[str, str] = {}
        self._register_builtin_actions()
        self._shortcuts = dict(self.DEFAULTS)
        self._load()

    def _register_builtin_actions(self) -> None:
        for definition in _BUILTIN_SHORTCUTS:
            self.register_action(
                definition.action,
                label=definition.label,
                default_sequence=definition.default,
                category=definition.category,
                tags=definition.tags,
            )

    def register_action(
        self,
        action: str,
        *,
        label: str,
        default_sequence: str = "",
        category: str = "通用",
        tags: Iterable[str] = (),
    ) -> None:
        clean_action = action.strip()
        if not clean_action:
            raise ValueError("shortcut action is required")
        definition = ShortcutDefinition(
            action=clean_action,
            label=label.strip() or clean_action,
            default=default_sequence.strip(),
            category=category.strip() or "通用",
            tags=tuple(str(tag).strip() for tag in tags if str(tag).strip()),
        )
        self._definitions[clean_action] = definition
        self.DEFAULTS[clean_action] = definition.default
        self.LABELS[clean_action] = definition.label
        self._shortcuts.setdefault(clean_action, definition.default)

    def list_definitions(self) -> List[ShortcutDefinition]:
        return list(self._definitions.values())

    def get_definition(self, action: str) -> Optional[ShortcutDefinition]:
        return self._definitions.get(action)

    def search_tags(self, action: str) -> Tuple[str, ...]:
        definition = self.get_definition(action)
        if definition is None:
            return tuple()
        return (definition.category, *definition.tags)

    def _load(self) -> None:
        try:
            if self._CONFIG_FILE.exists():
                with open(self._CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for action, key_sequence in data.items():
                    if action in self._shortcuts:
                        self._shortcuts[action] = str(key_sequence)
        except Exception:
            pass

    def save(self) -> None:
        try:
            self._CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self._CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._shortcuts, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, action: str) -> str:
        return self._shortcuts.get(action, self.DEFAULTS.get(action, ""))

    def set(self, action: str, key_sequence: str) -> None:
        if action not in self._shortcuts:
            return
        self._shortcuts[action] = key_sequence

    def reset_to_defaults(self) -> None:
        self._shortcuts = dict(self.DEFAULTS)
        self.save()
        self.shortcuts_changed.emit()

    def apply_all(self, mapping: Dict[str, str]) -> None:
        for action, key_sequence in mapping.items():
            if action in self._shortcuts:
                self._shortcuts[action] = key_sequence
        self.save()
        self.shortcuts_changed.emit()


shortcut_manager = ShortcutManager()
