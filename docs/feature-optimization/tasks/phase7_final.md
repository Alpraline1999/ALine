# Phase 7 Final: GlobalAssets 导入/导出 + 默认值

## 目标

把全局资产的导入/导出和默认值操作收口到统一入口，减少页面间重复逻辑。

## 实施

1. `core/global_assets.py`
   - 提供全局资产 JSON 导入/导出
   - 提供扩展配置默认值切换辅助
2. `ui/widgets/project_tree_menu_commands.py`
   - 扩展配置菜单增加“导出”“设为默认”
