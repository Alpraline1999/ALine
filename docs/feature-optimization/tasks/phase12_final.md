# Phase 12 Final: 首页最近项目空状态布局模式收口

## 目标

让首页在“最近项目为空”时保持顶部紧凑布局，并把空/非空两种布局模式收口到单一 helper。

## 实施

1. `ui/pages/home_page.py`
   - 新增 `_set_recent_section_mode(has_recent: bool)` 统一控制空/非空状态切换
   - 刷新时由 helper 同时管理最近项目区显隐、滚动区 sizePolicy 和 stretch
   - 初始化阶段只搭建结构，不再在多个位置硬编码布局切换
2. `tests/pages/test_home_page.py`
   - 补充空状态窄测
   - 将非空状态测试改为确定性 mock，验证最近项目区仍保持滚动扩展

## 验证

- `./.venv/bin/python -m pytest tests/pages/test_home_page.py -q -k 'recent_scroll_expands_to_fill_remaining_height or recent_section_uses_compact_layout_when_empty'`

## 后续

- 首页 banner、入口按钮和最近项目卡片样式仍保持当前边界，不纳入本阶段。

