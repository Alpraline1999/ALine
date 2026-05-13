========
数据导出
========

``Exporter`` 类提供曲线数据的多格式导出，支持 CSV、Excel（.xls / .xlsx）、JSON、TXT 和剪贴板。
支持单曲线和多曲线合流导出。

.. automodule:: core.exporter
   :members:
   :undoc-members:

----

支持的导出格式
--------------

.. list-table::
   :header-rows: 1

   * - 格式
     - 方法
   * - CSV
     - ``Exporter.to_csv(curve, file_path)``
   * - Excel (.xlsx)
     - ``Exporter.to_xlsx(curve, file_path)``
   * - Excel (.xls)
     - ``Exporter.to_xls(curve, file_path)``
   * - JSON
     - ``Exporter.to_json(curve, file_path)``
   * - TXT
     - ``Exporter.to_txt(curve, file_path)``
   * - 剪贴板
     - ``Exporter.to_clipboard(curve)``

DataSeries 导出
~~~~~~~~~~~~~~~

上述所有导出方法同时支持 ``Curve`` 和 ``DataSeries`` 对象。
DataSeries 方法带有 ``_ds`` 后缀：

* ``Exporter.to_csv_ds(series, file_path)``
* ``Exporter.to_xlsx_ds(series, file_path)``
* ``Exporter.to_json_ds(series, file_path)``

合并导出
~~~~~~~~

当多条曲线的 X 坐标完全对齐时，支持合并为一张表导出:

* ``Exporter.export_curves_merged(curves, file_path, format="csv")``
* ``Exporter.export_series_merged(series_list, file_path, format="xlsx")``

使用示例
--------

导出单条曲线::

    from core.exporter import Exporter

    # Curve 对象
    Exporter.to_csv(curve, "/path/to/output.csv")
    Exporter.to_xlsx(curve, "/path/to/output.xlsx")

    # DataSeries 对象
    Exporter.to_csv_ds(series, "/path/to/output.csv")
    Exporter.to_json(series, "/path/to/output.json")

合并导出多条曲线::

    # 多条 X 对齐的曲线合并成一张表
    Exporter.export_curves_merged(
        [curve_a, curve_b, curve_c],
        "/path/to/merged_output.csv",
        format="csv",
    )
