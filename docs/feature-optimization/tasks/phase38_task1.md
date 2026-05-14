# Phase 38 Task 1: 项目树领域模型与 index 映射抽离

## 目标

先把项目树的节点查询、父子关系、虚拟叶节点和 focus/filter 规则抽成可供 model 消费的领域层。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `ui/widgets/project_tree.py` | 抽离 item 依赖逻辑 |
| `ui/widgets/project_tree_support.py` | 常量与映射复核 |
| `ui/widgets/*` | 如有 helper 依赖 item 对象，先收口接口 |

## 验收清单

- [ ] 数据关系可在不创建 `QTreeWidgetItem` 的前提下访问
- [ ] focus/filter/global assets 规则可被新 model 复用
