========
数据模型
========

``models.schemas`` 模块定义了 ALine 项目中所有 Pydantic 数据模型。
这些模型序列化到项目文件（``.aline``）中，是项目持久化和内存操作的核心数据结构。

兼容性说明
  模型兼容旧版 PyLine 格式（``.pyline``），所有新增字段均带默认值，
  Pydantic 加载旧文件不会报错。

.. automodule:: models.schemas
   :members:
   :undoc-members:
   :show-inheritance:

----

模型分类索引
------------

PyLine 兼容模型
~~~~~~~~~~~~~~~

从 PyLine 继承的原始模型，字段保持不变：

* :class:`~models.schemas.CalibrationData` — 像素坐标到真实坐标的校准参数
* :class:`~models.schemas.Curve` — 一条数字化曲线
* :class:`~models.schemas.MaskData` — 图像遮罩
* :class:`~models.schemas.ImageWork` — 待数字化的图像及其提取曲线
* :class:`~models.schemas.PictureAsset` — 项目内管理的已导出图片

ALine 数据模型
~~~~~~~~~~~~~~

独立于 PyLine 的数据管理模型：

* :class:`~models.schemas.DataSeries` — 直接存储数值的独立数据系列
* :class:`~models.schemas.Dataset` — 多个 DataSeries 的容器
* :class:`~models.schemas.AnalysisResult` — 分析任务的完整结果
* :class:`~models.schemas.Project` — 项目根节点

图表配置模型（v0.3）
~~~~~~~~~~~~~~~~~~~~

* :class:`~models.schemas.AxisConfig` — 坐标轴配置
* :class:`~models.schemas.SeriesRef` — 图表中曲线引用及样式
* :class:`~models.schemas.FigureConfig` — 可视化页图表配置
* :class:`~models.schemas.FigureState` — 图表页运行时状态源

样式与主题模型
~~~~~~~~~~~~~~

* :class:`~models.schemas.CurveStyle` — 单条曲线的可复用样式
* :class:`~models.schemas.CurveStyleTemplate` — 曲线样式模板
* :class:`~models.schemas.PlotTheme` — 绘图样式主题

项目树模型（v0.2+）
~~~~~~~~~~~~~~~~~~~

* :class:`~models.schemas.ProjectTree` — 树形项目结构
* :class:`~models.schemas.DataFile` — 数据文件节点
* :class:`~models.schemas.SavedPipeline` — 保存的处理流水线模板
* :class:`~models.schemas.ReportTemplate` — 报告模板
* 相关的 AI 助手节点模型（AIPrompt, AISkill, AIAgent）


使用示例
--------

创建项目::

    from models.schemas import Project, DataSeries, Dataset

    project = Project.create_new("我的实验")
    series = DataSeries(name="样本A", x=[1, 2, 3], y=[4.1, 5.2, 6.0])
    dataset = Dataset(name="数据组1", series=[series])
    project.datasets.append(dataset)

查找数据系列::

    found = project.find_series(series_id)
    if found:
        print(f"名称: {found.name}, 点数: {len(found.x)}")
