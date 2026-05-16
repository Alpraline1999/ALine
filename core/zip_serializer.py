"""ZIP 容器格式的项目序列化器

提供 ZipProjectSerializer — 将 Project 序列化到 .aline ZIP 文件，
支持增量保存、按需加载曲线/系列数据。
"""
from __future__ import annotations

import json
import os
import tempfile
import zipfile
from typing import Any, Dict, Optional, Set, cast

from models.schemas import Curve, DataSeries, Project


class ZipProjectSerializer:
    """ZIP 格式的项目序列化器。

    特点：
    - project.json 只含元数据，树和配置秒开
    - 曲线点数据分块存储，按需加载
    - 增量保存：只写变更块
    - 原子写入：临时文件 + rename
    """

    FORMAT_VERSION = "1"

    # ── 格式检测 ────────────────────────────────────────────────

    @staticmethod
    def detect_format(path: str) -> str:
        """检测格式: 'zip' | 'unknown'"""
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                if 'project.json' in zf.namelist():
                    return 'zip'
        except (zipfile.BadZipFile, FileNotFoundError):
            pass
        return 'unknown'

    # ── save ────────────────────────────────────────────────────

    @staticmethod
    def save(project: Project, path: str, *,
             modified_series_ids: Optional[Set[str]] = None,
             modified_curve_ids: Optional[Set[str]] = None,
             modified_binary_paths: Optional[Set[str]] = None,
             binary_workspace: Any = None,
             empty_binary_dirs: Optional[Set[str]] = None) -> None:
        """增量保存项目。只写变更的数据块。

        Args:
            project: 要保存的 Project 对象。
            path: 目标 .aline 文件路径。
            modified_series_ids: 本次变更的 DataSeries ID 集合。
            modified_curve_ids: 本次变更的 Curve ID 集合。
            modified_binary_paths: 本次变更的二进制文件相对路径集合。
            binary_workspace: ZipBinaryWorkspace 实例，从中读取二进制文件。
            empty_binary_dirs: 树中空文件夹的 ZIP 相对路径集合（以 / 结尾）。
        """
        modified_series = modified_series_ids or set()
        modified_curves = modified_curve_ids or set()
        modified_binaries = modified_binary_paths or set()
        empty_dirs = empty_binary_dirs or set()

        # 确保父目录存在
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # 生成 meta.json
        meta = ZipProjectSerializer._build_meta(project)

        # 构建 project.json（不含曲线/系列数据点）
        project_data = project.model_dump()
        project_data.pop("file_path", None)
        project_data.pop("is_modified", None)
        ZipProjectSerializer._strip_data(project_data)

        # 写入临时 ZIP，完成后原子替换
        fd, tmp_path = tempfile.mkstemp(
            suffix='.aline.tmp',
            dir=os.path.dirname(path) if os.path.dirname(path) else None,
        )
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                # 核心元数据
                zf.writestr('project.json',
                            json.dumps(project_data, ensure_ascii=False))
                zf.writestr('meta.json',
                            json.dumps(meta, ensure_ascii=False))

                # 写入变更的数据系列
                for sid in modified_series:
                    series = ZipProjectSerializer._find_series(project, sid)
                    if series:
                        zf.writestr(
                            f'data/series_{sid}.json',
                            json.dumps({
                                'x': series.x,
                                'y': series.y,
                                'y_err': series.y_err,
                            }, ensure_ascii=False),
                        )

                # 写入变更的曲线数据
                for cid in modified_curves:
                    curve = ZipProjectSerializer._find_curve(project, cid)
                    if curve:
                        zf.writestr(
                            f'data/curve_{cid}.json',
                            json.dumps({
                                'x_data': curve.x_data,
                                'y_data': curve.y_data,
                                'x_actual': curve.x_actual,
                                'y_actual': curve.y_actual,
                            }, ensure_ascii=False),
                        )

                # 保留未变更的块（从旧 ZIP 复制）
                if (os.path.exists(path)
                        and ZipProjectSerializer.detect_format(path) == 'zip'):
                    with zipfile.ZipFile(path, 'r') as old_zf:
                        for name in old_zf.namelist():
                            if name.startswith('data/'):
                                item_id = name.replace('data/', '').replace('.json', '')
                                if item_id.startswith('series_'):
                                    sid = item_id.replace('series_', '')
                                    if sid not in modified_series:
                                        zf.writestr(name, old_zf.read(name))
                                elif item_id.startswith('curve_'):
                                    cid = item_id.replace('curve_', '')
                                    if cid not in modified_curves:
                                        zf.writestr(name, old_zf.read(name))
                            elif name.startswith('previews/'):
                                zf.writestr(name, old_zf.read(name))
                            elif name.startswith('files/'):
                                if name not in modified_binaries and name not in empty_dirs:
                                    zf.writestr(name, old_zf.read(name))

                # 写入变更的二进制文件（从暂存区）
                if binary_workspace is not None and modified_binaries:
                    binary_workspace.pack_to_zip(zf, modified_binaries)

                # 写入空文件夹条目（确保树中空文件夹在 ZIP 中有对应目录）
                for dir_path in sorted(empty_dirs):
                    info = zipfile.ZipInfo(dir_path)
                    zf.writestr(info, b'')

            # 原子替换
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    # ── load ────────────────────────────────────────────────────

    @staticmethod
    def load(path: str) -> Project:
        """加载项目。只读 project.json + meta.json，数据按需加载。

        Args:
            path: 项目文件路径（.aline ZIP 文件）。

        Returns:
            Project 对象。ZIP 格式下 series/curve 的数据点需通过
            load_series_data / load_curve_data 按需加载。

        Raises:
            ValueError: 不支持的文件格式。
        """
        with zipfile.ZipFile(path, 'r') as zf:
            project_data = json.loads(zf.read('project.json').decode('utf-8'))
        return Project(**project_data)

    # ── 按需加载数据 ────────────────────────────────────────────

    @staticmethod
    def load_series_data(path: str, series_id: str) -> Optional[Dict[str, Any]]:
        """从 ZIP 中按需加载单条 DataSeries 的数据。

        Args:
            path: .aline ZIP 文件路径。
            series_id: DataSeries.id。

        Returns:
            {'x': [...], 'y': [...], 'y_err': [...]} 或 None。
        """
        if ZipProjectSerializer.detect_format(path) != 'zip':
            return None
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                result = cast(Dict[str, Any], json.loads(
                    zf.read(f'data/series_{series_id}.json').decode('utf-8')
                ))
                return result
        except KeyError:
            return None

    @staticmethod
    def load_curve_data(path: str, curve_id: str) -> Optional[Dict[str, Any]]:
        """从 ZIP 中按需加载单条 Curve 的点数据。

        Args:
            path: .aline ZIP 文件路径。
            curve_id: Curve.id。

        Returns:
            {'x_data': [...], 'y_data': [...], ...} 或 None。
        """
        if ZipProjectSerializer.detect_format(path) != 'zip':
            return None
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                result = cast(Dict[str, Any], json.loads(
                    zf.read(f'data/curve_{curve_id}.json').decode('utf-8')
                ))
                return result
        except KeyError:
            return None

    # ── 内部辅助 ────────────────────────────────────────────────

    @staticmethod
    def _build_meta(project: Project) -> Dict[str, Any]:
        """生成 meta.json 内容。"""
        series_ids: list[str] = []
        for df in project.data_files:
            for s in df.series:
                series_ids.append(s.id)
        for ds in project.datasets:
            for s in ds.series:
                series_ids.append(s.id)

        return {
            "format_version": ZipProjectSerializer.FORMAT_VERSION,
            "aline_version": project.aline_version,
            "item_count": {
                "series": len(series_ids),
                "curves": sum(len(img.curves) for img in project.images),
                "data_files": len(project.data_files),
                "analyses": len(project.analyses),
            },
            "checksums": {},
        }

    @staticmethod
    def _strip_data(project_dict: Dict[str, Any]) -> None:
        """递归移除大字段，留下轻量元数据（原地修改）。"""
        # images -> curves -> x_data / y_data / x_actual / y_actual
        for img in project_dict.get("images", []):
            for curve in img.get("curves", []):
                curve.pop("x_data", None)
                curve.pop("y_data", None)
                curve.pop("x_actual", None)
                curve.pop("y_actual", None)
        # data_files -> series -> x / y / y_err
        for df in project_dict.get("data_files", []):
            for series in df.get("series", []):
                series.pop("x", None)
                series.pop("y", None)
                series.pop("y_err", None)
        # datasets -> series -> x / y / y_err
        for ds in project_dict.get("datasets", []):
            for series in ds.get("series", []):
                series.pop("x", None)
                series.pop("y", None)
                series.pop("y_err", None)

    @staticmethod
    def _find_series(project: Project, series_id: str) -> Optional[DataSeries]:
        """在项目中查找 DataSeries。"""
        for df in project.data_files:
            for s in df.series:
                if s.id == series_id:
                    return s
        for ds in project.datasets:
            for s in ds.series:
                if s.id == series_id:
                    return s
        return None

    @staticmethod
    def _find_curve(project: Project, curve_id: str) -> Optional[Curve]:
        """在项目的所有图像中查找 Curve。"""
        for img in project.images:
            for c in img.curves:
                if c.id == curve_id:
                    return c
        return None
