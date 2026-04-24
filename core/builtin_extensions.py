from __future__ import annotations

from pathlib import Path

from digitize.builtin_extensions import ensure_builtin_digitize_extensions


_BUILTIN_EXTENSION_DIRS = (
    "processing",
    "analysis",
)


def _extensions_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "extensions"


def register_core_builtin_extensions(registry) -> None:
    builtin_dir = _extensions_dir()
    builtin_directories = [builtin_dir / name for name in _BUILTIN_EXTENSION_DIRS if (builtin_dir / name).exists()]
    known_processing = {"crop", "smooth", "normalize", "resample", "fft", "derivative", "integral", "transform", "filter", "pairwise_compute"}
    known_analysis = {"curve_fit", "peak_detect", "statistics", "correlation", "error_compare"}

    if builtin_directories and not (known_processing <= {item.type for item in registry.list_processing()} and known_analysis <= {item.type for item in registry.list_analysis()}):
        for directory in builtin_directories:
            registry.load_from_directory(directory, source_kind="builtin")

    ensure_builtin_digitize_extensions(registry)