from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.builtin_ops import VERSION, build_single_line_handler


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="fft",
            name="FFT",
            handler=build_single_line_handler("fft"),
            description="将时域或空间域信号转换为频域频谱。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            config_fields=[
                ExtensionConfigField(
                    key="output",
                    label="输出类型",
                    field_type="selective",
                    default="amplitude",
                    choices=["amplitude", "power"],
                ),
                ExtensionConfigField(key="detrend", label="去直流分量", field_type="boolean", default=True),
                ExtensionConfigField(key="sampling_rate", label="采样率", field_type="number", default=1.0),
            ],
        )
    )
