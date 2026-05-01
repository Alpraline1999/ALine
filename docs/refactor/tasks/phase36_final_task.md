# Phase 36 最终执行: SaveExportCoordinator 提取与三大页面接入

## 目标

提取 DigitizePage/AnalysisPage/ProcessPage 共享的导出/保存目标解析与协调逻辑。

## 实施

1. 创建 `ui/pages/save_export_coordinator.py`:
   - `ensure_result_folder(folder_name, fallback)` — 共享 find-or-create 模式
   - `SaveExportCoordinator` 类，通过回调注入减少页面耦合
2. 接入 digitize_page.py — 替换 `_ensure_digitize_result_folder`
3. 接入 analysis_page.py — 替换 `_ensure_analysis_result_folder`
4. process_page 的 _save_batch_result 同理
