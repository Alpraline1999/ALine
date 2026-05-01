# Phase 6 Task 1: DataSeries 来源追踪字段

## 目标

添加 DataSeries 来源追踪能力，记录每条数据列的来源文件和导入参数。

## 实施

1. 在 `models/schemas.py` 的 `DataSeries` 添加:
   - `source_file_path: str = ""` — 来源文件路径
   - `import_params: dict = field(default_factory=dict)` — 导入参数快照
2. DataPage/import_dialog 在创建 DataSeries 时填入来源信息
