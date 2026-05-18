曲线处理
========

场景
----

处理页用于把原始曲线整理成可分析、可绘图、可复现的标准数据。推荐把每个步骤拆成原子操作，再按顺序串成 pipeline，而不是依赖某个扩展在内部偷偷补齐前置步骤。

典型流程
--------

1. 先做点序整理与异常值清理。
2. 再做重采样、平滑、滤波或基线校正。
3. 最后做导数、积分、归一化、配对计算或多曲线合成。

推荐内置扩展
------------

- ``order_points``: 仅做点序重排，适合数字化后点顺序混乱的数据。
- ``sort_dedup_interpolate``: 仅做按 X 排序、重复点合并与缺失补点，适合作为后续算法的前置整理步骤。
- ``crop``: 截取 X/Y 范围。
- ``despike``: 去除孤立尖刺点。
- ``smooth``: 常规平滑。
- ``filter``: 低通、高通等基础滤波。
- ``baseline_correction``: 去基线、去背景漂移。
- ``normalize``: 归一化到统一量纲。
- ``resample``: 重采样到统一 X 网格。
- ``derivative``: 求导。
- ``integral``: 积分。
- ``transform``: 线性或数学变换。
- ``kalman_filter``: 逐点平滑、降噪。
- ``fft`` / ``ifft``: 频域往返处理。
- ``multi_curve_mean``: 多条曲线求平均。
- ``pairwise_compute``: 两条曲线逐点四则运算。

原子性原则
----------

- ``pairwise_compute`` 不负责隐式重采样或自动对齐。
- 当两条曲线 X 网格不同，应先在 pipeline 中显式加入 ``resample`` 或 ``sort_dedup_interpolate``。
- ``order_points`` 只解决顺序问题，不同时承担平滑、去重、插值。
- ``baseline_correction``、``smooth``、``despike`` 应分别作为独立步骤存在，便于调参和复现。

面向二维曲线的实用建议
----------------------

- 数字化导入后的首选整理链通常是 ``order_points -> sort_dedup_interpolate -> despike -> smooth``。
- 比较两条实验曲线前，推荐 ``crop -> resample -> pairwise_compute`` 或 ``crop -> resample -> correlation``。
- 需要保留拐点和交点时，先做轻量 ``despike``，再谨慎使用 ``smooth``。

预期结果
--------

得到结构稳定、X 网格明确、适合分析和绘图的标准曲线，并且每个步骤都可单独复用、插拔和保存为模板。
