from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from core.project_asset_service import ProjectAssetService
from core.project_backup_manager import ProjectBackupManager
from core.project_migration_service import ProjectMigrationService
from core.project_repository import ProjectRepository
from core.project_session import ProjectSession
from core.project_tree_service import ProjectTreeService

if TYPE_CHECKING:
    from core.project_manager import ProjectManager


@dataclass(slots=True)
class ProjectServiceBundle:
    repository: ProjectRepository
    migration_service: ProjectMigrationService
    backup_manager: ProjectBackupManager
    tree_service: ProjectTreeService
    asset_service: ProjectAssetService
    session: ProjectSession


def build_project_services(
    manager: "ProjectManager",
    *,
    project_file_suffix: str,
    aline_version: str,
) -> ProjectServiceBundle:
    from core.recent_projects import add_recent

    repository = ProjectRepository(
        project_file_suffix=project_file_suffix,
        aline_version=aline_version,
        normalize_path=manager._normalize_path,
        sync_legacy_datasets=manager.sync_legacy_datasets,
        sync_project_backups=manager._sync_project_backups,
        add_recent_project=add_recent,
    )
    migration_service = ProjectMigrationService(
        ensure_project_tree_groups=lambda p: (manager._ensure_project_tree_groups(p), None)[1],
        migrate_project_assets_to_global=manager._migrate_project_assets_to_global,
    )
    backup_manager = ProjectBackupManager(manager)
    tree_service = ProjectTreeService(
        get_current_project=lambda: manager.current_project,
        clear_last_error=manager._clear_last_operation_error,
        ensure_project_tree=migration_service.migrate_to_v2,
        canonical_group_type=manager._canonical_group_type,
        ensure_unique_tree_child_name=manager._ensure_unique_tree_child_name,
        rename_source_file=manager.rename_source_file,
        rename_image=manager.rename_image,
        rename_picture=manager.rename_picture,
        delete_backup_if_managed=manager._delete_backup_if_managed,
        delete_picture_backup_if_managed=manager._delete_picture_backup_if_managed,
        delete_source_file_backup_if_managed=manager._delete_source_file_backup_if_managed,
        node_collection_group_type=manager._node_collection_group_type,
        sync_picture_storage=manager._sync_picture_storage,
        sync_source_file_storage=manager._sync_source_file_storage,
    )
    asset_service = ProjectAssetService(
        get_current_project=lambda: manager.current_project,
        clear_last_error=manager._clear_last_operation_error,
        ensure_project_tree=migration_service.migrate_to_v2,
        ensure_unique_tree_child_name=manager._ensure_unique_tree_child_name,
        next_unique_tree_child_name=manager._next_unique_tree_child_name,
        ensure_unique_series_name=manager._ensure_unique_series_name,
        ensure_unique_curve_name=manager._ensure_unique_curve_name,
        find_folder_by_group_type=manager._find_folder_by_group_type,
        find_folder_by_name=manager._find_folder_by_name,
        get_image=manager.get_image,
        sync_legacy_datasets=manager.sync_legacy_datasets,
    )
    session = ProjectSession(
        list_projects=lambda: manager._projects,
        get_current_project=lambda: manager.current_project,
        get_current_project_id=lambda: manager._current_project_id,
        set_current_project_id=manager.set_current_project,
        create_project=manager.create_new,
        open_project=manager.open,
        save_project=manager.save,
        close_current_project_cb=manager.close_current_project,
        close_project_cb=manager.close_project,
    )
    return ProjectServiceBundle(
        repository=repository,
        migration_service=migration_service,
        backup_manager=backup_manager,
        tree_service=tree_service,
        asset_service=asset_service,
        session=session,
    )
