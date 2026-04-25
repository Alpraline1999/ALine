from __future__ import annotations

from core.extension_api import ExtensionConfigField, ProcessingExtension
from extensions.processing.base_tools import VERSION, resample_xy


def resample_handler(xs, ys, params, lines=None):
    return resample_xy(list(xs), list(ys), dict(params or {}), lines=list(lines or []))


def register_extensions(registry) -> None:
    registry.register_processing(
        ProcessingExtension(
            type="resample",
            name="重采样",
            handler=resample_handler,
            description="支持按点数或间距重采样，便于多曲线对齐。",
            version=VERSION,
            lines_number=(1, 1),
            settings=True,
            source_kind="builtin",
            config_fields=[
                ExtensionConfigField(
                    key="algorithm",
                    label="插值算法",
                    field_type="selective",
                    default="linear",
                    choices=["linear", "nearest", "cubic"],
                ),
                ExtensionConfigField(
                    key="mode",
                    label="重采样模式",
                    field_type="selective",
                    default="spacing",
                    choices=["spacing", "align"],
                ),
                ExtensionConfigField(
                    key="spacing_mode",
                    label="间距方式",
                    field_type="selective",
                    default="point",
                    choices=["point", "coord"],
                ),
                ExtensionConfigField(key="n", label="目标点数", field_type="integer", default=200, min_value=2),
                ExtensionConfigField(key="step", label="目标步长", field_type="number", default=1.0),
                ExtensionConfigField(
                    key="target_line",
                    label="对齐曲线",
                    field_type="line",
                    default=1,
                    description="从当前数据集中选择 1 条曲线作为对齐参考。",
                ),
            ],
        )
    )
