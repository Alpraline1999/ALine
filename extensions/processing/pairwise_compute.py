from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.builtin_ops import VERSION, pairwise_compute_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="pairwise_compute",
            name="双曲线运算",
            handler=pairwise_compute_handler,
            description="使用两条输入曲线执行 x1/y1/x2/y2 表达式运算。",
            version=VERSION,
            lines_number=(2, 2),
            settings=True,
            config_fields=[
                ExtensionConfigField(key="x_expr", label="X 表达式", field_type="string", default="x1"),
                ExtensionConfigField(key="y_expr", label="Y 表达式", field_type="string", default="y1"),
            ],
        )
    )
