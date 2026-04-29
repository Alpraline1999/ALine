from __future__ import annotations

from typing import Optional, Protocol


class ProjectTreeBuildOwner(Protocol):
    _focus_root_group_types: list[str]
    _name_display_mode: str
    _tree: object
    _projects: list[object]

    def _capture_expansion_state(self): ...
    def _current_item_key(self): ...
    def _build_children(self, project, parent_id, parent_item) -> None: ...
    def _build_global_assets_root(self) -> None: ...
    def _restore_expansion_state(self, state) -> None: ...
    def _apply_focus_view(self, selected_key: Optional[str]) -> Optional[str]: ...
    def _restore_selection(self, selected_key: Optional[str]) -> None: ...
    def _apply_name_display_mode(self) -> None: ...
    def _schedule_wrapped_item_size_hint_update(self) -> None: ...
    def refreshed_emit(self) -> None: ...
    def _canonical_group_type(self, group_type): ...
    def _tree_node_sort_key(self, node, parent_id): ...
    def _make_item(self, node, project_id): ...
    def _make_project_item(self, project): ...


class ProjectTreeBuilder:
    def build(self, owner: ProjectTreeBuildOwner) -> None:
        expansion_state = owner._capture_expansion_state()
        selected_key = owner._current_item_key()
        owner._tree.blockSignals(True)
        owner._tree.clear()

        if not owner._projects:
            if not owner._focus_root_group_types:
                owner._build_global_assets_root()
            owner._restore_expansion_state(expansion_state)
            owner._restore_selection(selected_key)
            owner._tree.blockSignals(False)
            owner.refreshed_emit()
            return

        focus_group_types = set(owner._focus_root_group_types)
        multiple_projects = len(owner._projects) > 1
        for project in owner._projects:
            if project.tree is None:
                continue
            if focus_group_types:
                root_children = sorted(
                    project.tree.get_children(None),
                    key=lambda node: owner._tree_node_sort_key(node, None),
                )
                for node in root_children:
                    if node.kind != "folder":
                        continue
                    group_type = owner._canonical_group_type(getattr(node, "group_type", None))
                    if group_type not in focus_group_types:
                        continue
                    item = owner._make_item(node, project.id)
                    if multiple_projects:
                        label = f"{project.name} / {item.text(0)}"
                        item.setText(0, label)
                        item.setToolTip(0, label)
                    owner._tree.addTopLevelItem(item)
                    owner._build_children(project, node.id, item)
                    item.setExpanded(True)
                continue

            project_item = owner._make_project_item(project)
            owner._tree.addTopLevelItem(project_item)
            owner._build_children(project, None, project_item)
            project_item.setExpanded(True)

        if not focus_group_types:
            owner._build_global_assets_root()
        owner._restore_expansion_state(expansion_state)
        selected_key = owner._apply_focus_view(selected_key)
        owner._restore_selection(selected_key)
        owner._apply_name_display_mode()
        owner._tree.blockSignals(False)
        owner._tree.viewport().update()
        owner._tree.updateGeometry()
        if owner._name_display_mode == "wrap":
            owner._schedule_wrapped_item_size_hint_update()
        owner.refreshed_emit()
