from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


_CONFIG_PATH = Path.home() / ".config" / "aline" / "ui_preferences.json"
TreeNameDisplayMode = Literal["wrap", "elide"]


class UIPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tree_name_display_mode: TreeNameDisplayMode = "wrap"

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