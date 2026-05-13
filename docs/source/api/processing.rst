========
数据处理
========

数据处理系统负责对曲线数据执行非破坏性操作。核心是 ``processing.data_engine``，
它实现了一个流水线引擎，按顺序对数据应用一系列操作。

流水线引擎（Data Engine）
-------------------------

``data_engine`` 是数据处理的核心。每个操作用 ``dict`` 描述，支持的操作类型包括：

* **smooth** — 平滑（Savitzy-Golay、移动平均）
* **crop** — 裁剪 x 范围
* **normalize** — 归一化（min-max、z-score）
* **resample** — 重采样（均匀间距、对齐）
* **fft** — 快速傅里叶变换
* **derivative** — 数值微分
* **integral** — 数值积分
* **transform** — 表达式变换
* **filter** — 频域滤波
* **pairwise_compute** — 双曲线运算

.. automodule:: processing.data_engine
   :members:
   :exclude-members: XY, PipelineLine, PipelineResult, _pipeline_pool,
                     _op_crop, _op_smooth, _op_normalize, _op_resample,
                     _op_fft, _op_derivative, _op_integral, _op_transform,
                     _op_filter, _op_pairwise_compute,
                     _is_pairing_op, _is_multi_line_processing_op,
                     _find_single_pairing_op, _normalize_lines_list,
                     _resolve_pairing_inputs, _execute_pairing_op,

使用示例
~~~~~~~~

单曲线流水线::

    from processing.data_engine import apply_pipeline

    xs = [0, 1, 2, 3, 4, 5]
    ys = [0.1, 1.8, 4.2, 9.1, 16.3, 24.9]

    ops = [
        {"type": "smooth", "params": {"method": "savgol", "window": 5, "poly": 2}},
        {"type": "normalize", "params": {"mode": "minmax"}},
    ]
    xs_new, ys_new = apply_pipeline(xs, ys, ops)

多曲线流水线::

    from processing.data_engine import apply_pipeline_to_lines

    lines = [
        {"x": [0, 1, 2], "y": [0, 1, 4], "name": "曲线1"},
        {"x": [0, 1, 2], "y": [1, 2, 5], "name": "曲线2"},
    ]
    ops = [
        {"type": "smooth", "params": {"method": "savgol", "window": 3, "poly": 2}},
    ]
    processed_lines, warnings = apply_pipeline_to_lines(lines, ops)

坐标校准（Calibration）
-----------------------

将像素坐标转换为真实坐标。支持线性、对数和极坐标三种坐标类型。

.. automodule:: processing.calibration
   :members:

使用示例
~~~~~~~~

.. code-block:: python

    from models.schemas import CalibrationData
    from processing.calibration import compute_actual_coords

    calib = CalibrationData(
        x_start=(50, 100), x_end=(450, 100),
        y_start=(50, 50),  y_end=(50, 400),
        x_range=(0, 10),   y_range=(0, 100),
        coord_type="linear",
    )
    x_actual, y_actual = compute_actual_coords(calib, px=250, py=200)

降采样（Downsample）
--------------------

在保持视觉形状的前提下减少渲染点数，使用 LTTB 算法。

.. automodule:: processing.downsample
   :members:

使用示例
~~~~~~~~

.. code-block:: python

    import numpy as np
    from processing.downsample import downsample_lttb

    x = np.linspace(0, 10, 50000)
    y = np.sin(x) + np.random.normal(0, 0.05, len(x))
    x_down, y_down = downsample_lttb(x, y, max_points=1000)
