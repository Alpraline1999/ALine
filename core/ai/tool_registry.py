TOOLS = {
    "list_tree_nodes": {"label": "列出项目树节点", "description": "列出当前项目树中的主要节点"},
    "get_node_detail": {"label": "读取当前节点详情", "description": "读取当前共享树节点的详细信息"},
    "list_data_files": {"label": "列出数据文件", "description": "列出项目内全部数据文件"},
    "read_chart_config": {"label": "读取当前图表配置", "description": "读取可视化页当前 FigureState"},
    "save_pipeline_template": {"label": "保存当前 Pipeline 模板", "description": "把当前处理链保存为模板"},
    "render_report_template": {"label": "渲染当前报告模板", "description": "用当前分析结果渲染报告模板"},
    "export_curve_to_data_file": {"label": "将取点结果导出为数据列", "description": "把当前取点曲线写入项目数据文件"},
}


def list_registered_tools() -> dict:
    return dict(TOOLS)