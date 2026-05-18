"""局部放大绘图扩展 - 在当前图表中生成指定区域的对照放大视图。"""

from core.extension_api import ExtensionConfigField, PlotExtension
from core.value_parsing import coerce_float
from extensions.processing.extension_tools import BUILTIN_EXTENSION_VERSION

# 线型映射
_LS_MAP = {"-": "solid", "--": "dashed", "-.": "dashdot", ":": "dotted"}


def draw_local_zoom(plot_context, params):
    """在当前图表中绘制指定区域的放大嵌入视图。"""
    axis = plot_context.axis
    if axis is None:
        return

    x_min, x_max = axis.get_xlim()
    y_min, y_max = axis.get_ylim()
    view_w = x_max - x_min
    view_h = y_max - y_min

    # ── 1. 原图放大范围（选取要放大的数据区域）──
    src_mode = str(params.get("src_mode", "percentage"))
    if src_mode == "coordinate":
        src_x1 = coerce_float(params.get("src_x1", params.get("coord_x1", x_min + view_w * 0.25)), x_min)
        src_x2 = coerce_float(params.get("src_x2", params.get("coord_x2", x_max - view_w * 0.25)), x_max)
        src_y1 = coerce_float(params.get("src_y1", params.get("coord_y1", y_min + view_h * 0.25)), y_min)
        src_y2 = coerce_float(params.get("src_y2", params.get("coord_y2", y_max - view_h * 0.25)), y_max)
    else:
        pct_x1 = float(params.get("src_x1", params.get("pct_x1", 25)))
        pct_x2 = float(params.get("src_x2", params.get("pct_x2", 75)))
        pct_y1 = float(params.get("src_y1", params.get("pct_y1", 25)))
        pct_y2 = float(params.get("src_y2", params.get("pct_y2", 75)))
        src_x1 = x_min + view_w * pct_x1 / 100.0
        src_x2 = x_min + view_w * pct_x2 / 100.0
        src_y1 = y_min + view_h * pct_y1 / 100.0
        src_y2 = y_min + view_h * pct_y2 / 100.0

    if src_x1 > src_x2:
        src_x1, src_x2 = src_x2, src_x1
    if src_y1 > src_y2:
        src_y1, src_y2 = src_y2, src_y1

    # ── 2. 放大图位置（嵌入视图在主图上的锚定区域，全画幅百分比）──
    ins_pct_x1 = float(params.get("inset_pct_x1", 50))
    ins_pct_x2 = float(params.get("inset_pct_x2", 95))
    ins_pct_y1 = float(params.get("inset_pct_y1", 50))
    ins_pct_y2 = float(params.get("inset_pct_y2", 95))

    # ── 3. 创建放大嵌入视图 ──
    fig = axis.figure
    parent_pos = axis.get_position()
    fig_left = parent_pos.x0 + parent_pos.width * ins_pct_x1 / 100.0
    fig_bottom = parent_pos.y0 + parent_pos.height * ins_pct_y1 / 100.0
    fig_width = parent_pos.width * (ins_pct_x2 - ins_pct_x1) / 100.0
    fig_height = parent_pos.height * (ins_pct_y2 - ins_pct_y1) / 100.0

    axins = fig.add_axes([fig_left, fig_bottom, fig_width, fig_height])

    # 嵌入视图的数据范围固定等于原图选取范围（忠实放大）
    axins.set_xlim(src_x1, src_x2)
    axins.set_ylim(src_y1, src_y2)
    axins.tick_params(labelleft=False, labelbottom=False, left=False, bottom=False)

    # ── 4. 在嵌入视图中重绘曲线（忠实放大，不降采样）──
    for series in (plot_context.visible_series or []):
        x_data = list(series.get("x") or [])
        y_data = list(series.get("y") or [])
        if not x_data or not y_data:
            continue

        sty = series.get("style") or {}
        plot_kwargs = {
            "color": sty.get("color", "C0"),
            "linestyle": sty.get("linestyle", "-"),
            "linewidth": sty.get("linewidth", 1.0),
            "alpha": sty.get("alpha", 1.0),
        }

        # 保持与原图一致的虚线缩放
        dash_scale = float(sty.get("dash_scale", 1.0))
        linestyle = plot_kwargs["linestyle"]
        if linestyle in ("--", ":", "-.") and dash_scale != 1.0:
            base_dashes = {"--": [6, 4], ":": [1, 2], "-.": [8, 3, 1, 3]}
            dashes = base_dashes.get(linestyle)
            if dashes:
                plot_kwargs["dashes"] = [s * dash_scale for s in dashes]

        # 保持与原图一致的散点样式
        marker = sty.get("marker", "")
        if marker:
            plot_kwargs["marker"] = marker
            plot_kwargs["markersize"] = sty.get("marker_size", 6)
            markevery = max(1, int(sty.get("markevery", 1)))
            if markevery > 1:
                plot_kwargs["markevery"] = markevery

        axins.plot(x_data, y_data, **plot_kwargs)

    # ── 5. 原图放大区域边框（仅保留用户配置的框）──
    zoom_box_color = str(params.get("zoom_box_color", "#C23B22"))
    zoom_box_style = str(params.get("zoom_box_style", "--"))
    box_lw = coerce_float(params.get("box_linewidth", 1.2), 1.2)

    if zoom_box_style != "none":
        from matplotlib.patches import Rectangle
        rect = Rectangle(
            (src_x1, src_y1), src_x2 - src_x1, src_y2 - src_y1,
            fill=False, edgecolor=zoom_box_color,
            linestyle=_LS_MAP.get(zoom_box_style, zoom_box_style),
            linewidth=box_lw,
        )
        axis.add_patch(rect)

    # ── 6. 连接线 ──
    if bool(params.get("show_connector", True)):
        conn_style = str(params.get("connector_style", "--"))
        conn_start = str(params.get("connector_start", "none"))
        conn_end = str(params.get("connector_end", "none"))
        conn_lw = coerce_float(params.get("connector_linewidth", 0.8), 0.8)
        arrow_size = coerce_float(
            params.get("connector_arrow_size", params.get("connector_endpoint_size", 10)),
            10,
        )
        circle_size = coerce_float(
            params.get("connector_circle_size", params.get("connector_endpoint_size", 8)),
            8,
        )

        src_axes_p1 = axis.transAxes.inverted().transform(axis.transData.transform((src_x1, src_y1)))
        src_axes_p2 = axis.transAxes.inverted().transform(axis.transData.transform((src_x2, src_y2)))
        src_left = min(src_axes_p1[0], src_axes_p2[0])
        src_right = max(src_axes_p1[0], src_axes_p2[0])
        src_bottom = min(src_axes_p1[1], src_axes_p2[1])
        src_top = max(src_axes_p1[1], src_axes_p2[1])
        src_center = ((src_left + src_right) / 2.0, (src_bottom + src_top) / 2.0)

        inset_left = ins_pct_x1 / 100.0
        inset_right = ins_pct_x2 / 100.0
        inset_bottom = ins_pct_y1 / 100.0
        inset_top = ins_pct_y2 / 100.0
        inset_center = ((inset_left + inset_right) / 2.0, (inset_bottom + inset_top) / 2.0)

        dx = inset_center[0] - src_center[0]
        dy = inset_center[1] - src_center[1]

        if abs(dx) >= abs(dy):
            if dx >= 0:
                src_points = [(src_x2, src_y1), (src_x2, src_y2)]
                inset_points = [(0, 0), (0, 1)]
            else:
                src_points = [(src_x1, src_y1), (src_x1, src_y2)]
                inset_points = [(1, 0), (1, 1)]
        else:
            if dy >= 0:
                src_points = [(src_x1, src_y2), (src_x2, src_y2)]
                inset_points = [(0, 0), (1, 0)]
            else:
                src_points = [(src_x1, src_y1), (src_x2, src_y1)]
                inset_points = [(0, 1), (1, 1)]

        from matplotlib.lines import Line2D as L2
        from matplotlib.patches import FancyArrowPatch

        def _decorate(kind, pt_figure):
            if kind == "circle":
                fig.add_artist(L2(
                    [pt_figure[0]], [pt_figure[1]],
                    transform=fig.transFigure,
                    marker="o",
                    markersize=circle_size,
                    linestyle="None",
                    markerfacecolor=zoom_box_color,
                    markeredgecolor=zoom_box_color,
                    clip_on=False,
                    zorder=3001,
                ))

        for src_point, inset_point in zip(src_points, inset_points):
            src_display = axis.transData.transform(src_point)
            inset_display = axins.transAxes.transform(inset_point)
            pa = fig.transFigure.inverted().transform(src_display)
            pb = fig.transFigure.inverted().transform(inset_display)
            arrowstyle = "-"
            if conn_start == "arrow" and conn_end == "arrow":
                arrowstyle = "<|-|>"
            elif conn_start == "arrow":
                arrowstyle = "<|-"
            elif conn_end == "arrow":
                arrowstyle = "-|>"

            if arrowstyle == "-":
                fig.add_artist(L2(
                    [pa[0], pb[0]], [pa[1], pb[1]],
                    transform=fig.transFigure,
                    color=zoom_box_color, linewidth=conn_lw,
                    linestyle=_LS_MAP.get(conn_style, conn_style),
                    clip_on=False, zorder=3000,
                ))
            else:
                fig.add_artist(FancyArrowPatch(
                    posA=(pa[0], pa[1]),
                    posB=(pb[0], pb[1]),
                    transform=fig.transFigure,
                    arrowstyle=arrowstyle,
                    mutation_scale=arrow_size,
                    linewidth=conn_lw,
                    linestyle=_LS_MAP.get(conn_style, conn_style),
                    color=zoom_box_color,
                    clip_on=False,
                    zorder=3000,
                ))
            _decorate(conn_start, pa)
            _decorate(conn_end, pb)


