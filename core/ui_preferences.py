from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


_CONFIG_PATH = Path.home() / ".config" / "aline" / "ui_preferences.json"
TreeNameDisplayMode = Literal["wrap", "elide"]


class UIPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tree_name_display_mode: TreeNameDisplayMode = "elide"
    language: str = "zh_CN"
    ui_font_family: str = ""
    page_tree_focus_mode: bool = False
    home_welcome_dismissed: bool = False
    home_onboarding_completed: bool = False
    page_onboarding_completed: dict[str, bool] = Field(default_factory=dict)
    data_page_source_favorites: list[str] = Field(default_factory=list)
    auto_save_enabled: bool = True
    auto_save_interval_seconds: int = 300
    interface_scale: float = 0.0  # 0.0 = auto/system, 1.0=100%, 1.25=125%, etc.

    @classmethod
    def load(cls) -> "UIPreferences":
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


def get_tree_name_display_mode() -> TreeNameDisplayMode:
    return UIPreferences.load().tree_name_display_mode


def set_tree_name_display_mode(mode: TreeNameDisplayMode) -> TreeNameDisplayMode:
    prefs = UIPreferences.load()
    prefs.tree_name_display_mode = "elide" if mode == "elide" else "wrap"
    prefs.save()
    return prefs.tree_name_display_mode


def get_ui_language() -> str:
    language = str(UIPreferences.load().language or "zh_CN").strip()
    return language if language in {"zh_CN", "en_US"} else "zh_CN"


def set_ui_language(language: str) -> str:
    prefs = UIPreferences.load()
    clean = str(language or "").strip()
    prefs.language = clean if clean in {"zh_CN", "en_US"} else "zh_CN"
    prefs.save()
    return prefs.language


def get_ui_font_family() -> str:
    return str(UIPreferences.load().ui_font_family or "").strip()


def set_ui_font_family(family: str) -> str:
    prefs = UIPreferences.load()
    prefs.ui_font_family = str(family or "").strip()
    prefs.save()
    return prefs.ui_font_family


def is_page_tree_focus_mode_enabled() -> bool:
    return bool(UIPreferences.load().page_tree_focus_mode)


def set_page_tree_focus_mode_enabled(enabled: bool) -> bool:
    prefs = UIPreferences.load()
    prefs.page_tree_focus_mode = bool(enabled)
    prefs.save()
    return bool(prefs.page_tree_focus_mode)


def is_home_welcome_dismissed() -> bool:
    return UIPreferences.load().home_welcome_dismissed


def set_home_welcome_dismissed(dismissed: bool) -> bool:
    prefs = UIPreferences.load()
    prefs.home_welcome_dismissed = bool(dismissed)
    prefs.save()
    return prefs.home_welcome_dismissed


def is_home_onboarding_completed() -> bool:
    prefs = UIPreferences.load()
    return bool(prefs.home_onboarding_completed or prefs.home_welcome_dismissed)


def set_home_onboarding_completed(completed: bool) -> bool:
    prefs = UIPreferences.load()
    prefs.home_onboarding_completed = bool(completed)
    prefs.save()
    return prefs.home_onboarding_completed


def is_page_onboarding_completed(page_key: str) -> bool:
    prefs = UIPreferences.load()
    return bool(prefs.page_onboarding_completed.get(page_key.strip().lower(), False))


def set_page_onboarding_completed(page_key: str, completed: bool) -> bool:
    prefs = UIPreferences.load()
    key = page_key.strip().lower()
    if not key:
        return False
    prefs.page_onboarding_completed[key] = bool(completed)
    prefs.save()
    return bool(prefs.page_onboarding_completed.get(key, False))


def reset_all_onboarding_progress() -> None:
    prefs = UIPreferences.load()
    prefs.home_welcome_dismissed = False
    prefs.home_onboarding_completed = False
    prefs.page_onboarding_completed = {}
    prefs.save()


def get_data_page_source_favorites() -> list[str]:
    prefs = UIPreferences.load()
    result: list[str] = []
    for raw_path in prefs.data_page_source_favorites:
        clean = str(raw_path or "").strip()
        if not clean:
            continue
        if clean not in result:
            result.append(clean)
    return result


def set_data_page_source_favorites(paths: list[str]) -> list[str]:
    prefs = UIPreferences.load()
    normalized: list[str] = []
    for raw_path in paths:
        clean = str(raw_path or "").strip()
        if not clean or clean in normalized:
            continue
        normalized.append(clean)
    prefs.data_page_source_favorites = normalized
    prefs.save()
    return list(prefs.data_page_source_favorites)


def get_auto_save_enabled() -> bool:
    return bool(UIPreferences.load().auto_save_enabled)


def set_auto_save_enabled(enabled: bool) -> bool:
    prefs = UIPreferences.load()
    prefs.auto_save_enabled = bool(enabled)
    prefs.save()
    return bool(prefs.auto_save_enabled)


def get_auto_save_interval_seconds() -> int:
    return max(30, int(UIPreferences.load().auto_save_interval_seconds or 300))


def set_auto_save_interval_seconds(interval: int) -> int:
    prefs = UIPreferences.load()
    prefs.auto_save_interval_seconds = max(30, int(interval))
    prefs.save()
    return int(prefs.auto_save_interval_seconds)


def get_interface_scale() -> float:
    return float(UIPreferences.load().interface_scale or 0.0)


def set_interface_scale(scale: float) -> float:
    prefs = UIPreferences.load()
    prefs.interface_scale = max(0.0, float(scale))
    prefs.save()
    return float(prefs.interface_scale)
