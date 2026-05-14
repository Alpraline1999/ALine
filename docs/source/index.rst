====================
ALine API 参考文档
====================

ALine 是一个面向科研与工程场景的桌面数据工作台，用于把图片曲线数字化、把数据资产组织进统一项目、执行处理与分析、生成图表与报告素材，并通过 Python 扩展接入领域算法。

当前版本 **0.3.0**，以 PySide6 + qfluentwidgets 构建桌面界面，以 Matplotlib 完成绘图预览和导出。

核心能力
--------

* **共享项目树** — 统一管理数据文件、图片、分析结果、模板和扩展配置
* **图片数字化** — 校准、自动取点、手动修正、结果保存到项目资产
* **数据处理** — 通过 Pipeline 组织曲线处理步骤，支持模板保存和复用
* **数据分析** — 生成摘要、表格、文本、结果曲线和报告模板输出素材
* **图表与样式** — 曲线样式、绘图样式、绘图扩展和图片导出
* **扩展系统** — 支持 processing / analysis / plot / digitize 四类内置与外部扩展

文档导览
--------

本参考文档面向扩展开发者和希望深入了解 ALine 内部 API 的用户。

.. toctree::
   :maxdepth: 2
   :caption: 目录

   user-guide/index
   api/models
   api/extensions
   api/processing
   api/analysis
   api/export

模块架构
--------

.. list-table::
   :header-rows: 1

   * - 模块
     - 说明
   * - :doc:`api/models`
     - 项目、数据系列、曲线、图表配置等 Pydantic 数据模型
   * - :doc:`api/extensions`
     - 扩展类型定义、注册表、加载器、校验器、运行时调用
   * - :doc:`api/processing`
     - 数据处理流水线引擎、坐标校准、降采样
   * - :doc:`api/analysis`
     - 曲线拟合、峰值检测、统计分析、报告渲染
   * - :doc:`api/export`
     - CSV / Excel / JSON / TXT / 剪贴板导出

快速链接
--------

* 扩展开发指南：``extensions/README.md``
* 设计文档：``DESIGN.md``
* 开发架构指南：``docs/development-architecture-guide.md``
