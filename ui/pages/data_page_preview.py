"""
DataPage 预览渲染辅助 — 封装绘图、图像、文本、解析预览的绘制逻辑。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Optional

from PySide6.QtGui import QPixmap
from qfluentwidgets import isDarkTheme

from ui.pages.data_page_support import (
    _SOURCE_IMAGE_SUFFIXES,
    _TEXT_PREVIEW_SUFFIXES,
    _TABULAR_PREVIEW_SUFFIXES,
)


class DataPagePreviewPresenter:
    """DataPage 预览渲染 presenter。

    通过回调/引用注入访问 DataPage 的状态与控件。
    不持有 DataPage 引用，只与显式注入的依赖交互。
    """

    def __init__(
        self,
        *,
        # 状态 getter/setter
        get_preview_xs,
        set_preview_xs,
        get_preview_ys,
        set_preview_ys,
        get_preview_name,
        set_preview_name,
        get_preview_x_label,
        set_preview_x_label,
        get_preview_y_label,
        set_preview_y_label,
        get_preview_image_path,
        set_preview_image_path,
        get_data_file_preview_node_id,
        set_data_file_preview_node_id,
        # 控件引用
        preview_figure,
        preview_canvas,
        preview_stack,
        plot_preview_panel,
        image_preview_label,
        text_preview,
        parsed_preview_table,
        picture_preview_tree,
        preview_type_combo,
        # UI 控制方法
        show_preview_mode,
        set_preview_plot_type_controls_visible,
        set_source_file_preview_mode_controls_visible,
        set_source_file_detail_controls_visible,
        set_source_file_sheet_controls_visible,
        set_source_file_skip_rows_enabled,
        set_preview_summary,
        set_preview_footer_visible,
        set_extension_config_editor_mode,
        hide_source_path_links,
        show_source_path_links,
        apply_preview_host_background,
        update_preview_image_from_path,
        sync_preview_nav_toggle_states,
        # 工具方法
        preview_bar_width,
        show_text_preview,
        show_paginated_text_source_preview,
    ):
        self._get_xs = get_preview_xs
        self._set_xs = set_preview_xs
        self._get_ys = get_preview_ys
        self._set_ys = set_preview_ys
        self._get_name = get_preview_name
        self._set_name = set_preview_name
        self._get_x_label = get_preview_x_label
        self._set_x_label = set_preview_x_label
        self._get_y_label = get_preview_y_label
        self._set_y_label = set_preview_y_label
        self._get_image_path = get_preview_image_path
        self._set_image_path = set_preview_image_path
        self._get_df_preview_node_id = get_data_file_preview_node_id
        self._set_df_preview_node_id = set_data_file_preview_node_id
        self._figure = preview_figure
        self._canvas = preview_canvas
        self._preview_stack = preview_stack
        self._plot_panel = plot_preview_panel
        self._image_label = image_preview_label
        self._text_preview = text_preview
        self._parsed_table = parsed_preview_table
        self._picture_tree = picture_preview_tree
        self._type_combo = preview_type_combo
        self._show_preview_mode = show_preview_mode
        self._set_plot_controls = set_preview_plot_type_controls_visible
        self._set_source_preview_controls = set_source_file_preview_mode_controls_visible
        self._set_source_detail_controls = set_source_file_detail_controls_visible
        self._set_source_sheet_controls = set_source_file_sheet_controls_visible
        self._set_skip_rows = set_source_file_skip_rows_enabled
        self._set_summary = set_preview_summary
        self._set_footer_visible = set_preview_footer_visible
        self._set_ext_editor = set_extension_config_editor_mode
        self._hide_path_links = hide_source_path_links
        self._show_path_links = show_source_path_links
        self._apply_bg = apply_preview_host_background
        self._update_image = update_preview_image_from_path
        self._sync_nav = sync_preview_nav_toggle_states
        self._bar_width = preview_bar_width
        self._show_text = show_text_preview
        self._show_paginated = show_paginated_text_source_preview

    # ── 清除 ──────────────────────────────────────────────────

    def clear_preview(self) -> None:
        """重置所有预览状态。"""
        self._set_ext_editor(False)
        self._show_preview_mode()
        self._set_xs([])
        self._set_ys([])
        self._set_name("")
        self._set_x_label("X")
        self._set_y_label("Y")
        self._set_df_preview_node_id(None)
        self._set_image_path(None)
        self._preview_stack.setCurrentWidget(self._plot_panel)
        self.draw_preview()
        self._text_preview.clear()
        self._parsed_table.clear()
        self._parsed_table.setRowCount(0)
        self._parsed_table.setColumnCount(0)
        self._picture_tree.clear()
        self._image_label.clear()
        self._image_label.setText("选择节点后显示预览")
        self._set_summary(["（选择数据后显示统计信息）"])
        self._set_footer_visible(True)
        self._set_source_preview_controls(False)
        self._set_source_detail_controls(False)
        self._set_skip_rows(True)
        self._set_source_sheet_controls(False)

    # ── 绘图预览 ──────────────────────────────────────────────

    def draw_preview(self) -> None:
        """绘制 matplotlib 预览图。"""
        if self._figure is None or self._canvas is None:
            return
        self._preview_stack.setCurrentWidget(self._plot_panel)
        self._apply_bg()
        self._figure.clear()
        axis = self._figure.add_subplot(111)
        dark = isDarkTheme()
        bg = "#1e1e1e" if dark else "#ffffff"
        fg = "#cccccc" if dark else "#222222"
        gc = "#444444" if dark else "#dddddd"
        self._figure.patch.set_facecolor(bg)
        axis.set_facecolor(bg)
        axis.tick_params(colors=fg, labelcolor=fg)
        for spine in axis.spines.values():
            spine.set_edgecolor(fg)
        xs = self._get_xs()
        ys = self._get_ys()
        if not xs or not ys:
            axis.text(0.5, 0.5, "选择数据后显示绘图预览", ha="center", va="center", color=fg, transform=axis.transAxes)
            axis.set_axis_off()
            self._canvas.draw()
            return

        plot_type = self._type_combo.currentText()
        if plot_type == "散点":
            axis.scatter(xs, ys, s=22, color="#0078D4")
        elif plot_type == "折线+点":
            axis.plot(xs, ys, marker="o", linewidth=1.5, markersize=4.2, color="#0078D4")
        elif plot_type == "柱状":
            axis.bar(xs, ys, width=self._bar_width(xs), color="#0078D4", alpha=0.85)
        elif plot_type == "阶梯":
            axis.step(xs, ys, where="mid", linewidth=1.5, color="#0078D4")
        else:
            axis.plot(xs, ys, linewidth=1.8, color="#0078D4")

        axis.set_title(self._get_name() or "数据预览", color=fg)
        axis.set_xlabel(self._get_x_label() or "X", color=fg)
        axis.set_ylabel(self._get_y_label() or "Y", color=fg)
        axis.grid(True, color=gc, alpha=0.35)
        self._figure.tight_layout()
        self._canvas.draw()
        self._sync_nav()

    def show_xy_preview(self, xs, ys, name: str, x_label: str = "X", y_label: str = "Y") -> None:
        """填充绘图预览和统计摘要。"""
        self._set_ext_editor(False)
        self._show_preview_mode()
        self._set_image_path(None)
        self._set_source_preview_controls(False)
        self._set_source_detail_controls(False)
        self._set_plot_controls(True)
        self._hide_path_links()
        n = min(len(xs), len(ys))
        self._set_xs([float(v) for v in xs[:n]])
        self._set_ys([float(v) for v in ys[:n]])
        self._set_name(name)
        self._set_x_label(x_label or "X")
        self._set_y_label(y_label or "Y")
        self.draw_preview()
        if n > 0:
            x_min, x_max = min(xs[:n]), max(xs[:n])
            y_min, y_max = min(ys[:n]), max(ys[:n])
            y_mean = sum(ys[:n]) / n
            y_var = sum((v - y_mean)**2 for v in ys[:n]) / n
            y_std = math.sqrt(y_var)
            self._set_summary([
                name or "数据预览",
                f"N = {n}",
                f"X: [{x_min:.4g}, {x_max:.4g}]",
                f"Y: [{y_min:.4g}, {y_max:.4g}]",
                f"均值 = {y_mean:.4g}",
                f"标准差 = {y_std:.4g}",
            ])
        else:
            self._set_summary([name or "数据预览", "(无数据点)"])

    def show_text_preview(self, title: str, content: str, stats_text: str | list[str], *, show_source_file_controls: bool = False) -> None:
        """显示纯文本预览。"""
        self._show_preview_mode()
        self._set_image_path(None)
        self._set_source_preview_controls(show_source_file_controls)
        self._set_source_detail_controls(False)
        self._set_source_sheet_controls(False)
        self._set_plot_controls(False)
        self._hide_path_links()
        self._preview_stack.setCurrentWidget(self._text_preview)
        self._text_preview.setPlainText(content)
        if isinstance(stats_text, list):
            self._set_summary(stats_text)
        else:
            self._set_summary([stats_text])

    # ── 文件预览 ──────────────────────────────────────────────

    def show_file_preview_from_path(
        self,
        file_path: str,
        title: str,
        stats_lines: list[str],
        *,
        origin_path: str = "",
        show_path_links: bool = False,
        show_source_file_controls: bool = False,
    ) -> bool:
        """根据文件后缀显示对应的预览内容。"""
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix in _SOURCE_IMAGE_SUFFIXES:
            self._show_preview_mode()
            self._set_source_preview_controls(show_source_file_controls)
            self._set_source_detail_controls(False)
            self._set_source_sheet_controls(False)
            self._set_plot_controls(False)
            self._hide_path_links()
            self._preview_stack.setCurrentWidget(self._image_label)
            if not self._update_image(str(path)):
                self._show_text(title, f"无法加载图片预览。\n\n{file_path}", "\n".join(stats_lines), show_source_file_controls=show_source_file_controls)
                if show_path_links:
                    self._show_path_links(str(path), origin_path)
                return True
            self._set_summary(stats_lines)
            if show_path_links:
                self._show_path_links(str(path), origin_path)
            return True

        if suffix in _TEXT_PREVIEW_SUFFIXES:
            return self._show_paginated(str(path), title, stats_lines, origin_path=origin_path, show_source_file_controls=show_source_file_controls)

        preview_lines = [f"文件名: {title}"]
        if suffix in _TABULAR_PREVIEW_SUFFIXES:
            preview_lines.append("该文件类型暂不提供内联全文预览，但支持作为数据文件导入。")
        else:
            preview_lines.append("该文件类型暂不提供内联预览，可继续使用导入或导出动作。")
        preview_lines.append("")
        preview_lines.extend(stats_lines)
        self._show_text(title, "\n".join(preview_lines), "\n".join(stats_lines), show_source_file_controls=show_source_file_controls)
        self._set_source_sheet_controls(False)
        if show_path_links:
            self._show_path_links(str(path), origin_path)
        return True

    def show_image_preview(self, image_id: str, image_name: str, project_manager_get_image, project_manager_get_image_path) -> bool:
        """显示数字化图像预览。"""
        self._set_ext_editor(False)
        self._show_preview_mode()
        self._set_image_path(None)
        self._set_source_preview_controls(False)
        self._set_source_detail_controls(False)
        self._set_plot_controls(False)
        self._hide_path_links()
        image = project_manager_get_image(image_id)
        if image is None:
            return False
        image_path = project_manager_get_image_path(image_id)
        self._preview_stack.setCurrentWidget(self._image_label)
        if not self._update_image(image_path):
            self._image_label.setPixmap(QPixmap())
            self._image_label.setText(f"无法加载图片预览\n\n{image_path or '未找到图片路径'}")
            stats_text = f"图像名称: {image_name}\n曲线数量: {len(image.curves)}"
        else:
            pixmap = QPixmap(image_path)
            stats_text = (
                f"图像名称: {image_name}\n"
                f"尺寸: {pixmap.width()} × {pixmap.height()} px\n"
                f"曲线数量: {len(image.curves)}"
            )
        self._set_name(image_name)
        self._set_xs([])
        self._set_ys([])
        self._set_summary([stats_text])
        return True
