from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.extension_registry import ExtensionRegistry

_BUILTIN_EXTENSION_DIRS = (
    "processing",
    "analysis",
    "plot",
    "digitize",
)

_KNOWN_PROCESSING = {
    "baseline_correction",
    "crop",
    "despike",
    "derivative",
    "fft",
    "filter",
    "ifft",
    "integral",
    "kalman_filter",
    "multi_curve_mean",
    "normalize",
    "order_points",
    "pairwise_compute",
    "resample",
    "sort_dedup_interpolate",
    "smooth",
    "transform",
}
_KNOWN_ANALYSIS = {
    "area_between_curves",
    "correlation",
    "curve_intersections",
    "curve_fit",
    "error_compare",
    "lag_analysis",
    "multi_curve_correlation",
    "peak_detect",
    "spectrum_analysis",
    "statistics",
}
_KNOWN_PLOT = {
    "plot_arrow_annotation",
    "plot_circle_annotation",
    "plot_dual_curve_band",
    "plot_line_end_label",
    "plot_local_zoom",
    "plot_polar_projection",
    "plot_rectangle_annotation",
    "plot_reference_line",
    "plot_science_style",
    "plot_text_annotation",
    "plot_uncertainty_band",
}
_KNOWN_DIGITIZE = {
    "builtin_digitize_color_detect",
    "builtin_digitize_continuous_trace",
    "builtin_digitize_dashed_trace",
    "builtin_digitize_marker_centroid",
    "builtin_digitize_multicolor_curve",
    "builtin_digitize_shape_detect",
}


def _extensions_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "extensions"


def register_core_builtin_extensions(registry: ExtensionRegistry) -> None:
    builtin_dir = _extensions_dir()
    builtin_directories = [builtin_dir / name for name in _BUILTIN_EXTENSION_DIRS if (builtin_dir / name).exists()]

    if builtin_directories and not (
        _KNOWN_PROCESSING <= {item.type for item in registry.list_processing()}
        and _KNOWN_ANALYSIS <= {item.type for item in registry.list_analysis()}
        and _KNOWN_PLOT <= {item.type for item in registry.list_plot()}
        and _KNOWN_DIGITIZE <= {item.type for item in registry.list_digitize()}
    ):
        for directory in builtin_directories:
            registry.load_from_directory(directory, source_kind="builtin")
