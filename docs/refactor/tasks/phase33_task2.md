# Phase 33 Task 2: DataPage source manager/preview/pending import 切分

## 背景

`DataPage` (4944 行) 仍混合了：
- Source browser (left panel, manage panel, source favorites)
- Preview (plot preview, image preview, text preview, parsed preview table)
- Pending import queue management
- Global asset preview (extension config, plot style 预览)
- 布局构建 (`_build_left_panel`, `_build_manage_panel`, `_build_right_panel`)

已有 extracted modules:
- `data_page_support.py` — 常量和 helper
- `data_page_state_bridge.py` — 状态桥接

## 本次提取目标

1. **Preview presenter**: 将预览相关逻辑提取为独立 presenter
   - 预览绘制 (`_draw_preview`, `_clear_preview`)
   - 预览模式切换 (`_set_preview_plot_type`, `_set_preview_source_file_mode`)
   - 预览控件显隐 (`_set_preview_plot_type_controls_visible`, etc.)
   - 预览样式 (`_apply_preview_host_background`)
2. **Pending import coordinator**: 将导入队列管理提取为独立 coordinator
   - `_pending_import_states`, `_import_file`, `_queue_import`, `_process_import_queue`
   - 导入进度 UI 更新
3. **Global asset preview support**: 将全局资产预览提取
   - Extension config 预览
   - Plot style 预览
   - 预览工具栏管理
4. **DataPage 瘦身**: 保留页面壳层只做布局、状态桥接和高层命令接线

## 验收标准

- DataPage 新增修复不再需要同时触碰 preview、browser、resource 管理多个无关区域
- Preview 修改可在独立 presenter 模块中完成
- Pending import 逻辑可在独立 coordinator 模块中完成