def register_extensions(registry) -> None:
    registry.register_plot(
        PlotExtension(
            type="plot_local_zoom",
            name="局部放大",
            handler=draw_local_zoom,
            description="在当前图表中选中一个矩形区域，在嵌入视图中生成放大对照。"
                        "支持坐标/比例两种方式设定原图范围，"
                        "以及全画幅比例设定放大图位置。",
            version=BUILTIN_EXTENSION_VERSION,
            lines_number=None,
            phases=("after_plot",),
            settings=True,
            source_kind="builtin",
            tool_tier="tool",
            config_fields=[
                # ── 原图范围模式 ──
                ExtensionConfigField(
                    key="src_mode",
                    label="原图范围模式",
                    field_type="selective",
                    default="percentage",
                    choices=["percentage", "coordinate"],
                    description="选择使用画幅比例还是数据坐标来设定原图放大区域。",
                ),
                ExtensionConfigField(
                    key="src_x1",
                    label="原图 X 起点",
                    field_type="number",
                    default=25,
                    description="原图放大区域左边界。范围模式为坐标时直接用数值；为百分比时按画幅宽度百分比解释。",
                ),
                ExtensionConfigField(
                    key="src_x2",
                    label="原图 X 终点",
                    field_type="number",
                    default=75,
                    description="原图放大区域右边界。范围模式为坐标时直接用数值；为百分比时按画幅宽度百分比解释。",
                ),
                ExtensionConfigField(
                    key="src_y1",
                    label="原图 Y 起点",
                    field_type="number",
                    default=25,
                    description="原图放大区域下边界。范围模式为坐标时直接用数值；为百分比时按画幅高度百分比解释。",
                ),
                ExtensionConfigField(
                    key="src_y2",
                    label="原图 Y 终点",
                    field_type="number",
                    default=75,
                    description="原图放大区域上边界。范围模式为坐标时直接用数值；为百分比时按画幅高度百分比解释。",
                ),
                # ── 放大图位置 ──
                ExtensionConfigField(
                    key="inset_pct_x1",
                    label="放大图 X 起点 (%)",
                    field_type="number",
                    default=50, min_value=0, max_value=100, step=1,
                    description="放大嵌入视图左边界位置（全画幅百分比）。",
                ),
                ExtensionConfigField(
                    key="inset_pct_x2",
                    label="放大图 X 终点 (%)",
                    field_type="number",
                    default=95, min_value=0, max_value=100, step=1,
                    description="放大嵌入视图右边界位置（全画幅百分比）。",
                ),
                ExtensionConfigField(
                    key="inset_pct_y1",
                    label="放大图 Y 起点 (%)",
                    field_type="number",
                    default=50, min_value=0, max_value=100, step=1,
                    description="放大嵌入视图下边界位置（全画幅百分比）。",
                ),
                ExtensionConfigField(
                    key="inset_pct_y2",
                    label="放大图 Y 终点 (%)",
                    field_type="number",
                    default=95, min_value=0, max_value=100, step=1,
                    description="放大嵌入视图上边界位置（全画幅百分比）。",
                ),
                # ── 放大区域边框 ──
                ExtensionConfigField(
                    key="zoom_box_color",
                    label="区域边框颜色",
                    field_type="color",
                    default="#C23B22",
                    description="原图放大区域矩形框和连接线的颜色。",
                ),
                ExtensionConfigField(
                    key="zoom_box_style",
                    label="区域边框线型",
                    field_type="selective",
                    default="--",
                    choices=["-", "--", "-.", ":", "none"],
                    description="原图放大区域矩形框的线型。选 none 则不显示边框。",
                ),
                ExtensionConfigField(
                    key="box_linewidth",
                    label="边框线宽",
                    field_type="number",
                    default=1.2, min_value=0.1, max_value=5, step=0.1,
                    description="原图放大区域矩形框的线宽。",
                ),
                # ── 连接线（线型）──
                ExtensionConfigField(
                    key="show_connector",
                    label="显示连接线",
                    field_type="boolean",
                    default=True,
                    description="是否在放大区域和嵌入视图之间绘制连接线。",
                ),
                ExtensionConfigField(
                    key="connector_style",
                    label="连接线线型",
                    field_type="selective",
                    default="--",
                    choices=["-", "--", "-.", ":"],
                    description="连接线的线型，与原图区域边框独立设置。",
                ),
                ExtensionConfigField(
                    key="connector_linewidth",
                    label="连接线线宽",
                    field_type="number",
                    default=0.8, min_value=0.1, max_value=5, step=0.1,
                    description="连接线的线宽。",
                ),
                ExtensionConfigField(
                    key="connector_arrow_size",
                    label="箭头大小",
                    field_type="number",
                    default=10, min_value=1, max_value=30, step=1,
                    description="箭头端点的显示大小。",
                ),
                ExtensionConfigField(
                    key="connector_circle_size",
                    label="圆点大小",
                    field_type="number",
                    default=8, min_value=1, max_value=30, step=1,
                    description="圆形端点的显示大小。",
                ),
                # ── 连接线（端点）──
                ExtensionConfigField(
                    key="connector_start",
                    label="起点端点",
                    field_type="selective",
                    default="none",
                    choices=["none", "arrow", "circle"],
                    description="连接线在原图放大区域一端的端点样式。",
                ),
                ExtensionConfigField(
                    key="connector_end",
                    label="终点端点",
                    field_type="selective",
                    default="none",
                    choices=["none", "arrow", "circle"],
                    description="连接线在嵌入放大视图一端的端点样式。",
                ),
            ],
        )
    )
