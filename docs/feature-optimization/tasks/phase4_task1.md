# Phase 4 Task 1: 扩展协议元数据补全

## 目标

在保留现有四类扩展体系的前提下，补齐协议元数据：
1. API 兼容版本声明
2. capability 声明（supports_progress, supports_cancel 等）
3. authority 声明（plot 扩展的样式接管策略）

## 修改范围

- `core/extension_types.py` — 添加 Capability 类型、ExtensionMetadata
- `core/extension_api.py` — 注册时收集 metadata
- 不影响现有扩展实现
