# Phase 6 Task 1

## 阶段

- Phase 6 / quality-gates-and-test-restructure

## 对应方案

- `docs/refactor/07-phase-6-quality-gates-and-test-restructure.md`

## 目标

- 固定 characterization tests。
- 将架构护栏测试从聚合文件中拆出，形成独立测试模块。

## 本任务范围

- 新增字符化测试模块。
- 新增架构护栏测试模块。
- 让原有聚合测试文件仅保留兼容导入层。

## 验证

- `python3 -m unittest tests.test_refactor_guardrails`
- `python3 -m py_compile tests/test_refactor_guardrails.py tests/test_refactor_phase0.py tests/test_architecture_guardrails.py`

## 完成判定

- 字符化测试与架构护栏测试完成分层。
