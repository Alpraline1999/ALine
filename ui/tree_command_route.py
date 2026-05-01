from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class TreeCommandRoute:
    switch_to: Callable[[Any], None]
    current_page: Callable[[], Any]
    refresh_tree: Callable[[], None]
    refresh_templates: Callable[[], None]
    get_node_by_id: Callable[[str], Any | None]
    get_source_file_path: Callable[[str], str]
    open_extension_config_node: Callable[[str], bool]
    data_page: Any
    digitize_page: Any
    chart_page: Any
    process_page: Any
    analysis_page: Any

    def dispatch_selected(self, kind: str, node_id: str) -> None:
        self._handle_selected(kind, node_id)

    def dispatch_activated(self, kind: str, node_id: str) -> None:
        self._handle_activated(kind, node_id)

    def dispatch_send_to_visualize(self, data_type: str, obj_id: str) -> None:
        """发送数据到可视化页。"""
        self.switch_to(self.chart_page)
        if data_type == "picture" and hasattr(self.chart_page, "on_tree_node_activated"):
            self.chart_page.on_tree_node_activated("picture", obj_id)
            return
        if hasattr(self.chart_page, 'receive_data'):
            self.chart_page.receive_data(data_type, obj_id)

    def dispatch_send_to_process(self, data_type: str, obj_id: str) -> None:
        """发送数据到处理页。"""
        self.switch_to(self.process_page)
        if hasattr(self.process_page, 'receive_data'):
            self.process_page.receive_data(data_type, obj_id)

    def _dispatch_activation_to_current_page(self, kind: str, node_id: str) -> bool:
        page = self.current_page()
        if kind == "data_file" and page is not self.process_page:
            return False
        if page is self.digitize_page and kind == "image_work":
            if hasattr(self.digitize_page, "load_image_by_id"):
                self.digitize_page.load_image_by_id(node_id)
                return True
            return False
        if hasattr(page, "on_tree_node_activated"):
            page.on_tree_node_activated(kind, node_id)
            return True
        if hasattr(page, "on_tree_node_selected"):
            page.on_tree_node_selected(kind, node_id)
            return True
        return False

    def _handle_selected(self, kind: str, node_id: str) -> None:
        if kind == "project":
            self.refresh_tree()
            self.refresh_templates()
            return
        page = self.current_page()
        if hasattr(page, "on_tree_node_selected"):
            page.on_tree_node_selected(kind, node_id)

    def _handle_activated(self, kind: str, node_id: str) -> None:
        if kind == "project":
            self.refresh_tree()
            self.refresh_templates()
            return
        if kind == "image_work":
            self.switch_to(self.digitize_page)
            if hasattr(self.digitize_page, "load_image_by_id"):
                self.digitize_page.load_image_by_id(node_id)
            return
        if kind == "image_work_add_curve":
            self.switch_to(self.digitize_page)
            if hasattr(self.digitize_page, "load_image_by_id"):
                self.digitize_page.load_image_by_id(node_id)
            if hasattr(self.digitize_page, "add_curve_from_shell"):
                self.digitize_page.add_curve_from_shell()
            return
        if kind == "curve_export_to_data_file":
            self.switch_to(self.digitize_page)
            if hasattr(self.digitize_page, "load_curve_by_id"):
                self.digitize_page.load_curve_by_id(node_id)
            if hasattr(self.digitize_page, "export_current_curve_to_data_file"):
                self.digitize_page.export_current_curve_to_data_file()
            return
        if kind in ("data_file", "series", "curve") and self._dispatch_activation_to_current_page(kind, node_id):
            return
        if kind in ("source_file", "source_file_to_data"):
            self.switch_to(self.data_page)
            self.data_page.on_tree_node_selected("source_file", node_id)
            if kind == "source_file_to_data" and hasattr(self.data_page, "import_current_source_file_to_dataset"):
                self.data_page.import_current_source_file_to_dataset()
            return
        if kind == "source_file_to_digitize":
            source_node = self.get_node_by_id(node_id)
            source_path = ""
            source_name = ""
            if source_node is not None and getattr(source_node, "kind", None) == "source_file":
                source_path = self.get_source_file_path(getattr(source_node, "source_file_id", ""))
                source_name = getattr(source_node, "name", "")
            if source_path:
                self.switch_to(self.digitize_page)
                if hasattr(self.digitize_page, "import_source_image"):
                    self.digitize_page.import_source_image(source_path, name=source_name)
            return
        if kind in ("pipeline", "global_pipeline"):
            if hasattr(self.process_page, "load_pipeline"):
                self.process_page.load_pipeline(node_id)
            self.switch_to(self.process_page)
            return
        if kind in ("global_figure_template", "figure_template"):
            if hasattr(self.chart_page, "load_template"):
                self.chart_page.load_template(node_id)
            self.switch_to(self.chart_page)
            return
        if kind in ("global_curve_style_template",):
            self.switch_to(self.chart_page)
            if hasattr(self.chart_page, "load_curve_style_template"):
                self.chart_page.load_curve_style_template(node_id)
            return
        if kind in ("global_plot_style", "global_plot_theme"):
            self.switch_to(self.chart_page)
            if hasattr(self.chart_page, "load_plot_style"):
                self.chart_page.load_plot_style(node_id)
            return
        if kind in ("global_report_template", "report_template"):
            self.switch_to(self.analysis_page)
            if hasattr(self.analysis_page, "load_report_template"):
                self.analysis_page.load_report_template(node_id)
            return
        if kind == "global_extension_config":
            self.open_extension_config_node(node_id)
            return
        if kind == "analysis_result":
            self.switch_to(self.analysis_page)
            if hasattr(self.analysis_page, "load_analysis_result"):
                self.analysis_page.load_analysis_result(node_id)
            return
        if kind in ("data_file_to_chart", "image_work_to_chart", "series_to_chart", "curve_to_chart", "picture_to_chart", "picture"):
            self.switch_to(self.chart_page)
            if hasattr(self.chart_page, "on_tree_node_activated"):
                self.chart_page.on_tree_node_activated(kind, node_id)
            return
        if kind in ("data_file_to_process", "series_to_process", "curve_to_process"):
            self.switch_to(self.process_page)
            if hasattr(self.process_page, "on_tree_node_activated"):
                self.process_page.on_tree_node_activated(kind, node_id)
            return
        if kind in ("data_file_to_analysis", "series_to_analysis", "curve_to_analysis"):
            self.switch_to(self.analysis_page)
            if hasattr(self.analysis_page, "on_tree_node_activated"):
                self.analysis_page.on_tree_node_activated(kind, node_id)
