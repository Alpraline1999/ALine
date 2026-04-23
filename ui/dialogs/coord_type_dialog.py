from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
from qfluentwidgets import BodyLabel, PrimaryPushButton, PushButton
from qfluentwidgets import ComboBox
from PySide6.QtCore import Qt
from ui.theme import border_color, secondary_color, surface_color


class CoordTypeDialog(QDialog):
    """坐标类型选择对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._coord_type = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("选择坐标类型")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)

        title_label = BodyLabel("请选择坐标类型:", self)
        layout.addWidget(title_label)

        self._type_combo = ComboBox(self)
        self._type_combo.addItems(["二维线性坐标 (Cartesian)", "二维对数坐标 (Log)", "二维极坐标 (Polar)"])
        self._type_combo.setCurrentIndex(0)
        layout.addWidget(self._type_combo)

        # 说明标签
        self._desc_label = BodyLabel(
            "二维线性坐标：用X轴和Y轴表示平面上的点\n"
            "二维对数坐标：X轴或Y轴使用对数刻度\n"
            "二维极坐标：用距离和角度表示平面上的点",
            self
        )
        self._desc_label.setStyleSheet(
            f"color: {secondary_color()}; padding: 10px; background: {surface_color()};"
            f" border: 1px solid {border_color()}; border-radius: 6px;"
        )
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label)

        btn_layout = QHBoxLayout()
        self._ok_btn = PrimaryPushButton("确定", self)
        self._cancel_btn = PushButton("取消", self)
        self._ok_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self._ok_btn)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def get_coord_type(self) -> str:
        """获取选择的坐标类型"""
        types = ["linear", "log", "polar"]
        return types[self._type_combo.currentIndex()]
