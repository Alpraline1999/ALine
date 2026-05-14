# Phase 34 Task 1: 节点备注字段与持久化

## 目标

为主要节点类型引入 `remark` 字段，并确保保存/加载兼容。

## 涉及文件

| 文件 | 操作 |
|---|---|
| `models/schemas.py` | 节点模型增加 remark |
| `core/project_serializer.py` / `core/zip_serializer.py` | 持久化链路复核 |
| `core/project_manager.py` | 备注读写 façade |

## 验收清单

- [ ] remark 可保存、加载、复制
- [ ] 未设置 remark 的旧项目兼容
