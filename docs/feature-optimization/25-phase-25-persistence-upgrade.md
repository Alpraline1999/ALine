# Phase 25：持久化升级

## 目标与完成定义

**目标**：解决 JSON 纯文本存储的性能瓶颈，实现增量保存、懒加载、文件级原子写入，提升大型项目的加载和保存速度。

**完成定义**：
- `.aline` 项目文件升级为 ZIP 容器格式（内含 `project.json` + 分块数据文件）
- 曲线点数据独立存储，支持按需懒加载
- 保存时仅写入变更块（增量保存）
- 打开旧 `.pyline` / `.aline` 纯 JSON 文件时自动兼容
- 原子写入防止保存中断导致文件损坏

## 当前代码现状

- 项目文件为纯 JSON（`.pyline` / `.aline`），全部序列化为一个文件
- `ProjectManager._save_project()` 全程 `model_dump()` → `json.dumps()` → 单次写入
- `ProjectManager._load_project()` 全程 `json.loads()` → 解析所有模型
- 一个含 50 条曲线各 10000 点的项目，JSON 文件可达 10-30MB，加载耗时数秒
- 无增量写入：任何微小修改（如重命名一条曲线）都要重写整个文件
- 无原子写入：保存中途崩溃会导致文件损坏

## 优化方案

### 1. ZIP + JSON 容器格式

```
project.aline  → 实际为 ZIP 包
├── aline.json              # 项目元数据（不含曲线点）
├── data/
│   ├── series_{id}.json    # 每条 DataSeries 的 x/y 数据
│   ├── curve_{id}.json     # 每条 Curve 的点数据
│   └── analysis_{id}.json  # 分析摘要（大文本）
└── meta.json               # 版本、校验和、块清单
```

`aline.json` 只包含：
- Project 元数据（名称、ID、时间）
- 树结构（无数据载荷）
- 所有非数值配置（样式、模板内容、分析参数）

曲线点数据从 `DataSeries.x/y`、`Curve.x_data/y_data` 等字段中分离到独立文件。

### 2. 懒加载策略

- 打开项目时只加载 `aline.json` + `meta.json`
- 树节点加载后即可正常展示
- 曲线具体数据在需要渲染或计算时才从 ZIP 中读取对应文件
- 加载进度通过 `meta.json` 中的块清单预知总大小

### 3. 增量保存

- `meta.json` 维护每个数据块的 version/hash
- 保存时只写 version 变更的块
- 树结构调整只写 `aline.json`

### 4. 原子写入

- 写入临时文件 → fsync → 重命名覆盖原文件
- 写入中断时保留上次完整版本

### 5. 向前兼容

- `ProjectSerializer` 检测文件格式
- `.pyline` 或旧 `.aline`（纯 JSON）→ 使用原有全量加载逻辑
- 首次保存时升级为新 ZIP 格式

## 分步实施

1. 定义 ZIP 容器格式规范与 `ProjectSerializerV2`
2. 实现懒加载的数据代理（在 DataSeries/Curve 模型中引入 lazy loading）
3. 实现增量保存策略
4. 兼容旧格式加载
5. 基准测试验证性能提升

## 验收要点

- 50 条 x 10000 点项目的加载时间 < 500ms（当前可能数秒）
- 单条曲线重命名保存时间 < 100ms
- 旧 `.pyline` 文件可以正常打开
- 保存过程中强行终止不损坏已有文件

## 边界与约束

- 不改变 `Project` / `DataSeries` / `Curve` 等模型的定义
- 不改变 `project_manager` 的公共 API
- 初始仅优化存储格式，暂不引入 SQLite
- 向后兼容旧格式，但不支持写回旧格式
