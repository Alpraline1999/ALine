from __future__ import annotations

from core.extension_api import DigitizeExtension, ExtensionConfigField
from digitize.builtin_extensions import COLOR_DIGITIZE_EXTENSION_TYPE, _BUILTIN_EXTENSION_VERSION, _color_digitize


def register_extensions(registry) -> None:
    registry.register_digitize(
        DigitizeExtension(
            type=COLOR_DIGITIZE_EXTENSION_TYPE,
            name="颜色识别",
            handler=_color_digitize,
            description="按采样颜色和容差自动提取图像中的散点位置。",
            version=_BUILTIN_EXTENSION_VERSION,
            settings=True,
            config_fields=[
                ExtensionConfigField(
                    key="tolerance",
                    label="颜色容差",
                    description="颜色识别使用的容差强度。",
                    field_type="integer",
                    default=20,
                    min_value=1,
                    max_value=80,
                ),
                ExtensionConfigField(
                    key="step",
                    label="搜索步长",
                    description="图像扫描步长。",
                    field_type="integer",
                    default=5,
                    min_value=1,
                    max_value=20,
                ),
            ],
        )
    )
