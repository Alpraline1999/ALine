"""
Profiling fixtures and performance baseline tracking for Phase 22.

Provides reproducible large-curve data generators and a lightweight
performance measurement recorder for use with cProfile and manual benchmarks.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np


class LargeCurveProfileFixture:
    """Fixture for reproducible profiling of curve operations on large datasets."""

    USAGE_NOTE = (
        "Use this fixture for reproducible profiling. "
        "Run with: python -m cProfile -s cumulative"
    )

    @staticmethod
    def gen_large_curve(n_points: int = 50000) -> Dict[str, List[float]]:
        """Generate a single large curve as dict with 'x' and 'y' float lists.

        Uses a slow sinusoidal envelope for realistic profiling load.
        """
        xs = np.linspace(0, 1000.0, n_points, dtype=np.float64).tolist()
        ys = (np.sin(np.array(xs) * 0.05) * 10.0 + np.array(xs) * 0.001).tolist()
        return {"x": xs, "y": ys}

    @staticmethod
    def gen_multi_curve(
        n_curves: int = 10, n_points: int = 20000
    ) -> List[Dict[str, Any]]:
        """Generate multiple independent curves, each with phase-shifted sinusoid."""
        curves: List[Dict[str, Any]] = []
        for i in range(n_curves):
            xs = np.linspace(0, 1000.0, n_points, dtype=np.float64).tolist()
            ys = (np.sin(np.array(xs) * 0.05 + i * 0.5) * 10.0).tolist()
            curves.append({"name": f"curve_{i}", "x": xs, "y": ys})
        return curves

    @staticmethod
    def gen_large_workspace(
        n_files: int = 20,
        n_curves_per_file: int = 5,
        n_points: int = 10000,
    ) -> Dict[str, Any]:
        """Generate a project model payload with many curves spread across files."""
        files: List[Dict[str, Any]] = []
        for f_idx in range(n_files):
            file_curves: List[Dict[str, Any]] = []
            for c_idx in range(n_curves_per_file):
                xs = np.linspace(0, 1000.0, n_points, dtype=np.float64).tolist()
                ys = (np.sin(np.array(xs) * 0.05 + c_idx * 0.3) * 10.0).tolist()
                file_curves.append(
                    {"name": f"curve_{f_idx}_{c_idx}", "x": xs, "y": ys}
                )
            files.append({"name": f"image_{f_idx}", "curves": file_curves})
        return {
            "project_name": "benchmark_project",
            "file_count": n_files,
            "curves_per_file": n_curves_per_file,
            "points_per_curve": n_points,
            "files": files,
        }


class PerformanceBaseline:
    """Lightweight performance tracker using online (Welford) statistics.

    Stores measurements keyed by benchmark name.  Each entry records
    running mean, standard deviation, count, and the last timestamp.
    """

    def __init__(self) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}

    def record(self, name: str, duration_seconds: float) -> None:
        """Record a single duration measurement against *name*."""
        import datetime as _dt

        if name not in self._records:
            self._records[name] = {
                "mean": duration_seconds,
                "std": 0.0,
                "count": 1,
                "timestamp": _dt.datetime.now().isoformat(),
            }
            return

        rec = self._records[name]
        old_mean: float = rec["mean"]
        old_count: int = rec["count"]
        new_count = old_count + 1
        delta = duration_seconds - old_mean
        new_mean = old_mean + delta / new_count
        delta2 = duration_seconds - new_mean
        # Welford's online variance update
        new_var = ((old_count - 1) * (rec["std"] ** 2) + delta * delta2) / new_count
        rec["mean"] = new_mean
        rec["std"] = float(max(new_var, 0.0) ** 0.5)
        rec["count"] = new_count
        rec["timestamp"] = _dt.datetime.now().isoformat()

    def report(self) -> str:
        """Return a multi-line formatted report of all recorded benchmarks."""
        if not self._records:
            return "No performance measurements recorded."

        lines = ["Performance Baseline Report", "=" * 40]
        for name in sorted(self._records):
            rec = self._records[name]
            lines.append(
                f"  {name}: mean={rec['mean']:.6f}s  std={rec['std']:.6f}s  "
                f"n={rec['count']}  last={rec['timestamp']}"
            )
        return "\n".join(lines)


def test_large_curve_fixture_shape():
    """Verify that the profile fixture produces correctly-sized data."""
    fixture = LargeCurveProfileFixture()
    curve = fixture.gen_large_curve(1000)
    assert len(curve["x"]) == 1000
    assert len(curve["y"]) == 1000
