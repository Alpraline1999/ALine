from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field


_CONFIG_PATH = Path.home() / ".config" / "aline" / "extension_settings.json"
_EXTENSION_NUMBER_DECIMALS_DEFAULT = 6
_EXTENSION_NUMBER_DECIMALS_MIN = 0
_EXTENSION_NUMBER_DECIMALS_MAX = 12


class ExtensionSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    external_extensions_dir: str = ""
    external_extensions_dirs: list[str] = Field(default_factory=list)
    load_builtin_extensions: bool = True
    disabled_builtin_extensions: list[str] = Field(default_factory=list)
    load_external_extensions: bool = True
    disabled_external_extensions: list[str] = Field(default_factory=list)
    external_extension_sandbox: bool = False
    number_decimals: int = _EXTENSION_NUMBER_DECIMALS_DEFAULT

    @classmethod
    def load(cls) -> "ExtensionSettings":
        if _CONFIG_PATH.exists():
            try:
                data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
                return cls(**data)
            except Exception:
                pass
        return cls()

    def save(self) -> None:
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(self.model_dump_json(indent=2), encoding="utf-8")


def default_external_extensions_directory() -> Path:
    return (_CONFIG_PATH.parent / "extensions").resolve(strict=False)


def _normalize_builtin_extension_ids(extension_ids: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in extension_ids or []:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        normalized.append(clean)
    return normalized


def _normalize_external_extension_ids(extension_ids: Iterable[str] | None) -> list[str]:
    return _normalize_builtin_extension_ids(extension_ids)


def _normalize_extension_number_decimals(value: int | None) -> int:
    try:
        numeric = int(_EXTENSION_NUMBER_DECIMALS_DEFAULT if value is None else value)
    except (TypeError, ValueError):
        numeric = _EXTENSION_NUMBER_DECIMALS_DEFAULT
    return max(_EXTENSION_NUMBER_DECIMALS_MIN, min(_EXTENSION_NUMBER_DECIMALS_MAX, numeric))


def _normalize_extension_directory(directory: str | Path | None) -> Path:
    raw = str(directory or "").strip()
    path = Path(raw).expanduser() if raw else default_external_extensions_directory()
    if path.exists() and not path.is_dir():
        raise ValueError("扩展目录必须是文件夹路径")
    return path.resolve(strict=False)


def _normalize_extension_directories(directories: Iterable[str | Path] | None) -> list[Path]:
    normalized: list[Path] = []
    seen: set[str] = set()
    raw_items = list(directories or [])
    if not raw_items:
        return [default_external_extensions_directory()]

    for item in raw_items:
        path = _normalize_extension_directory(item)
        marker = str(path)
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(path)

    return normalized or [default_external_extensions_directory()]


def get_external_extensions_directories() -> list[Path]:
    settings = ExtensionSettings.load()
    configured = list(settings.external_extensions_dirs or [])
    if not configured and settings.external_extensions_dir.strip():
        configured = [settings.external_extensions_dir.strip()]
    try:
        return _normalize_extension_directories(configured)
    except ValueError:
        return [default_external_extensions_directory()]


def get_external_extensions_directory() -> Path:
    return get_external_extensions_directories()[0]


def set_external_extensions_directories(directories: Iterable[str | Path] | None) -> list[Path]:
    normalized = _normalize_extension_directories(directories)
    for path in normalized:
        path.mkdir(parents=True, exist_ok=True)
    settings = ExtensionSettings.load()
    settings.external_extensions_dirs = [str(path) for path in normalized]
    settings.external_extensions_dir = str(normalized[0]) if normalized else ""
    settings.save()
    return normalized


def set_external_extensions_directory(directory: str | Path | None) -> Path:
    return set_external_extensions_directories([directory] if directory is not None else [])[0]


def get_external_extension_settings() -> tuple[bool, list[str]]:
    settings = ExtensionSettings.load()
    return bool(settings.load_external_extensions), _normalize_external_extension_ids(settings.disabled_external_extensions)


def get_extension_number_decimals() -> int:
    settings = ExtensionSettings.load()
    return _normalize_extension_number_decimals(settings.number_decimals)


def set_extension_number_decimals(decimals: int | None) -> ExtensionSettings:
    settings = ExtensionSettings.load()
    settings.number_decimals = _normalize_extension_number_decimals(decimals)
    settings.save()
    return settings


def set_external_extension_settings(load_external: bool, disabled_extension_ids: Iterable[str] | None = None) -> ExtensionSettings:
    settings = ExtensionSettings.load()
    settings.load_external_extensions = bool(load_external)
    settings.disabled_external_extensions = _normalize_external_extension_ids(disabled_extension_ids)
    settings.save()
    return settings


def get_external_extension_sandbox_enabled() -> bool:
    settings = ExtensionSettings.load()
    return bool(settings.external_extension_sandbox)


def set_external_extension_sandbox_enabled(enabled: bool) -> ExtensionSettings:
    settings = ExtensionSettings.load()
    settings.external_extension_sandbox = bool(enabled)
    settings.save()
    return settings


def get_builtin_extension_settings() -> tuple[bool, list[str]]:
    settings = ExtensionSettings.load()
    return bool(settings.load_builtin_extensions), _normalize_builtin_extension_ids(settings.disabled_builtin_extensions)


def set_builtin_extension_settings(load_builtin: bool, disabled_extension_ids: Iterable[str] | None = None) -> ExtensionSettings:
    settings = ExtensionSettings.load()
    settings.load_builtin_extensions = bool(load_builtin)
    settings.disabled_builtin_extensions = _normalize_builtin_extension_ids(disabled_extension_ids)
    settings.save()
    return settings


# ── 外部扩展文件管理 ──────────────────────────────────────


def add_external_extension_file(source_path: str | Path) -> Path:
    """Copy a .py file into the first external extensions directory and return the target path."""
    from shutil import copy2

    source = Path(source_path).expanduser().resolve(strict=True)
    if source.suffix.lower() != ".py":
        raise ValueError("仅支持 .py 扩展文件")

    directories = get_external_extensions_directories()
    target_dir = directories[0]
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / source.name

    if target_path.exists():
        raise FileExistsError(f"文件已存在: {target_path}")

    copy2(str(source), str(target_path))
    return target_path


def delete_external_extension_file(file_path: str | Path) -> None:
    """Delete an external extension file."""
    target = Path(file_path).expanduser().resolve(strict=False)
    directories = get_external_extensions_directories()
    resolved_dirs = {str(d.resolve(strict=False)) for d in directories}

    if not any(str(target).startswith(d) for d in resolved_dirs):
        raise PermissionError("只能删除外部扩展目录中的文件")

    if not target.exists():
        raise FileNotFoundError(f"文件不存在: {target}")

    if target.suffix.lower() != ".py":
        raise ValueError("仅支持删除 .py 扩展文件")

    target.unlink()


def resolve_external_extension_path(spec_id: str) -> Path | None:
    """Resolve a spec ID to its full file path in external extension directories."""
    directories = get_external_extensions_directories()
    spec_name = Path(spec_id).stem.strip()
    for directory in directories:
        for py_file in directory.rglob("*.py"):
            if py_file.stem == spec_name:
                return py_file
    return None


_EXTENSION_TEMPLATES: dict[str, str] = {
    "processing": '''from core.extension_api import ProcessingExtension

register_extensions = ...

extension = ProcessingExtension(
    type="${EXTENSION_TYPE}",
    name="${EXTENSION_NAME}",
    description="",
    parameters=[],
    lines=1,
)
''',
    "analysis": '''from core.extension_api import AnalysisExtension

register_extensions = ...

extension = AnalysisExtension(
    type="${EXTENSION_TYPE}",
    name="${EXTENSION_NAME}",
    description="",
    parameters=[],
    lines=1,
)
''',
    "plot": '''from core.extension_api import PlotExtension

register_extensions = ...

extension = PlotExtension(
    type="${EXTENSION_TYPE}",
    name="${EXTENSION_NAME}",
    description="",
    parameters=[],
    lines=1,
)
''',
    "digitize": '''from core.extension_api import DigitizeExtension

register_extensions = ...

extension = DigitizeExtension(
    type="${EXTENSION_TYPE}",
    name="${EXTENSION_NAME}",
    description="",
    parameters=[],
    lines=0,
)
''',
}


def create_external_extension_file(category: str, extension_name: str) -> Path:
    """Create a new external extension .py file from a template and return its path."""
    normalized_category = str(category or "").strip().lower()
    template = _EXTENSION_TEMPLATES.get(normalized_category)
    if template is None:
        raise ValueError(f"不支持的扩展类别: {category}")

    normalized_name = str(extension_name or "").strip()
    if not normalized_name:
        raise ValueError("扩展名称不能为空")

    import re
    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", normalized_name)
    extension_type = safe_name
    file_name = safe_name + ".py"

    directories = get_external_extensions_directories()
    target_dir = directories[0]
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / file_name

    if target_path.exists():
        counter = 1
        while target_path.exists():
            target_path = target_dir / f"{safe_name}_{counter}.py"
            counter += 1

    content = (
        template
        .replace("${EXTENSION_TYPE}", extension_type)
        .replace("${EXTENSION_NAME}", normalized_name)
    )
    target_path.write_text(content, encoding="utf-8")
    return target_path