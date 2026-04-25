from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget
from qfluentwidgets import InfoBar, InfoBarPosition


def _message_text(content: object) -> str:
    if isinstance(content, BaseException):
        message = str(content).strip()
        return message or content.__class__.__name__
    message = str(content).strip()
    return message or "发生未知错误"


def show_warning(
    parent: Optional[QWidget],
    title: str,
    content: object,
    *,
    duration: int = 3000,
    position: InfoBarPosition = InfoBarPosition.TOP,
) -> str:
    message = _message_text(content)
    InfoBar.warning(title, message, parent=parent, position=position, duration=duration)
    return message


def show_error(
    parent: Optional[QWidget],
    title: str,
    content: object,
    *,
    duration: int = 5000,
    position: InfoBarPosition = InfoBarPosition.TOP,
) -> str:
    message = _message_text(content)
    InfoBar.error(title, message, parent=parent, position=position, duration=duration)
    return message


def show_success(
    parent: Optional[QWidget],
    title: str,
    content: object,
    *,
    duration: int = 2500,
    position: InfoBarPosition = InfoBarPosition.TOP,
) -> str:
    message = _message_text(content)
    InfoBar.success(title, message, parent=parent, position=position, duration=duration)
    return message