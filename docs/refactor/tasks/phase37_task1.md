# Phase 37 Task 1: 结构闭环清单与功能优化入口条件

## 检查清单

### 大文件预算
- [x] core/project_manager.py — 已多次 service 拆分，无大型 monolith
- [x] ui/pages/data_page.py — 已拆分 preview/pending_import support 模块
- [x] ui/widgets/project_tree.py — 已拆分 delegate/menu/drag-drop
- [x] ai/command_layer.py — 已消除重复定义，导入 registry
- [ ] ui/pages/digitize_page.py (3598 行) — 仍偏大，后续功能优化前建议拆分
- [ ] ui/pages/analysis_page.py (2896 行) — 仍偏大
- [ ] ui/pages/settings_page.py (1715 行) — 仍偏大

### 私有 API 泄漏检查
- [x] ui/app 目录无 `project_manager._*` 跨模块访问 (Phase 34)

### 重复命令面检查
- [x] command_layer / command_registry 去重完成 (Phase 35)

### 页面壳层职责检查
- [x] ProjectTreeWidget 已清晰分为 view / menu / drag-drop 层
- [x] MainWindow 树路由已转交 TreeCommandRoute
- [x] DataPage 已有 preview / pending_import support 模块

### 超大测试文件
- [ ] tests/test_ui.py — 需确认拆分计划

### UI 一致性
- [x] 导出/保存计划模型已提取为共享模块 (Phase 36)
