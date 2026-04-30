from __future__ import annotations

DEFAULT_REPORT_TEMPLATE = """\
# 数据分析报告

**日期：** {{date}}

**结果数量：** {{result_count}}

**结果名称：** {{result_names}}

**分析类型：** {{analysis_type}}

**数据来源：** {{source_name}}

---

## 结果概览

{{table:analysis_results}}

## 结果详情

{{multi_result_sections}}

---

## 常用占位符

- 基础信息: {{date}}, {{result_count}}, {{result_names}}, {{analysis_type}}, {{source_name}}, {{name1}}, {{name2}}
- 拟合结果: {{model}}, {{equation}}, {{r2}}, {{table:params}}
- 峰谷检测: {{peak_count}}, {{valley_count}}, {{table:peaks}}, {{table:valleys}}
- 统计结果: {{n}}, {{x_mean}}, {{x_std}}, {{x_min}}, {{x_max}}, {{y_mean}}, {{y_std}}, {{y_min}}, {{y_max}}
- 相关性/误差: {{r}}, {{mae}}, {{rmse}}, {{mean_error}}, {{max_abs_error}}, {{relative_mae}}
"""
