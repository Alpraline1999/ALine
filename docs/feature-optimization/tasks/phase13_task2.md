# Phase 13 Task 2: 项目树对话框适配层 API 收口

## 目标

修复 `ProjectTreeWidget` 对话框适配层对 `SelectionDialog` / `TextInputDialog` 的旧 API 调用，避免“移动到...”“新建”“重命名”路径继续因适配层漂移报错。

## 实施

1. 统一项目树选择对话框调用
   - `SelectionDialog` 统一走当前 `get_item()` / `value()` API
   - 不再调用不存在的 `get_selected_item()`
2. 统一项目树文本输入对话框调用
   - `TextInputDialog` 统一走当前 `get_text()` / `value()` API
   - 不再读取不存在的 `lineEdit`
3. 补充窄测试
   - 覆盖“移动到...”路径的选择对话框适配
   - 覆盖新建/重命名路径的文本输入适配
4. 保持 phase13 边界
   - 仅修正适配层和最小守护，不扩展 UI 行为

