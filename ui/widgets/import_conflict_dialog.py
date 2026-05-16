"""导入名称冲突处理对话框。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from qfluentwidgets import BodyLabel, MessageBoxBase, PrimaryPushButton, PushButton, SubtitleLabel


class ImportConflictDialog(MessageBoxBase):
    """导入名称冲突处理对话框。

    显示冲突的资源名称，提供 跳过 / 覆盖 / 重命名 / 全部跳过 / 全部覆盖 选项。
    返回 {"action": "skip"|"overwrite"|"rename", "apply_to_all": bool}。
    """

    def __init__(
        self,
        resource_name: str,
        *,
        existing_info: str = "",
        imported_info: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._result: dict = {"action": "skip", "apply_to_all": False}

        title = SubtitleLabel("名称冲突", self.widget)
        title.setWordWrap(True)
        self.viewLayout.addWidget(title)

        message = BodyLabel(
            f"资源「{resource_name}」已存在。",
            self.widget,
        )
        message.setWordWrap(True)
        self.viewLayout.addWidget(message)

        if existing_info or imported_info:
            detail_lines = []
            if existing_info:
                detail_lines.append(f"已有：{existing_info}")
            if imported_info:
                detail_lines.append(f"导入：{imported_info}")
            detail = BodyLabel("\n".join(detail_lines), self.widget)
            detail.setWordWrap(True)
            self.viewLayout.addWidget(detail)

        self.widget.setMinimumWidth(460)

        # 隐藏默认按钮，自定义全部按钮
        self.yesButton.hide()
        self.cancelButton.hide()

        btn_layout = self.buttonLayout
        # 第一行：跳过 / 覆盖 / 重命名
        self._skip_btn = PushButton("跳过", self.buttonGroup)
        self._skip_btn.clicked.connect(self._on_skip)
        btn_layout.addWidget(self._skip_btn)

        self._overwrite_btn = PrimaryPushButton("覆盖", self.buttonGroup)
        self._overwrite_btn.clicked.connect(self._on_overwrite)
        btn_layout.addWidget(self._overwrite_btn)

        self._rename_btn = PushButton("重命名", self.buttonGroup)
        self._rename_btn.clicked.connect(self._on_rename)
        btn_layout.addWidget(self._rename_btn)

        # 第二行：全部跳过 / 全部覆盖
        self._all_skip_btn = PushButton("全部跳过", self.buttonGroup)
        self._all_skip_btn.clicked.connect(self._on_all_skip)
        btn_layout.addWidget(self._all_skip_btn)

        self._all_overwrite_btn = PushButton("全部覆盖", self.buttonGroup)
        self._all_overwrite_btn.clicked.connect(self._on_all_overwrite)
        btn_layout.addWidget(self._all_overwrite_btn)

    def _on_skip(self) -> None:
        self._result = {"action": "skip", "apply_to_all": False}
        self.accept()

    def _on_overwrite(self) -> None:
        self._result = {"action": "overwrite", "apply_to_all": False}
        self.accept()

    def _on_rename(self) -> None:
        self._result = {"action": "rename", "apply_to_all": False}
        self.accept()

    def _on_all_skip(self) -> None:
        self._result = {"action": "skip", "apply_to_all": True}
        self.accept()

    def _on_all_overwrite(self) -> None:
        self._result = {"action": "overwrite", "apply_to_all": True}
        self.accept()

    @property
    def result_action(self) -> str:
        return self._result["action"]

    @property
    def apply_to_all(self) -> bool:
        return self._result["apply_to_all"]
