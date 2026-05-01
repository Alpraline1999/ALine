"""
导出/保存计划数据模型 — 在多个页面和对话框之间共享。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass(frozen=True)
class DataExportPlan:
    export_name: str
    target_data_file_id: Optional[str] = None
    new_parent_id: Optional[str] = None
    new_data_file_name: Optional[str] = None


@dataclass(frozen=True)
class DataCreateTargetOption:
    label: str
    parent_id: Optional[str] = None
    ensure_parent_id: Optional[Callable[[], Optional[str]]] = None


@dataclass(frozen=True)
class BatchDataExportPlan:
    export_names: List[str]
    target_data_file_id: Optional[str] = None
    new_parent_id: Optional[str] = None
    new_data_file_name: Optional[str] = None


@dataclass(frozen=True)
class PictureExportPlan:
    export_name: str
    target_folder_id: Optional[str]


@dataclass(frozen=True)
class AnalysisResultSavePlan:
    result_name: str
    target_parent_id: Optional[str]
