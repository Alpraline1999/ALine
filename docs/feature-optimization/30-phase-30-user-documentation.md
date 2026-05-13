# Phase 30：用户文档体系

## 目标与完成定义

**目标**：建立面向最终用户和扩展开发者的完整文档体系，降低使用和二次开发门槛。

**完成定义**：
- 基于 docstring 自动生成 API 参考文档
- 用户手册覆盖完整工作流（数字化 → 处理 → 分析 → 绘图 → 导出）
- 扩展开发指南与 `extensions/README.md` 保持同步
- 各文档之间有清晰的导航索引

## 当前代码现状

- `README.md` — 产品介绍、安装方式、功能说明、项目结构（较完整）
- `DESIGN.md` — 架构重构设计文档（面向开发者）
- `extensions/README.md` — 扩展开发指南（较完整，323 行）
- 代码中有不少 docstring，但未集中生成文档
- 缺少面向最终用户的完整操作手册
- 缺少扩展开发的进阶教程和示例

## 优化方案

### 1. API 参考文档

使用 Sphinx + autodoc 从 docstring 生成：
```bash
# docs/source/conf.py
extensions = ['sphinx.ext.autodoc', 'sphinx.ext.napoleon']
```

目标模块（按优先级）：
1. `core/extension_api.py` — 扩展开发者的主要接口
2. `models/schemas.py` — 数据模型参考
3. `processing/data_engine.py` — Pipeline 执行接口
4. `core/analysis_engine.py` — 分析功能接口
5. `core/exporter.py` — 导出格式参考

### 2. 用户手册

目录结构：
```
docs/user-guide/
├── index.md               # 导览
├── quick-start.md         # 快速开始（从图片到图表）
├── project-management.md  # 项目管理
├── digitization.md        # 数字化取点
├── data-management.md     # 数据管理
├── processing.md          # 曲线处理流水线
├── analysis.md            # 分析与报告
├── charting.md            # 出版级绘图
├── export.md              # 导出与分享
└── settings.md            # 个性化设置
```

内容要求：
- 每个页面包含：场景说明、操作步骤、预期结果
- 配合截图或 GIF（预留占位）
- 有"典型工作流"串联各页面

### 3. 扩展开发指南补充

在现有 `extensions/README.md` 基础上补充：
- 进阶示例：复杂参数表单、多曲线处理、绘图扩展与交互
- 调试技巧：如何测试扩展、查看日志、处理错误
- 发布检查表（已部分存在，可更详细）

### 4. 文档生成自动化

- 在 `pyproject.toml` 中添加 docs 命令
- CI 中可选自动构建文档（但用户已排除 CI 阶段，保持手动构建）

## 验收要点

- `sphinx-build` 成功生成 HTML 文档
- 用户手册覆盖核心工作流（从图片数字化到图表导出）
- 扩展开发指南包含至少 3 个完整示例
- 所有文档可通过索引页面导航访问

## 边界与约束

- 不要求文档翻译（留待 i18n 之后）
- API 文档自动从代码生成，用户手册手动维护
- 文档放在 `docs/` 目录，不混入 `extensions/` 或 `ui/` 等代码目录
