# ALine

ALine 是一个面向科研与工程场景的桌面数据工作台，用于把图片曲线数字化、把数据资产组织进统一项目、执行处理与分析、生成图表与报告素材，并通过 Python 扩展接入领域算法。

当前实现以 PySide6 + qfluentwidgets 构建桌面界面，以 Matplotlib 完成绘图预览和导出，围绕“共享项目树 + 页面工作区 + 扩展协议”组织整体工作流。

当前冻结发布版本：`ALine v0.1.0`。

## 核心能力

- 共享项目树：统一管理数据文件、图片、分析结果、模板和扩展配置，页面之间不再各自维护第二套源树。
- 图片数字化：支持校准、自动取点、手动修正、结果保存到项目资产。
- 数据处理：通过 Pipeline 组织曲线处理步骤，并支持模板保存、加载和复用。
- 数据分析：生成摘要、表格、文本、结果曲线和报告模板输出素材。
- 图表与样式：支持曲线样式、绘图样式、绘图扩展和图片导出。
- 扩展系统：支持 processing / analysis / plot / digitize 四类内置与外部扩展。

## 架构摘要

当前代码库按以下层次组织：

- `models/`：项目、数据、模板、绘图快照等共享 schema
- `core/`：项目系统、迁移、全局资产、扩展协议、导出、渲染与偏好
- `app/`：workspace state/controller、树命令服务、应用消息与上下文
- `ui/`：主窗口、页面、对话框、共享控件、主题
- `processing/`、`digitize/`：通用数值与数字化基础算法
- `extensions/`：内置扩展实现
- `tests/`、`scripts/`：回归测试、架构护栏、结构检查

更完整的结构说明见 [DESIGN.md](/home/alpraline/Projects/Python/ALine/DESIGN.md)。
开发边界与约束见 [docs/development-architecture-guide.md](/home/alpraline/Projects/Python/ALine/docs/development-architecture-guide.md)。

## 主要页面

- 首页：最近项目、创建/打开项目入口
- 数据管理页：导入、预览、整理项目资产
- 可视化页：当前图表工作集、样式与绘图扩展
- 数据处理页：Pipeline 编辑、执行与模板复用
- 数据分析页：分析输入、结果展示、报告模板输出
- 图片数字化页：校准、自动取点、修正与结果导出
- 设置页：主题、快捷键、扩展、全局资源入口

## 扩展系统

ALine 当前支持四类正式扩展：

| 类型 | 标准签名 | 返回值 |
| --- | --- | --- |
| 处理扩展 | `(lines, params)` | `line` |
| 分析扩展 | `(lines, params)` | `dict` |
| 绘图扩展 | `(plot_context, params)` | `None` |
| 数字化扩展 | `(figure, params)` | `line` |

扩展曲线协议统一为 point-list：

```python
line = [[x0, y0], [x1, y1], ...]
```

推荐通过 `extensions.processing.extension_tools.line_from_xy()` 和 `line_xy()` 做转换。
完整扩展说明见 [extensions/README.md](/home/alpraline/Projects/Python/ALine/extensions/README.md)。

## 安装与运行

推荐使用仓库内虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

启动应用：

```bash
python run.py
```

如果已创建仓库内虚拟环境：

```bash
.venv/bin/python run.py
```

## 源码发布

GitHub Public 仓库当前主要提供源码托管、Issue/文档协作和源码版本里程碑发布。
适合内部测试、开发协作和已经具备 Python 环境的用户：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## 打包发布

Windows 当前主分发方式是 bootstrap 启动包。构建脚本会：

- 复制当前源码与资源
- 注入 Windows embeddable Python runtime
- 写入锁定依赖清单
- 生成 `ALine Launcher.exe` 与最终 zip 包

构建命令：

```bash
python scripts/build_bootstrap_windows.py
```

默认产物位置：

```bash
dist/ALine-bootstrap-0.1.0-windows-x64.zip
```

GitHub Actions 已预留两条自动化流程：

- `CI`：在 `push` / `pull_request` 时执行编译检查、焦点回归测试，并生成当前 `mypy` 基线报告。
- `Source Release`：在推送 `v*` 标签时执行质量门，并在 GitHub 上创建源码版本里程碑 Release；不上传桌面安装包。

当前发布策略：

- GitHub：公开源码、文档、Issue 和源码版本标签。
- Windows：通过外部分发渠道单独发布 bootstrap 压缩包，不通过 GitHub Releases 分发安装包。
- Linux：不提供安装包，默认通过源码运行。

首次在 Windows 启动时，launcher 会在包内嵌入式 Python 运行时里自动安装依赖；因此首次启动会比后续启动更慢，并且需要联网。

## 开发与测试

常用命令：

```bash
python -m pytest tests/test_backend.py -q
python -m pytest tests/test_ui.py -q
python -m pytest tests/test_architecture_guardrails.py -q
python -m pytest tests/test_refactor_guardrails.py -q
```

开发时建议优先遵守以下规则：

- 页面不新增第二套全量数据源。
- 新的共享业务能力优先下沉到 `core/` 或 `app/`。
- 扩展协议、项目树行为、预览工具栏和参数表单优先复用现有实现。
- 影响结构边界的改动，同步更新设计文档和架构护栏。

## 文档入口

- [DESIGN.md](/home/alpraline/Projects/Python/ALine/DESIGN.md)：当前软件设计与仓库结构
- [docs/development-architecture-guide.md](/home/alpraline/Projects/Python/ALine/docs/development-architecture-guide.md)：开发架构指南
- [docs/refactor/README.md](/home/alpraline/Projects/Python/ALine/docs/refactor/README.md)：重构历史与阶段索引
- [docs/feature-optimization/README.md](/home/alpraline/Projects/Python/ALine/docs/feature-optimization/README.md)：功能优化阶段索引
- [extensions/README.md](/home/alpraline/Projects/Python/ALine/extensions/README.md)：扩展开发文档

## License

本项目采用 [MPL-2.0](/home/alpraline/Projects/Python/ALine/LICENSE) 许可发布。
