# Phase 7 Task 1: GlobalAssets 资产操作增强

## 目标

补齐全局资产的复制、重命名、导出操作，提升资产工作流。

## 实施

1. `core/global_assets.py` 添加:
   - `duplicate_pipeline(pipeline_id, new_name)` — 复制 pipeline
   - `duplicate_figure_template(template_id, new_name)` — 复制 figure template
   - `duplicate_extension_config(config_id)` — 复制扩展配置
2. 项目树右键菜单接入复制操作
