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

## 验证

- `python3 -m py_compile ui/dialogs/project_close_dialog.py ui/main_window.py ui/widgets/project_tree.py ui/pages/digitize_page.py tests/test_ui.py`
- 目标 UI 用例尝试运行时，当前环境缺少 `PySide6`，因此无法在这里完成 Qt 级联测试。

## 后续

- 在具备完整 Qt 依赖的环境中复跑 phase18 的窄范围 UI 测试。
- 若后续发现还有其他项目关闭入口，再统一接入同一三态契约，不再各自拼装二元确认框。

