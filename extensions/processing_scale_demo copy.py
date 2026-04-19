from core.extension_api import ExtensionConfigField, ProcessingExtension


def scale_y_values(xs, ys, params):
    return list(ys), list(xs)


def register_extensions(registry):
    registry.register_processing(
        ProcessingExtension(
            type="demo_processing_complex",
            name="示例·复杂处理",
            handler=scale_y_values,
            description="X/Y 交换",
        )
    )