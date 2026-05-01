# Phase 35 Task 1: AI 命令面收口 — registry-first

## 问题

command_layer.py 和 command_registry.py 存在完全重复的类/函数定义：
- `CommandResult`, `CommandDef` 在两个文件中各有一份
- `cmd_get_project_summary`, `cmd_list_data_files` 等 20+ 函数完全重复

## 解决方案

1. `command_registry.py` 保持为唯一命令定义源
2. `command_layer.py` 删除自身定义的 `CommandResult`/`CommandDef`/`cmd_*`，改为从 `command_registry` 导入
3. 保留 `command_layer.py` 中的 `CommandDispatcher` 和 `_dynamic_*` 方法
