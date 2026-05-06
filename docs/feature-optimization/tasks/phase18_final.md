# Phase 18 Final: 关闭确认三态契约收口

## 目标

确认未保存项目关闭流程已补齐 `保存 / 不保存 / 取消` 三态，并且项目树、主窗口、数字化页共用同一确认契约。

## 已完成

1. 新增共享关闭确认对话框
   - `ui/dialogs/project_close_dialog.py`
   - 对外返回 `ProjectCloseDecision`
2. 收口项目关闭入口
   - `ui/main_window.py`
   - `ui/widgets/project_tree.py`
   - `ui/pages/digitize_page.py`
3. 补齐窄范围测试
   - 项目树取消关闭
   - 主窗口取消关闭与保存后关闭
   - 数字化页取消关闭
4. 收口弹窗底部布局
   - 关闭确认按钮移回 `MessageBoxBase` 底部按钮区
   - 消除弹窗下半部分白边

## 验证

- `python3 -m py_compile ui/dialogs/project_close_dialog.py ui/main_window.py ui/widgets/project_tree.py ui/pages/digitize_page.py tests/test_ui.py`
- `.venv/bin/python -m py_compile ui/dialogs/project_close_dialog.py ui/main_window.py ui/widgets/project_tree.py ui/pages/digitize_page.py tests/test_ui.py`
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_ui.TestProjectTreeWidget.test_unsaved_close_dialog_uses_bottom_button_group tests.test_ui.TestProjectTreeWidget.test_close_current_project_cancel_keeps_project_open tests.test_ui.TestDigitizePage.test_close_project_cancel_keeps_current_project tests.test_ui.TestMainWindow.test_close_current_project_cancel_keeps_project_open tests.test_ui.TestMainWindow.test_close_current_project_save_then_closes`
- 目标 UI 用例尝试运行时，当前环境缺少 `PySide6`，因此无法在这里完成 Qt 级联测试。
- 使用仓库内 `.venv` 后，已完成窄范围 Qt 测试并通过。

## 后续

- 在具备完整 Qt 依赖的环境中复跑 phase18 的窄范围 UI 测试。
- 若后续发现还有其他项目关闭入口，再统一接入同一三态契约，不再各自拼装二元确认框。
