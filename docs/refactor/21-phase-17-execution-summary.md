# Phase 17 Execution Summary

## 范围

- Phase 17：长流程业务编排与分析工作台收口

## 已完成内容

- 收口了 `core/analysis_engine.py` 的曲线拟合结果拼装路径，把结果装配逻辑从主分支中抽出，降低了长函数密度。
- 提取了 `ui/dialogs/import_dialog.py` 的 `ImportPreviewParser`，把导入预览解析与对话框状态管理分离。
- 将 `processing/data_engine.py` 的 pipeline 执行路径拆成无配对与配对两条 helper，保留主入口只负责调度。
- 阶段任务文档已按要求写入 `docs/refactor/tasks/`，并完成对应窄测验证。

## 验证

- `.venv/bin/python -m py_compile processing/data_engine.py`
- `.venv/bin/python -m unittest tests.test_extension_runtime.TestExtensionRuntime.test_request_builds_curve_buffers tests.test_backend.TestDataEngine.test_apply_pipeline_empty_ops`

## 备注

- 本阶段仅做长流程编排收口，不涉及算法行为重写，也未触碰扩展协议大改版。
