# Phase 10 Final: 静态未定义名称守护栏 + 关键 UI 烟测

## 目标

把重构后最容易演化为运行时崩溃的 `NameError` / 旧符号残留 / 回调注入遗漏收口为轻量守护栏。

## 实施

1. `scripts/structure_check.py`
   - 增加 `ruff F821` 未定义名称检查
   - 增加 `MainWindow` / `SettingsPage` / `ProjectTreeWidget` 的 `offscreen` 烟测
   - 为硬失败检查返回非零退出码
2. 新增 `tests/test_phase10_guardrails.py`
   - 覆盖 `_safe_filename()` 路径整理
   - 覆盖 `SettingsPage` 扩展目录卡片装配
   - 覆盖扩展配置导出 / 设为默认行为
   - 覆盖项目树全局扩展配置菜单的 `pos` 传递与回调注入
3. 扩展 `tests/test_ui_smoke.py`
   - 补充 `SettingsPage` / `ProjectTreeWidget` 构造烟测

## 验证

- `./.venv/bin/python -m pytest tests/test_phase10_guardrails.py tests/test_ui_smoke.py tests/test_settings_page_refresh.py -q`
- `./.venv/bin/python scripts/structure_check.py`
