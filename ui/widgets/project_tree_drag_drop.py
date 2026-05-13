"""
ProjectTreeWidget 拖放逻辑 — source file drop、节点移动、拖放源管理。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTreeWidgetItem
from qfluentwidgets import InfoBar, InfoBarPosition

from core.app_context import get_app_context


class _PMProxy:
    __slots__ = ()

    def __getattr__(self, name):
        pm = get_app_context().project_manager
        if pm is None:
            import core.project_manager as _pm_module
            pm = _pm_module.project_manager
        return getattr(pm, name)


project_manager = _PMProxy()


class ProjectTreeDragDropHelper:
    """ProjectTreeWidget 的拖放操作辅助。

    通过回调注入避免对 tree widget 的循环引用。
    """

    def __init__(
        self,
        *,
        item_role_data: Callable,
        item_key: Callable,
        item_project_id: Callable,
        find_item_by_key: Callable,
        find_item: Callable,
        expand_item_ancestors: Callable,
        dialog_parent: Callable,
        folder_collection_group: Callable,
        refresh: Callable,
        select_node: Callable[[str], None],
        select_nodes: Callable[[list[str]], None],
        project_modified: Callable,
        command_service: object,
        _SOURCE_IMAGE_SUFFIXES: set,
        _MANAGED_FOLDER_GROUP_TYPES: frozenset,
        _SYNTHETIC_GLOBAL_KINDS: frozenset,
        _ROOT_GROUP_LABELS: dict,
        _move_node_to_target: Callable,
        _batch_action_payloads: Callable,
        _common_batch_move_choices: Callable,
        tree_view: object,
    ):
        self._item_role_data = item_role_data
        self._item_key = item_key
        self._item_project_id = item_project_id
        self._find_item_by_key = find_item_by_key
        self._find_item = find_item
        self._expand_item_ancestors = expand_item_ancestors
        self._dialog_parent = dialog_parent
        self._folder_collection_group = folder_collection_group
        self._refresh = refresh
        self._select_node = select_node
        self._select_nodes = select_nodes
        self._project_modified = project_modified
        self._command_service = command_service
        self._SOURCE_IMAGE_SUFFIXES = _SOURCE_IMAGE_SUFFIXES
        self._MANAGED_FOLDER_GROUP_TYPES = _MANAGED_FOLDER_GROUP_TYPES
        self._SYNTHETIC_GLOBAL_KINDS = _SYNTHETIC_GLOBAL_KINDS
        self._ROOT_GROUP_LABELS = _ROOT_GROUP_LABELS
        self._move_node_to_target = _move_node_to_target
        self._batch_action_payloads = _batch_action_payloads
        self._common_batch_move_choices = _common_batch_move_choices
        self._tree = tree_view

        # 拖放状态
        self._drag_source_item_key: Optional[str] = None
        self._drag_source_item_keys: list[str] = []

    def normalized_source_file_drop_target(
        self,
        target_item: Optional[QTreeWidgetItem],
    ) -> tuple[Optional[str], Optional[str]]:
        """解析源文件拖放的目标。"""
        target_data = self._item_role_data(target_item)
        if not target_data:
            return None, None
        target_kind, target_id = target_data
        if target_kind == "series":
            parent_item = None if target_item is None else target_item.parent()
            parent_data = self._item_role_data(parent_item)
            if parent_data and parent_data[0] == "data_file":
                return parent_data
        if target_kind == "source_file":
            parent_item = None if target_item is None else target_item.parent()
            parent_data = self._item_role_data(parent_item)
            if parent_data and parent_data[0] == "folder":
                return parent_data
        return target_kind, target_id

    def perform_source_file_drop_action(
        self,
        source_id: str,
        target_item: Optional[QTreeWidgetItem],
        *,
        defer_view_refresh: bool = False,
    ) -> bool:
        """执行源文件的拖放导入操作。"""
        target_kind, target_id = self.normalized_source_file_drop_target(target_item)
        if not target_kind or not target_id:
            return False

        source_node = project_manager.get_node_by_id(source_id)
        if source_node is None or getattr(source_node, "kind", None) != "source_file":
            return False
        source_path = project_manager.get_source_file_path(getattr(source_node, "source_file_id", ""))
        source_asset = project_manager.get_source_file(getattr(source_node, "source_file_id", ""))
        if not source_path:
            return False

        target_data_file_id: Optional[str] = None
        target_folder_id: Optional[str] = None
        if target_kind == "data_file":
            target_node = project_manager.get_node_by_id(target_id)
            target_data_file_id = None if target_node is None else getattr(target_node, "data_file_id", None)
        elif target_kind == "folder":
            target_folder_id = target_id
        elif target_kind == "source_file":
            target_node = project_manager.get_node_by_id(target_id)
            if target_node is not None:
                target_folder_id = getattr(target_node, "parent_id", None)

        if target_folder_id and self._folder_collection_group(target_folder_id) == "source_files":
            if self._move_node_to_target("source_file", source_id, target_folder_id):
                if defer_view_refresh:
                    QTimer.singleShot(0, lambda node_id=source_id: self._finalize_drop_move(node_id))
                else:
                    self._finalize_drop_move(source_id)
                self._project_modified()
                return True

        if target_data_file_id or (target_folder_id and self._folder_collection_group(target_folder_id) == "datasets"):
            select_node_id = self._command_service.import_source_file_as_dataset(
                source_path,
                target_folder_id=target_folder_id,
                target_data_file_id=target_data_file_id,
            )
            if not select_node_id:
                return False
            if defer_view_refresh:
                QTimer.singleShot(0, lambda node_id=select_node_id: self._finalize_drop_move(node_id))
            else:
                self._finalize_drop_move(select_node_id)
            self._project_modified()
            return True

        if target_folder_id and self._folder_collection_group(target_folder_id) == "images":
            image_node_id = self._command_service.import_source_file_as_digitize_image(
                source_path,
                parent_id=target_folder_id,
                display_name=source_asset.name if source_asset is not None else Path(source_path).name,
            )
            if not image_node_id:
                return False
            final_node_id = image_node_id or target_folder_id
            InfoBar.success(
                "导入成功",
                f"已导入到数字化: {source_asset.name if source_asset is not None else Path(source_path).name}",
                parent=self._dialog_parent(),
                position=InfoBarPosition.TOP,
            )
            if defer_view_refresh:
                QTimer.singleShot(0, lambda node_id=final_node_id: self._finalize_drop_move(node_id))
            else:
                self._finalize_drop_move(final_node_id)
            self._project_modified()
            return True

        return False

    def resolve_drop_target_id(
        self,
        source_kind: str,
        source_id: str,
        target_item: Optional[QTreeWidgetItem],
    ) -> Optional[str]:
        """解析拖放目标节点 ID。"""
        target_data = self._item_role_data(target_item)
        if not target_data:
            return None
        target_kind, target_id = target_data
        resolved_target_id = self._resolve_virtual_drop_container_id(target_kind, target_id)
        if source_kind == "series":
            if target_kind == "data_file" and resolved_target_id != source_id:
                return resolved_target_id
            if target_kind == "series":
                parent_item = None if target_item is None else target_item.parent()
                parent_data = self._item_role_data(parent_item)
                if parent_data and parent_data[0] == "data_file":
                    return self._resolve_virtual_drop_container_id(parent_data[0], parent_data[1])
            return None
        if source_kind == "curve":
            if target_kind == "image_work" and resolved_target_id != source_id:
                return resolved_target_id
            if target_kind == "curve":
                parent_item = None if target_item is None else target_item.parent()
                parent_data = self._item_role_data(parent_item)
                if parent_data and parent_data[0] == "image_work":
                    return self._resolve_virtual_drop_container_id(parent_data[0], parent_data[1])
            return None
        if target_kind == "folder" and target_id != source_id:
            return target_id
        parent_item = None if target_item is None else target_item.parent()
        parent_data = self._item_role_data(parent_item)
        if parent_data and parent_data[0] == "folder":
            return parent_data[1]
        return None

    def _resolve_virtual_drop_container_id(self, target_kind: str, target_id: str) -> Optional[str]:
        if target_kind == "data_file":
            node = project_manager.get_node_by_id(target_id)
            return getattr(node, "data_file_id", None)
        if target_kind == "image_work":
            node = project_manager.get_node_by_id(target_id)
            return getattr(node, "image_work_id", None)
        return target_id

    def perform_drop_move(
        self,
        source_item: Optional[QTreeWidgetItem],
        target_item: Optional[QTreeWidgetItem],
        defer_view_refresh: bool = False,
    ) -> bool:
        """执行单节点拖放移动。"""
        source_item = self.drag_source_item_for_drop(source_item)
        source_data = self._item_role_data(source_item)
        if not source_data:
            return False
        source_kind, source_id = source_data
        if source_kind in {"project", "global_root", "global_group"} or source_kind in self._SYNTHETIC_GLOBAL_KINDS:
            return False
        source_project_id = self._item_project_id(source_item)
        target_project_id = self._item_project_id(target_item)
        if not source_project_id or source_project_id != target_project_id:
            return False
        project_manager.set_current_project(source_project_id)
        if source_kind == "source_file":
            return self.perform_source_file_drop_action(source_id, target_item, defer_view_refresh=defer_view_refresh)
        target_id = self.resolve_drop_target_id(source_kind, source_id, target_item)
        if not target_id or not self._move_node_to_target(source_kind, source_id, target_id):
            return False
        if defer_view_refresh:
            QTimer.singleShot(0, lambda node_id=source_id: self._finalize_drop_move(node_id))
        else:
            self._finalize_drop_move(source_id)
        self._project_modified()
        return True

    def perform_batch_drop_move(
        self,
        source_items: list[QTreeWidgetItem],
        target_item: Optional[QTreeWidgetItem],
        defer_view_refresh: bool = False,
    ) -> bool:
        """执行批量拖放移动。"""
        payloads = self._batch_action_payloads(source_items)
        if not payloads:
            return False

        project_ids = {self._item_project_id(item) for item in source_items}
        target_project_id = self._item_project_id(target_item)
        if len(project_ids) != 1 or not target_project_id or target_project_id not in project_ids:
            return False

        names = [str(payload.get("name") or "").strip() for payload in payloads]
        if len(set(names)) != len(names):
            return False

        target_ids = {
            self.resolve_drop_target_id(str(payload["kind"]), str(payload["node_id"]), target_item)
            for payload in payloads
        }
        target_ids.discard(None)
        if len(target_ids) != 1:
            return False

        target_id = next(iter(target_ids), None)
        if not target_id:
            return False

        common_choice_ids = {choice_id for _label, choice_id in self._common_batch_move_choices(payloads)}
        if target_id not in common_choice_ids:
            return False

        project_manager.set_current_project(target_project_id)
        moved_ids: list[str] = []
        for payload in payloads:
            node_id = str(payload["node_id"])
            kind = str(payload["kind"])
            if not self._move_node_to_target(kind, node_id, target_id):
                return False
            moved_ids.append(node_id)

        if defer_view_refresh:
            QTimer.singleShot(0, lambda node_ids=list(moved_ids): self._finalize_batch_drop_move(node_ids))
        else:
            self._finalize_batch_drop_move(moved_ids)
        self._project_modified()
        return True

    def _finalize_drop_move(self, source_id: str) -> None:
        self._refresh()
        self._select_node(source_id)
        self._tree.viewport().update()
        self._tree.updateGeometry()

    def _finalize_batch_drop_move(self, source_ids: list[str]) -> None:
        self._refresh()
        self._select_nodes(source_ids)
        self._tree.viewport().update()
        self._tree.updateGeometry()

    def remember_drag_source_item(self, item: Optional[QTreeWidgetItem]) -> None:
        self.remember_drag_source_items([item] if item is not None else [])

    def remember_drag_source_items(self, items: list[QTreeWidgetItem]) -> None:
        keys = [key for key in (self._item_key(item) for item in items) if key]
        self._drag_source_item_keys = list(dict.fromkeys(keys))
        self._drag_source_item_key = self._drag_source_item_keys[0] if self._drag_source_item_keys else None

    def drag_source_item_for_drop(self, fallback_item: Optional[QTreeWidgetItem]) -> Optional[QTreeWidgetItem]:
        remembered = self._find_item_by_key(self._drag_source_item_key)
        return remembered or fallback_item

    def drag_source_items_for_drop(self, fallback_item: Optional[QTreeWidgetItem]) -> list[QTreeWidgetItem]:
        remembered_items = [item for item in (self._find_item_by_key(key) for key in self._drag_source_item_keys) if item is not None]
        if remembered_items:
            return remembered_items
        fallback = self.drag_source_item_for_drop(fallback_item)
        return [fallback] if fallback is not None else []

    def clear_drag_source_item(self) -> None:
        self._drag_source_item_key = None
        self._drag_source_item_keys = []
