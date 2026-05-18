from matplotlib.patches import Circle

from core.extension_api import ExtensionConfigField, PlotExtension
from core.value_parsing import coerce_float
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION


def draw_circle_annotation(plot_context, params):
    axis = plot_context.axis
    if axis is None:
        return

    transform = axis.transData if str(params.get("coordinate_mode", "axes_fraction")).strip().lower() == "data" else axis.transAxes
    x = coerce_float(params.get("x", params.get("center_x", 0.5)), 0.5) or 0.5
    y = coerce_float(params.get("y", params.get("center_y", 0.5)), 0.5) or 0.5
    radius = max(0.0, coerce_float(params.get("radius", 0.12), 0.12) or 0.12)
    alpha = min(1.0, max(0.0, coerce_float(params.get("alpha", 0.22), 0.22) or 0.22))
    fill = bool(params.get("fill", False))
    facecolor = str(params.get("face_color", "#ffd966")) if fill else "none"

    patch = Circle(
        (x, y),
        radius,
        transform=transform,
        facecolor=facecolor,
        edgecolor=str(params.get("edge_color", "#ff8c00")),
        linewidth=max(0.1, coerce_float(params.get("line_width", 1.6), 1.6) or 1.6),
        linestyle=str(params.get("line_style", "--")),
        alpha=alpha,
        fill=fill,
        clip_on=False,
    )
    axis.add_patch(patch)


def register_extensions(registry):
    registry.register_plot(
        PlotExtension(
            type="plot_circle_annotation",
            name="圆形框",
            handler=draw_circle_annotation,
            description="在图中绘制圆形框，适合圈出局部特征。",
            version=BUILTIN_EXTENSION_VERSION,
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            hidden=True,
            phases=("after_plot",),
            config_fields=[
                ExtensionConfigField(key="coordinate_mode", description="坐标模式：axes_fraction 使用画布比例坐标，data 使用数据坐标。", field_type="selective", default="axes_fraction", choices=("axes_fraction", "data")),
                ExtensionConfigField(key="x", description="圆心 X。", field_type="number", default=0.5),
                ExtensionConfigField(key="y", description="圆心 Y。", field_type="number", default=0.5),
                ExtensionConfigField(key="radius", description="圆半径。", field_type="number", default=0.12),
                ExtensionConfigField(key="edge_color", description="边框颜色。", field_type="color", default="#ff8c00"),
                ExtensionConfigField(key="face_color", description="填充颜色。", field_type="color", default="#ffd966"),
                ExtensionConfigField(key="line_width", description="边框线宽。", field_type="number", default=1.6),
                ExtensionConfigField(key="line_style", description="边框线型。", field_type="selective", default="--", choices=("-", "--", "-.", ":")),
                ExtensionConfigField(key="alpha", description="圆形框透明度。", field_type="limited", default=0.22, min_value=0.0, max_value=1.0, step=0.01),
                ExtensionConfigField(key="fill", description="是否填充圆形框内部。", field_type="boolean", default=False),
            ],
        )
    )
