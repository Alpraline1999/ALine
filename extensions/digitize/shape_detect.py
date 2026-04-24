from __future__ import annotations

from core.extension_api import DigitizeExtension, ExtensionConfigField
from digitize.builtin_extensions import SHAPE_DIGITIZE_EXTENSION_TYPE, _BUILTIN_EXTENSION_VERSION, _shape_digitize


def register_extensions(registry) -> None:
    registry.register_digitize(
        DigitizeExtension(
            type=SHAPE_DIGITIZE_EXTENSION_TYPE,
            name="图形识别 (测试功能)",
            handler=_shape_digitize,
            description="按截图模板和匹配阈值搜索图中相同形状。",
            version=_BUILTIN_EXTENSION_VERSION,
            settings=True,
            config_fields=[
                ExtensionConfigField(
                    key="threshold",
                    label="匹配精度",
                    description="形状匹配阈值。",
                    field_type="limited",
                    default=0.65,
                    min_value=0.3,
                    max_value=0.95,
                    step=0.01,
                ),
                ExtensionConfigField(
                    key="color_weight",
                    label="颜色权重",
                    description="颜色分数在总匹配评分中的占比。",
                    field_type="limited",
                    default=0.7,
                    min_value=0.0,
                    max_value=1.0,
                    step=0.01,
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
