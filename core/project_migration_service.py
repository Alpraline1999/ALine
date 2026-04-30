from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from models.schemas import (
    AIAgentNode,
    AIPromptNode,
    AISkillNode,
    DataFile,
    DataFileNode,
    FolderNode,
    ImageWorkNode,
    PictureNode,
    Project,
    ProjectTree,
)


@dataclass(slots=True)
class ProjectMigrationService:
    ensure_project_tree_groups: Callable[[Project], None]
    migrate_project_assets_to_global: Callable[[Project], bool]

    def init_new_project_tree(self, project: Project) -> None:
        project.tree = ProjectTree()
        self.ensure_project_tree_groups(project)

    def migrate_to_v2(self, project: Project | None) -> None:
        if project is None:
            return
        if project.tree is not None:
            self.ensure_project_tree_groups(project)
            return

        project.tree = ProjectTree()
        order = 0

        if project.datasets:
            ds_folder = FolderNode(name="数据集", order=order, group_type="datasets")
            project.tree.nodes.append(ds_folder)
            order += 1

            for dataset in project.datasets:
                data_file = DataFile(
                    id=str(uuid.uuid4()),
                    name=dataset.name,
                    series=list(dataset.series),
                )
                project.data_files.append(data_file)
                project.tree.nodes.append(
                    DataFileNode(
                        name=dataset.name,
                        parent_id=ds_folder.id,
                        data_file_id=data_file.id,
                        order=len(project.tree.nodes),
                    )
                )

        if project.images:
            image_folder = FolderNode(name="数字化", order=order, group_type="images")
            project.tree.nodes.append(image_folder)
            order += 1

            for image in project.images:
                project.tree.nodes.append(
                    ImageWorkNode(
                        name=image.name,
                        parent_id=image_folder.id,
                        image_work_id=image.id,
                        order=len(project.tree.nodes),
                    )
                )

        if project.pictures:
            picture_folder = FolderNode(name="图片集", order=order, group_type="pictures")
            project.tree.nodes.append(picture_folder)
            order += 1

            for picture in project.pictures:
                project.tree.nodes.append(
                    PictureNode(
                        name=picture.name,
                        parent_id=picture_folder.id,
                        picture_id=picture.id,
                        order=len(project.tree.nodes),
                    )
                )

        tools_folder = FolderNode(name="工具集", order=order, group_type="tools")
        project.tree.nodes.append(tools_folder)
        project.tree.nodes.append(
            FolderNode(
                name="Pipelines",
                parent_id=tools_folder.id,
                order=0,
                group_type="pipeline_group",
            )
        )

        self.ensure_project_tree_groups(project)
        project.aline_version = "0.2"
        project.is_modified = True

    def migrate_to_v3(self, project: Project | None) -> None:
        if project is None:
            return
        if project.tree is None:
            self.migrate_to_v2(project)
        if project.tree is None:
            return

        name_to_group = {
            "源文件": "source_files",
            "数据集": "datasets",
            "图片集": "pictures",
            "数字化": "images",
            "工具集": "tools",
            "Pipelines": "pipeline_group",
            "绘图模板": "figure_template_group",
            "绘图模板组": "figure_template_group",
            "报告模板": "report_template_group",
            "分析结果": "analysis_result_group",
            "AI 工具": "ai_group",
            "Prompts": "prompt_group",
            "Skills": "skill_group",
            "Agents": "agent_group",
        }
        for node in project.tree.nodes:
            if node.kind == "folder" and node.group_type is None:
                node.group_type = name_to_group.get(node.name)  # type: ignore[assignment]

        new_nodes = []
        for node in project.tree.nodes:
            if node.kind == "ai_tool":
                if node.tool_type == "prompt":
                    new_nodes.append(
                        AIPromptNode(
                            id=node.id,
                            name=node.name,
                            parent_id=node.parent_id,
                            order=node.order,
                            prompt_id=node.tool_id,
                        )
                    )
                elif node.tool_type == "skill":
                    new_nodes.append(
                        AISkillNode(
                            id=node.id,
                            name=node.name,
                            parent_id=node.parent_id,
                            order=node.order,
                            skill_id=node.tool_id,
                        )
                    )
                elif node.tool_type == "agent":
                    new_nodes.append(
                        AIAgentNode(
                            id=node.id,
                            name=node.name,
                            parent_id=node.parent_id,
                            order=node.order,
                            agent_id=node.tool_id,
                        )
                    )
            else:
                new_nodes.append(node)
        project.tree.nodes = new_nodes

        self.migrate_project_assets_to_global(project)
        self.ensure_project_tree_groups(project)
        project.aline_version = "0.3"
        project.is_modified = True
