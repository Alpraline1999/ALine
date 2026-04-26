from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field


_CONFIG_PATH = Path.home() / ".config" / "aline" / "extension_settings.json"


class ExtensionSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    external_extensions_dir: str = ""
    external_extensions_dirs: list[str] = Field(default_factory=list)
    load_builtin_extensions: bool = True
    disabled_builtin_extensions: list[str] = Field(default_factory=list)
    load_external_extensions: bool = True
    disabled_external_extensions: list[str] = Field(default_factory=list)

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
    return set_external_extensions_directories([directory])[0]


def get_external_extension_settings() -> tuple[bool, list[str]]:
    settings = ExtensionSettings.load()
    return bool(settings.load_external_extensions), _normalize_external_extension_ids(settings.disabled_external_extensions)


def set_external_extension_settings(load_external: bool, disabled_extension_ids: Iterable[str] | None = None) -> ExtensionSettings:
    settings = ExtensionSettings.load()
    settings.load_external_extensions = bool(load_external)
    settings.disabled_external_extensions = _normalize_external_extension_ids(disabled_extension_ids)
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