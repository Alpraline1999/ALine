# Phase 2 Task 1: 样式优先级契约 — advisory/authoritative patch

## 目标

1. 为扩展 patch 增加 authority 元数据: `advisory`（建议）/ `authoritative`（强制）
2. 修改 `_effective_*` 合并函数: advisory patch 不覆盖手动修改的字段
3. 用户手动修改的字段保持最终决定权，除非扩展声明 authoritative

## 修改范围

- `core/extension_types.py` — patch authority 类型定义
- `ui/pages/chart_page.py` — `_effective_*` 合并函数加入 authority 判断
