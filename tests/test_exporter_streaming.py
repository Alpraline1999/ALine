from __future__ import annotations

import json
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

from core.exporter import Exporter


def _make_curve() -> SimpleNamespace:
    return SimpleNamespace(
        name="demo",
        x_data=[1, 2, 3],
        y_data=[4, 5, 6],
        x_actual=[],
        y_actual=[],
        calibration=None,
    )


class TestExporterStreaming(unittest.TestCase):
    def test_iter_rows_preserves_curve_order(self) -> None:
        curve = _make_curve()

        self.assertEqual([(1, 4), (2, 5), (3, 6)], list(Exporter._iter_rows(curve)))

    def test_export_txt_uses_iter_rows(self) -> None:
        curve = _make_curve()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "curve.txt"
            Exporter.export_txt(curve, str(file_path))

            content = file_path.read_text(encoding="utf-8")

        self.assertIn("# demo", content)
        self.assertIn("X\tY", content)
        self.assertIn("1\t4", content)
        self.assertIn("3\t6", content)

    def test_export_json_uses_iter_rows(self) -> None:
        curve = _make_curve()

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "curve.json"
            Exporter.export_json(curve, str(file_path))
            payload = json.loads(file_path.read_text(encoding="utf-8"))

        self.assertEqual("demo", payload["name"])
        self.assertEqual([{"x": 1, "y": 4}, {"x": 2, "y": 5}, {"x": 3, "y": 6}], payload["points"])


if __name__ == "__main__":
    unittest.main()
