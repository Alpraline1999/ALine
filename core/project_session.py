from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True)
class ProjectSession:
    list_projects: Callable[[], list[object]]
    get_current_project: Callable[[], object | None]
    get_current_project_id: Callable[[], str | None]
    set_current_project_id: Callable[[str], None]
    create_project: Callable[[str, str | None, bool], object]
    open_project: Callable[[str], object]
    save_project: Callable[[str | None], str]
    close_current_project_cb: Callable[[], None]
    close_project_cb: Callable[[str], None]

    @property
    def projects(self) -> list[object]:
        return self.list_projects()

    @property
    def current_project(self) -> object | None:
        return self.get_current_project()

    @property
    def current_project_id(self) -> str | None:
        return self.get_current_project_id()

    def set_current_project(self, project_id: str) -> None:
        self.set_current_project_id(project_id)

    def create_new(self, name: str, parent_dir: str | None = None, create_structure: bool = False) -> object:
        return self.create_project(name, parent_dir, create_structure)

    def open(self, file_path: str) -> object:
        return self.open_project(file_path)

    def save(self, file_path: str | None = None) -> str:
        return self.save_project(file_path)

    def close_project(self, project_id: str) -> None:
        self.close_project_cb(project_id)

    def close_current_project(self) -> None:
        self.close_current_project_cb()

    def mark_current_project_modified(self) -> None:
        project = self.current_project
        if project is not None:
            project.is_modified = True
