========
分析引擎
========

``analysis_engine`` 提供曲线拟合、峰值检测、统计分析和报告生成功能。
所有函数输入 ``List[float]``，输出结构化的 ``dict`` 结果。

核心函数
--------

曲线拟合
~~~~~~~~

.. autofunction:: core.analysis_engine.fit_curve

支持的拟合模型：

.. list-table::
   :header-rows: 1

   * - 显示名
     - 模型 ID
   * - 线性 (ax+b)
     - ``linear``
   * - 幂函数 (a·x^b)
     - ``power``
   * - 指数 (a·e^(bx))
     - ``exponential``
   * - 高斯 (a·exp(-(x-μ)²/2σ²))
     - ``gaussian``
   * - 2次多项式
     - ``poly2``
   * - 3次多项式
     - ``poly3``

峰值检测
~~~~~~~~

.. autofunction:: core.analysis_engine.detect_peaks
.. autofunction:: core.analysis_engine.detect_valleys

统计分析
~~~~~~~~

.. autofunction:: core.analysis_engine.compute_statistics
.. autofunction:: core.analysis_engine.compute_correlation
.. autofunction:: core.analysis_engine.compute_error_metrics

分析执行
~~~~~~~~

.. autofunction:: core.analysis_engine.run_analysis

报告生成
--------

.. autofunction:: core.analysis_engine.list_report_template_placeholders
.. autofunction:: core.analysis_engine.render_report

使用示例
--------

曲线拟合::

    from core.analysis_engine import fit_curve

    xs = [0, 1, 2, 3, 4, 5]
    ys = [0.1, 2.1, 4.0, 5.9, 8.2, 9.9]
    result = fit_curve(xs, ys, model="linear")
    print(f"方程: {result['equation']}")
    print(f"R²: {result['r2']:.4f}")

峰值检测::

    from core.analysis_engine import detect_peaks

    import math
    xs = [i * 0.1 for i in range(100)]
    ys = [math.sin(x) + 0.3 * math.sin(3 * x) for x in xs]
    peaks = detect_peaks(xs, ys, distance=10, prominence=0.3)

统计分析::

    from core.analysis_engine import compute_statistics

    stats = compute_statistics(xs, ys)
    print(f"均值: {stats['mean']:.4f}")
    print(f"标准差: {stats['std']:.4f}")

完整分析流程::

    from core.analysis_engine import run_analysis

    # 使用扩展执行分析
    result = run_analysis(
        analysis_type="curve_fit",
        xs=xs, ys=ys,
        params={"model": "linear"},
    )
