# Changelog

## v0.1.0 (2025-05-18)

### 新增

- **共享项目树**：统一管理数据文件、图片、分析结果、模板和扩展配置
- **图片数字化**：支持校准、自动取点、手动修正、结果保存到项目资产
- **数据处理 Pipeline**：支持模板保存、加载和复用
- **数据分析**：生成摘要、表格、文本、结果曲线和报告模板输出素材
- **图表与样式**：支持曲线样式、绘图样式、绘图扩展和图片导出
- **扩展系统**：支持 processing / analysis / plot / digitize 四类内置与外部扩展（51 个内置扩展）
- **AI 运行时**：命令注册、工具分发、Agent 运行时与 provider 封装（实验性）
- **国际化**：zh_CN + en_US 语言支持
- **Windows bootstrap 打包**：嵌入 Python 运行时，无需用户预装 Python
- **CI/CD**：GitHub Actions 质量门与源码发布流水线
- **架构护栏**：AST 级依赖方向检查

### 修复

- Matplotlib 3.10 兼容性：修正 `draw_local_zoom` 嵌入视图坐标翻转逻辑
- Matplotlib 3.10 兼容性：修正 `show_connector` 对字符串 `"false"` 的布尔解析
- 内置扩展发布层级：`multi_curve_correlation` 调整为默认隐藏 (experimental)

### 工程

- 锁定依赖版本范围（`requirements.txt` 添加上下界）
- CI 从仅 2 个测试文件扩展为全量后端 + 架构护栏 + 设置页回归
- mypy 配置从 `strict = true`（1362 错误未通过）调整为诚实声明的具体选项
