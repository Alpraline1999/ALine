# Phase 4：ExtensionRuntime 与 GlobalAssetCatalog

## 目标与完成定义

目标：

- 把扩展系统变成独立 runtime。
- 让全局资产只承担跨项目共享资源职责。
- 消除 `core -> extensions` 反向依赖。

完成定义：

- 页面不再自行注册扩展。
- 扩展系统按 `types/registry/loader/invoker/config adapter` 分层。
- 报告模板默认值与 `global_assets` 不再依赖分析实现细节。

## 进入前提

- `Phase 3` 完成。
- 页面业务状态已脱离 widget 私有实现。

## 本阶段纳入的状态与边界

- 纳入：
  - 扩展注册状态
  - 扩展配置适配
  - 全局模板、全局样式、扩展配置
- 不纳入：
  - 页面自己的工作区状态

## 本阶段禁止改动的区域

- 禁止继续在页面构造函数中注册内置扩展。
- 禁止再把共享工具放回 `extensions` 目录供 `core` 调用。

## 目标接口/类型/运行时对象

- `ExtensionRuntime`
  - `types`
  - `registry`
  - `loader`
  - `invoker`
  - `config adapter`
- `GlobalAssetCatalog`
  - 只负责跨项目共享的：
    - pipeline 模板
    - 绘图样式
    - 报告模板
    - 曲线样式模板
    - 扩展配置

## 实施顺序

1. 把页面中的扩展注册逻辑迁到统一 bootstrap。
2. 拆 `extension_api.py`。
3. 把通用曲线/线工具迁到 `core`。
4. 清理 `core` 对 `extensions` 的导入。
5. 从分析实现中移出默认报告模板常量。
6. 收口 `global_assets` 的职责边界。

## 兼容/迁移策略

- 保留现有扩展能力，但切断页面注册路径。
- 对外部扩展仍保留现有加载能力，但通过统一 runtime 进入。

## 验收标准

- 页面构造路径不再触发内置扩展注册。
- `core/**` 中不再直接导入 `extensions/**`。
- 全局资产不再依赖分析引擎实现细节。

## 提交检查点

- 检查点 1：扩展统一 bootstrap 落地。
- 检查点 2：`extension_api.py` 完成分层。
- 检查点 3：通用曲线工具迁入 `core` 并清除反向依赖。
- 检查点 4：`GlobalAssetCatalog` 边界收口。

## 风险与回退办法

风险：

- 扩展注册顺序变化导致页面功能退化。
- 通用工具迁移后遗漏某些调用点。

回退办法：

- 如果出现运行时缺扩展，先修正 bootstrap，不允许回退到页面注册。
- 若某工具迁移造成调用断裂，临时提供单一转发层，但必须在本阶段内清除。
