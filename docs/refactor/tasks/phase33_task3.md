# Phase 33 Task 3: MainWindow 树路由收口与窄测验收

## 背景

`MainWindow` (744 行) 仍保留较多树节点激活与页面转发细节：
- `_dispatch_tree_node_selected`, `_dispatch_tree_node_activated`
- `_on_tree_node_selected`, `_on_tree_node_activated`
- `_handle_tree_app_command`, `_on_tree_node_selected_command`
- `_open_extension_config_node`, `_on_send_to_visualize`, `_on_send_to_process`

这些方法本质上是树节点事件的页面路由分发，不应集中在 MainWindow 中。

## 本次提取目标

1. **Tree routing support**: 将树节点路由逻辑提取为独立 support 模块
   - `_dispatch_tree_node_selected`, `_dispatch_tree_node_activated`
   - `_on_tree_node_selected`, `_on_tree_node_activated`
   - `_handle_tree_app_command`, `_on_tree_node_selected_command`
   - `_open_extension_config_node`, `_on_send_to_visualize`, `_on_send_to_process`
2. **MainWindow 瘦身**: 处理后 MainWindow 只保留顶层页面编排和项目生命周期
3. **窄测验证**: 页面切换、树节点选中/激活基本流验证

## 验收标准

- MainWindow 不再是树节点语义解释的默认落点
- 页面路由可在独立 support 模块中完成
- 现有页面切换和树节点交互不受影响
