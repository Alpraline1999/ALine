from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.global_assets import global_assets
from models.schemas import FolderNode, Project


@dataclass(slots=True)
class ProjectTreeService:
    get_current_project: Callable[[], Project | None]
    clear_last_error: Callable[[], None]
    ensure_project_tree: Callable[[Project], None]
    canonical_group_type: Callable[[str | None], str | None]
    ensure_unique_tree_child_name: Callable[..., bool]
    rename_source_file: Callable[[str, str], bool]
    rename_image: Callable[[str, str], bool]
    rename_picture: Callable[[str, str], bool]
    delete_backup_if_managed: Callable[[object, Project], None]
    delete_picture_backup_if_managed: Callable[[object, Project], None]
    delete_source_file_backup_if_managed: Callable[[object, Project], None]
    node_collection_group_type: Callable[[str], str | None]
    sync_picture_storage: Callable[[], None]
    sync_source_file_storage: Callable[[], None]

    def add_folder(self, name: str, parent_id: str | None = None, group_type: str | None = None) -> FolderNode | None:
        self.clear_last_error()
        project = self.get_current_project()
        if project is None:
            return None
        self.ensure_project_tree(project)
        if project.tree is None:
            return None
        group_type = self.canonical_group_type(group_type)
        if not self.ensure_unique_tree_child_name(parent_id, name, node_kind="folder", project=project):
            return None
        order = project.tree.get_siblings_max_order(parent_id) + 1
        node = FolderNode(name=name, parent_id=parent_id, order=order, group_type=group_type)
        project.tree.nodes.append(node)
        project.is_modified = True
        return node

    def rename_node(self, node_id: str, new_name: str) -> bool:
        self.clear_last_error()
        project = self.get_current_project()
        if project is None or project.tree is None:
            return False
        node = project.tree.get_node(node_id)
        if node is None:
            return False
        if not self.ensure_unique_tree_child_name(
            node.parent_id,
            new_name,
            node_kind=node.kind,
            exclude_node_id=node.id,
            project=project,
        ):
            return False
        if node.kind == "data_file":
            data_file = project.find_data_file(node.data_file_id)
            if data_file:
                data_file.name = new_name
        elif node.kind == "source_file":
            if not self.rename_source_file(node.source_file_id, new_name):
                return False
        elif node.kind == "image_work":
            if not self.rename_image(node.image_work_id, new_name):
                return False
        elif node.kind == "picture":
            if not self.rename_picture(node.picture_id, new_name):
                return False
        elif node.kind == "analysis_result":
            analysis = project.find_analysis(node.analysis_id)
            if analysis:
                analysis.name = new_name
        elif node.kind == "pipeline":
            global_assets.update_saved_pipeline(node.pipeline_id, name=new_name)
        elif node.kind == "figure_template":
            global_assets.update_figure_template(node.figure_id, name=new_name)
        elif node.kind == "report_template":
            global_assets.update_report_template(node.template_id, name=new_name)
        elif node.kind == "ai_prompt":
            global_assets.update_ai_prompt(node.prompt_id, name=new_name)
        elif node.kind == "ai_skill":
            global_assets.update_ai_skill(node.skill_id, name=new_name)
        elif node.kind == "ai_agent":
            global_assets.update_ai_agent(node.agent_id, name=new_name)
        node.name = new_name
        collection_group = self.node_collection_group_type(node.id)
        if node.kind in {"folder", "picture"} and collection_group == "pictures":
            self.sync_picture_storage()
        if node.kind in {"folder", "source_file"} and collection_group == "source_files":
            self.sync_source_file_storage()
        project.is_modified = True
        return True

    def delete_node(self, node_id: str) -> bool:
        project = self.get_current_project()
        if project is None or project.tree is None:
            return False

        def collect_ids(current_id: str) -> list[str]:
            ids = [current_id]
            for child in project.tree.get_children(current_id):
                ids.extend(collect_ids(child.id))
            return ids

        ids_to_delete = set(collect_ids(node_id))
        for current_id in ids_to_delete:
            node = project.tree.get_node(current_id)
            if node is None:
                continue
            if node.kind == "data_file":
                project.data_files = [item for item in project.data_files if item.id != node.data_file_id]
            elif node.kind == "source_file":
                source_file = next((item for item in project.source_files if item.id == node.source_file_id), None)
                if source_file is not None:
                    self.delete_source_file_backup_if_managed(source_file, project)
                project.source_files = [item for item in project.source_files if item.id != node.source_file_id]
            elif node.kind == "image_work":
                image = next((item for item in project.images if item.id == node.image_work_id), None)
                if image is not None:
                    self.delete_backup_if_managed(image, project)
                project.images = [item for item in project.images if item.id != node.image_work_id]
            elif node.kind == "picture":
                picture = next((item for item in project.pictures if item.id == node.picture_id), None)
                if picture is not None:
                    self.delete_picture_backup_if_managed(picture, project)
                project.pictures = [item for item in project.pictures if item.id != node.picture_id]
            elif node.kind == "pipeline":
                global_assets.delete_saved_pipeline(node.pipeline_id)
            elif node.kind == "figure_template":
                global_assets.delete_figure_template(node.figure_id)
            elif node.kind == "report_template":
                global_assets.delete_report_template(node.template_id)
            elif node.kind == "analysis_result":
                project.analyses = [item for item in project.analyses if item.id != node.analysis_id]
            elif node.kind == "ai_prompt":
                global_assets.delete_ai_prompt(node.prompt_id)
            elif node.kind == "ai_skill":
                global_assets.delete_ai_skill(node.skill_id)
            elif node.kind == "ai_agent":
                global_assets.delete_ai_agent(node.agent_id)
            elif node.kind == "ai_tool":
                tool_id = getattr(node, "tool_id", "")
                global_assets.delete_ai_prompt(tool_id)
                global_assets.delete_ai_skill(tool_id)
                global_assets.delete_ai_agent(tool_id)

        project.tree.nodes = [item for item in project.tree.nodes if item.id not in ids_to_delete]
        project.is_modified = True
        return True

    def remove_empty_folders(self, root_id: str | None = None, *, include_root: bool = False) -> list[str]:
        project = self.get_current_project()
        if project is None or project.tree is None:
            return []

        scoped_ids = None
        if root_id is not None:
            root = project.tree.get_node(root_id)
            if root is None or root.kind != "folder":
                return []

            def collect_folder_ids(node_id: str) -> list[str]:
                ids = [node_id]
                for child in project.tree.get_children(node_id):
                    if child.kind == "folder":
                        ids.extend(collect_folder_ids(child.id))
                return ids

            scoped_ids = set(collect_folder_ids(root_id))
            if not include_root:
                scoped_ids.discard(root_id)

        removed_ids: list[str] = []
        while True:
            removable_ids: list[str] = []
            for node in list(project.tree.nodes):
                if node.kind != "folder":
                    continue
                if scoped_ids is not None and node.id not in scoped_ids:
                    continue
                canonical_group = self.canonical_group_type(getattr(node, "group_type", None))
                if canonical_group not in {None, "user"} and getattr(node, "parent_id", None) is None:
                    continue
                if project.tree.get_children(node.id):
                    continue
                removable_ids.append(node.id)
            if not removable_ids:
                break
            removable_set = set(removable_ids)
            project.tree.nodes = [item for item in project.tree.nodes if item.id not in removable_set]
            removed_ids.extend(removable_ids)
            if scoped_ids is not None:
                scoped_ids.difference_update(removable_set)
        if removed_ids:
            project.is_modified = True
        return removed_ids

    def move_node(
        self,
        node_id: str,
        new_parent_id: str | None,
        new_order: int,
        *,
        group_type_aliases: dict[str, set[str]],
        tool_node_parent_group: dict[str, str],
    ) -> bool:
        self.clear_last_error()
        project = self.get_current_project()
        if project is None or project.tree is None:
            return False
        node = project.tree.get_node(node_id)
        if node is None:
            return False
        parent = project.tree.get_node(new_parent_id) if new_parent_id else None
        if parent is None or parent.kind != "folder":
            return False
        parent_group_type = self.canonical_group_type(getattr(parent, "group_type", None))
        if node.kind == "folder":
            if node.parent_id is None:
                return False
            node_group_type = self.canonical_group_type(getattr(node, "group_type", None))
            if node_group_type is None:
                current = project.tree.get_node(node.parent_id) if node.parent_id else None
                while current is not None and current.kind == "folder":
                    node_group_type = self.canonical_group_type(getattr(current, "group_type", None))
                    if node_group_type is not None:
                        break
                    current = project.tree.get_node(current.parent_id) if current.parent_id else None
            if node_group_type != parent_group_type:
                return False
            current = parent
            while current is not None and current.kind == "folder":
                if current.id == node.id:
                    return False
                current = project.tree.get_node(current.parent_id) if current.parent_id else None
            if not self.ensure_unique_tree_child_name(
                new_parent_id,
                node.name,
                node_kind="folder",
                exclude_node_id=node.id,
                project=project,
            ):
                return False
            node.parent_id = new_parent_id
            node.order = new_order
            if self.node_collection_group_type(node.id) == "pictures":
                self.sync_picture_storage()
            project.is_modified = True
            return True
        if node.kind == "data_file" and parent_group_type not in group_type_aliases["datasets"]:
            return False
        if node.kind == "source_file" and parent_group_type not in group_type_aliases["source_files"]:
            return False
        if node.kind == "image_work" and parent_group_type not in group_type_aliases["images"]:
            return False
        if node.kind == "picture" and parent_group_type not in group_type_aliases["pictures"]:
            return False
        if node.kind in tool_node_parent_group:
            required_group = tool_node_parent_group[node.kind]
            if parent_group_type not in group_type_aliases[required_group]:
                return False
        if node.kind == "ai_tool":
            required_group = {
                "prompt": "prompt_group",
                "skill": "skill_group",
                "agent": "agent_group",
            }.get(getattr(node, "tool_type", "prompt"), "prompt_group")
            if parent_group_type not in group_type_aliases[required_group]:
                return False
        if not self.ensure_unique_tree_child_name(
            new_parent_id,
            node.name,
            node_kind=node.kind,
            exclude_node_id=node.id,
            project=project,
        ):
            return False
        node.parent_id = new_parent_id
        node.order = new_order
        collection_group = self.node_collection_group_type(node.id)
        if node.kind in {"folder", "picture"} and collection_group == "pictures":
            self.sync_picture_storage()
        if node.kind in {"folder", "source_file"} and collection_group == "source_files":
            self.sync_source_file_storage()
        project.is_modified = True
        return True

    def get_node_by_id(self, node_id: str):
        project = self.get_current_project()
        if project is None or project.tree is None:
            return None
        return project.tree.get_node(node_id)

    def get_children(self, parent_id: str | None):
        project = self.get_current_project()
        if project is None or project.tree is None:
            return []
        return project.tree.get_children(parent_id)
