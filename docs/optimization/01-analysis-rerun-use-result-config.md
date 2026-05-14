# 优化 01：分析页"复跑此配置"应使用结果配置而非面板配置

## 问题描述

分析页的"复跑此配置"按钮在点击后，实际使用的扩展参数来自**设置面板当前显示的文本**，
而非该分析结果**保存时的配置**。当用户在查看某个旧结果时切换过设置页面的参数再点击复跑，
实际运行的是切换后的参数，而不是该结果原本的参数。

## 当前调用链

```
_rerun_current_analysis()
  ├─ _current_analysis_view()          → 获取当前显示的 result view
  ├─ _sync_state_from_analysis_view()  → 恢复 inputs + params 到 UI 面板
  │   └─ _restore_analysis_params()    → 设置 self._analysis_extension_options
  │       └─ _extension_panel.set_entries() → 更新面板 UI
  │                                           ← 但可能未更新文本编辑器的内容
  └─ _run_analysis()
      └─ _current_extension_analysis_options()
          └─ _parse_extension_analysis_options_text()
              └─ self._extension_params_edit.current_options()
                  ← 从 UI 文本编辑器读取！可能读取到的是未更新的陈旧内容
```

## 根因

`_parse_extension_analysis_options_text()` (L1047) 调用 `self._extension_params_edit.current_options()`
从 UI 文本编辑器读取参数，而不是从已恢复的 `self._analysis_extension_options[type_id]` 读取。
即使 `_restore_analysis_params()` 正确设置了 `_analysis_extension_options`，
文本编辑器的内容可能未被刷新，导致使用当前面板文本。

## 方案

修改 `_rerun_current_analysis()`，跳过 UI 文本编辑器读取路径：
直接从 `view.get("params")` 中的 `extension_options` 获取已保存参数，
并直接传递给 `_run_analysis()`，绕开 `_current_extension_analysis_options` 的 UI 读取路径。

## 验收

- 某个分析结果保存后、切换到其他设置再点击"复跑此配置"，应当使用该结果保存时的参数
- 普通"运行分析"不受影响（仍从面板读取）
