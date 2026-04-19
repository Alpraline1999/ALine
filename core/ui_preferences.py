from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


_CONFIG_PATH = Path.home() / ".config" / "aline" / "ui_preferences.json"
TreeNameDisplayMode = Literal["wrap", "elide"]


class UIPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tree_name_display_mode: TreeNameDisplayMode = "wrap"
    home_welcome_dismissed: bool = False
    home_onboarding_completed: bool = False
    page_onboarding_completed: dict[str, bool] = Field(default_factory=dict)

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