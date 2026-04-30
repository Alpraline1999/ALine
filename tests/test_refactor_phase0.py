from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

MAIN_FLOW_SAMPLES = [
    "打开项目",
    "共享树选择",
    "数据导入",
    "加入绘图",
    "加入处理",
    "运行分析",
    "数字化导出",
    "保存项目",
]

PHASE0_TASK_PATH = REPO_ROOT / "docs" / "refactor" / "tasks" / "phase0_task1.md"


class TestPhase0TaskPlan(unittest.TestCase):
    def test_phase0_task_file_exists(self) -> None:
        self.assertTrue(PHASE0_TASK_PATH.exists(), "缺少 Phase 0 任务文件")

    def test_phase0_task_contains_main_flow_samples(self) -> None:
        content = PHASE0_TASK_PATH.read_text(encoding="utf-8")
        for sample in MAIN_FLOW_SAMPLES:
            self.assertIn(sample, content)
