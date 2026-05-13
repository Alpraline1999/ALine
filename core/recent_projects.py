"""
最近项目记录模块

默认使用 ~/.aline_recent.json。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

_RECENT_FILE = os.path.join(os.path.expanduser("~"), ".aline_recent.json")
_MAX_RECENT = 10


def load_recent() -> List[Dict[str, Any]]:
    """读取最近项目列表（按最新打开时间倒序）。

    返回格式：
    [
      {"path": "/a/b/c.aline", "name": "项目名", "opened_at": "2024-01-01T12:00:00"},
      ...
    ]
    自动过滤已不存在的文件。
    """
    if not os.path.exists(_RECENT_FILE):
        return []
    try:
        with open(_RECENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [item for item in data if os.path.exists(item.get("path", ""))]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def add_recent(path: str, name: str) -> None:
    """添加或更新一条最近项目记录（同路径则移到最前并更新时间）。"""
    items = load_recent()
    items = [item for item in items if item.get("path") != path]
    items.insert(0, {
        "path": path,
        "name": name,
        "opened_at": datetime.now().isoformat(),
    })
    items = items[:_MAX_RECENT]
    _save(items)


def remove_recent(path: str) -> None:
    """移除指定路径的记录。"""
    items = load_recent()
    items = [item for item in items if item.get("path") != path]
    _save(items)


def clear_recent() -> None:
    """清空最近项目列表。"""
    _save([])


def _save(items: List[Dict[str, Any]]) -> None:
    try:
        with open(_RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
