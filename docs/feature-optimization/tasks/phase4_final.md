# Phase 4 Final: Extension 元数据 UI 消费层

## 目标

把扩展协议新增的兼容性/能力/authority 元数据真正暴露到 UI 消费层，而不是只停留在 core helper 中。

## 实施

1. `core/extension_api.py`
   - 保留新增元数据摘要输出
   - 统一生成可展示的兼容性/能力/authority 标签
2. `ui/widgets/extension_panel.py`
   - 显示兼容性/能力/authority 标签
   - 让 help-only / full 模式都能看到这些标签
3. `ui/pages/data_page.py`
   - 在扩展预览说明中补充元数据摘要
