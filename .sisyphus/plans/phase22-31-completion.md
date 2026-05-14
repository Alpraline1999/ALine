# Phase 22-31 Completion Plan

## Priority Order (dependencies first)

### P0 - Phase 31: Fix 9 failing backend tests (blocker)
**Files:** tests/test_backend.py
- TestCommandLayerV3: setUp() doesn't patch `ai.command_registry.project_manager` (Phase 35 moved commands to command_registry). Add `cr_module.project_manager = self.pm`.
- test_invoke_plot_extension_handler_respects_plot_phases: handler signature is `(lines, params)` but runtime calls `handler(context, params)`. Change to `(context, params)`.

### P1 - Phase 25: Add missing dialog exports
**Files:** ui/dialogs/__init__.py
- Add exports for: export_flow (choose_data_export_plan etc.), export_models (DataExportPlan etc.), plot_extension_instance_dialog (PlotExtensionInstanceEditDialog)

### P1 - Phase 28: Add isVisible guards on QTimer targets
**Files:** ui/pages/settings_page.py
- Add `isVisible()` / `isWidgetType()` guards in `_refresh_extension_category_tab_heights()` and `_update_colors()` delayed refresh path
- Extract duplicate "SmoothScrollArea { background: transparent; }" strings to a helper

### P1 - Phase 24/30: Deduplicate interpolation in smoother.py
**Files:** processing/smoother.py, core/line_tools.py
- Make processing/smoother.py import resample_uniform, resample_uniform_spacing from core.line_tools

### P1 - Phase 24: Add multiline perf guardrail tests
**Files:** tests/test_multi_curve_mean.py
- Add wall-clock timing assertion for multi_curve_mean with N≥50 curves

### P1 - Phase 27: Add theme benchmark + delegate smoke test
**Files:** tests/test_ui.py
- Add theme switch timing test wrapping MainWindow._update_all_pages_theme()
- Add ProjectTreeWrapAnywhereDelegate paint smoke test

### P1 - Phase 24: Copy budget hardening
**Files:** processing/data_engine.py
- Move deepcopy from per-loop (lines 166-167) to pool creation (line 97)

### P2 - Phase 29: SettingsPage tab extraction
**Files:** ui/pages/settings_page_support.py, ui/pages/settings_page.py
- Extract general/extensions/shortcuts/AI tab builders to settings_page_support.py

### P2 - Phase 27: Theme performance benchmark test
**Files:** tests/test_ui.py (add new test)

### P3 - Phase 22: Create profiling fixtures
**Files:** tests/test_profiling.py, scripts/profiling/
- Create LargeCurveProfileFixture and basic perf baseline

### P3 - Phase 22: StreamingExportPlan
**Files:** core/exporter.py
- Add StreamingExportPlan dataclass and streaming export method

### P3 - Phase 22: PipelineCopyBudget
**Files:** processing/data_engine.py
- Add PipelineCopyBudget dataclass to track/cap copy count

### P3 - Phase 26: Normalize page target resolution
**Files:** app/workspaces/*.py, ui/pages/*.py
