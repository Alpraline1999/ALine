#!/usr/bin/env python3
"""Build a Windows bootstrap package for ALine."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from importlib import metadata
from pathlib import Path
from zipfile import ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aline_metadata import APP_NAME, APP_VERSION


DIST_DIR = ROOT / "dist"
BOOTSTRAP_TEMPLATE_DIR = ROOT / "bootstrap"
DEFAULT_OUTPUT_NAME = f"{APP_NAME}-bootstrap-{APP_VERSION}-windows-x64"
DEFAULT_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
DEFAULT_EXTRA_INDEX_URLS = ["https://pypi.org/simple"]
DEFAULT_LOCK_PYTHON = ROOT / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "python"
DEBUG = os.environ.get("ALINE_BOOTSTRAP_DEBUG") == "1"
DEFAULT_WINDOWS_PYTHON_VERSION = "3.12.10"
DEFAULT_WINDOWS_EMBED_URL = (
    f"https://www.python.org/ftp/python/{DEFAULT_WINDOWS_PYTHON_VERSION}/"
    f"python-{DEFAULT_WINDOWS_PYTHON_VERSION}-embed-amd64.zip"
)
DEFAULT_GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"

SOURCE_ITEMS = [
    "app",
    "assets",
    "config",
    "core",
    "digitize",
    "extensions",
    "locale",
    "models",
    "processing",
    "ui",
    "LICENSE",
    "README.md",
    "aline_metadata.py",
    "main.py",
    "requirements.txt",
    "run.py",
]

CRITICAL_IMPORTS = [
    "PySide6",
    "qfluentwidgets",
    "numpy",
    "scipy",
    "matplotlib",
    "cv2",
]

PACKAGE_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


def _normalize_dist_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db"),
    )


def _debug(message: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {message}", file=sys.stderr)


def _download_file(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _debug(f"download {url} -> {destination}")
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return destination


def _runtime_python_tag(version: str) -> str:
    match = re.match(r"^\s*(\d+)\.(\d+)", version)
    if not match:
        raise SystemExit(f"Unsupported runtime Python version: {version!r}")
    return f"python{match.group(1)}{match.group(2)}"


def _copy_sources(app_dir: Path) -> None:
    app_dir.mkdir(parents=True, exist_ok=True)
    for relative in SOURCE_ITEMS:
        src = ROOT / relative
        dst = app_dir / relative
        if src.is_dir():
            _copy_tree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _resolve_installed_versions(python_executable: Path | None) -> dict[str, str]:
    if python_executable is None or not python_executable.exists():
        _debug(f"lock python missing: {python_executable}")
        return {}
    _debug(f"resolve versions with: {python_executable}")
    result = subprocess.run(
        [str(python_executable), "-m", "pip", "freeze", "--all"],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        _debug(f"pip freeze failed: rc={result.returncode} stderr={result.stderr.strip()}")
        return {}
    resolved: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        resolved[_normalize_dist_name(name.strip())] = version.strip()
    _debug(f"resolved installed versions: {len(resolved)} entries")
    return resolved


def _iter_runtime_requirements(installed_versions: dict[str, str]) -> list[str]:
    requirements_path = ROOT / "requirements.txt"
    result: list[str] = []
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        marker = ""
        if ";" in line:
            line, marker = line.split(";", 1)
            marker = marker.strip()
        match = PACKAGE_NAME_RE.match(line)
        if not match:
            result.append(raw_line.rstrip())
            continue
        original_name = match.group(1)
        resolved_version = installed_versions.get(_normalize_dist_name(original_name))
        if resolved_version:
            pinned = f"{original_name}=={resolved_version}"
        else:
            try:
                version = metadata.version(original_name)
                pinned = f"{original_name}=={version}"
            except metadata.PackageNotFoundError:
                pinned = raw_line.strip()
        if marker:
            pinned = f"{pinned}; {marker}"
        result.append(pinned)
    return result


def _write_requirements_lock(bootstrap_dir: Path, *, lock_python: Path | None) -> Path:
    lock_path = bootstrap_dir / "requirements-lock.txt"
    lines = _iter_runtime_requirements(_resolve_installed_versions(lock_python))
    lock_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lock_path


def _write_manifest(
    bootstrap_dir: Path,
    *,
    base_python_relative: str,
    runtime_included: bool,
    runtime_python_version: str,
) -> Path:
    manifest_path = bootstrap_dir / "bootstrap_manifest.json"
    runtime_python_tag = _runtime_python_tag(runtime_python_version)
    payload = {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "bootstrap_version": "1",
        "python_version": runtime_python_version,
        "requirements_file": "bootstrap/requirements-lock.txt",
        "entrypoint": "app/run.py",
        "runtime_mode": "embedded",
        "runtime_dir": "runtime/python",
        "base_python": base_python_relative,
        "launch_python": "runtime/python/pythonw.exe",
        "log_file": "logs/bootstrap.log",
        "state_file": "runtime/python/.aline-bootstrap-state.json",
        "critical_imports": CRITICAL_IMPORTS,
        "pip_index_url": DEFAULT_INDEX_URL,
        "extra_index_urls": DEFAULT_EXTRA_INDEX_URLS,
        "get_pip_file": "bootstrap/get-pip.py",
        "embedded_pth": f"runtime/python/{runtime_python_tag}._pth",
        "embedded_site_dir": "runtime/python/Lib/site-packages",
        "runtime_included": runtime_included,
    }
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _copy_runtime(output_dir: Path, *, embed_dir: Path | None, embed_zip: Path | None) -> bool:
    runtime_python_dir = output_dir / "runtime" / "python"
    runtime_python_dir.mkdir(parents=True, exist_ok=True)

    if embed_dir is not None:
        _copy_tree(embed_dir, runtime_python_dir)
        return True

    if embed_zip is not None:
        with zipfile.ZipFile(embed_zip) as archive:
            archive.extractall(runtime_python_dir)
        return True

    note = runtime_python_dir / "RUNTIME_NOT_INCLUDED.txt"
    note.write_text(
        "Windows Python runtime was not bundled into this bootstrap skeleton.\n"
        "Provide --python-embed-dir or --python-embed-zip when building a distributable package.\n",
        encoding="utf-8",
    )
    return False


def _download_runtime_bundle(cache_dir: Path, *, url: str) -> Path:
    archive_name = url.rstrip("/").split("/")[-1]
    destination = cache_dir / archive_name
    if destination.exists():
        _debug(f"reuse cached runtime: {destination}")
        return destination
    return _download_file(url, destination)


def _ensure_get_pip(bootstrap_dir: Path, *, url: str) -> Path:
    destination = bootstrap_dir / "get-pip.py"
    if destination.exists():
        return destination
    return _download_file(url, destination)


def _write_launcher_files(output_dir: Path) -> None:
    bootstrap_dir = output_dir / "bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BOOTSTRAP_TEMPLATE_DIR / "windows_launcher.py", bootstrap_dir / "windows_launcher.py")

    launcher_bat = output_dir / "ALine Launcher.bat"
    launcher_bat.write_text(
        "@echo off\n"
        "setlocal\n"
        "set ROOT=%~dp0\n"
        "if not exist \"%ROOT%runtime\\python\\python.exe\" (\n"
        "  echo Bundled Python runtime is missing.\n"
        "  echo Please re-download the bootstrap package or use the full offline package.\n"
        "  pause\n"
        "  exit /b 1\n"
        ")\n"
        "\"%ROOT%runtime\\python\\python.exe\" \"%ROOT%bootstrap\\windows_launcher.py\"\n"
        "set EXITCODE=%ERRORLEVEL%\n"
        "if not \"%EXITCODE%\"==\"0\" pause\n"
        "exit /b %EXITCODE%\n",
        encoding="utf-8",
    )


def _write_exe_launcher(output_dir: Path, *, launcher_kind: str = "console") -> Path:
    try:
        from distlib.resources import finder
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "distlib is required to build ALine Launcher.exe. "
            "Install it into the build environment first, for example: "
            f"{sys.executable} -m pip install distlib"
        ) from exc

    package = "distlib"
    kind_prefix = "t" if launcher_kind == "console" else "w"
    resource_name = f"{kind_prefix}64.exe"
    resource = finder(package).find(resource_name)
    if not resource:
        raise SystemExit(f"Unable to find distlib launcher resource: {resource_name}")

    shebang = b"#!runtime\\python\\pythonw.exe\r\n"
    main_script = (
        "from pathlib import Path\n"
        "import runpy\n"
        "import sys\n"
        "root = Path(sys.argv[0]).resolve().parent\n"
        "target = root / 'bootstrap' / 'windows_launcher.py'\n"
        "runpy.run_path(str(target), run_name='__main__')\n"
    ).encode("utf-8")

    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
        if source_date_epoch:
            date_time = time.gmtime(int(source_date_epoch))[:6]
            info = ZipInfo(filename="__main__.py", date_time=date_time)
            archive.writestr(info, main_script)
        else:
            archive.writestr("__main__.py", main_script)

    exe_bytes = resource.bytes + shebang + stream.getvalue()
    output_path = output_dir / "ALine Launcher.exe"
    output_path.write_bytes(exe_bytes)
    return output_path


def _archive_output(output_dir: Path) -> Path:
    archive_path = DIST_DIR / f"{output_dir.name}.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as handle:
        for file_path in sorted(output_dir.rglob("*")):
            if file_path.is_file():
                handle.write(file_path, file_path.relative_to(output_dir.parent))
    return archive_path


def build_bootstrap(
    *,
    output_dir: Path,
    python_embed_dir: Path | None,
    python_embed_zip: Path | None,
    lock_python: Path | None,
    runtime_python_version: str,
    runtime_download_url: str | None,
    get_pip_url: str,
    download_cache_dir: Path,
    allow_missing_runtime: bool,
    archive: bool,
) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    app_dir = output_dir / "app"
    _copy_sources(app_dir)
    (output_dir / "logs").mkdir(parents=True, exist_ok=True)
    (output_dir / "user-data" / "config").mkdir(parents=True, exist_ok=True)
    (output_dir / "user-data" / "cache").mkdir(parents=True, exist_ok=True)

    embed_zip_path = python_embed_zip
    if embed_zip_path is None and python_embed_dir is None and runtime_download_url:
        embed_zip_path = _download_runtime_bundle(download_cache_dir, url=runtime_download_url)

    runtime_included = _copy_runtime(output_dir, embed_dir=python_embed_dir, embed_zip=embed_zip_path)
    if not runtime_included and not allow_missing_runtime:
        raise SystemExit(
            "Windows runtime was not provided. Use --python-embed-dir or --python-embed-zip, "
            "or pass --allow-missing-runtime to build a skeleton package."
        )

    bootstrap_dir = output_dir / "bootstrap"
    bootstrap_dir.mkdir(parents=True, exist_ok=True)
    _write_requirements_lock(bootstrap_dir, lock_python=lock_python)
    _ensure_get_pip(bootstrap_dir, url=get_pip_url)
    _write_manifest(
        bootstrap_dir,
        base_python_relative="runtime/python/python.exe",
        runtime_included=runtime_included,
        runtime_python_version=runtime_python_version,
    )
    _write_launcher_files(output_dir)
    _write_exe_launcher(output_dir, launcher_kind="console")

    if archive:
        archive_path = _archive_output(output_dir)
        print(f"[OK] Created {archive_path}")

    print(f"[OK] Bootstrap package staged at {output_dir}")
    return output_dir


def _preserve_invocation_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_absolute():
        return path
    return Path.cwd() / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Windows bootstrap package for ALine.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DIST_DIR / DEFAULT_OUTPUT_NAME,
        help="Directory where the bootstrap package will be staged.",
    )
    parser.add_argument(
        "--python-embed-dir",
        type=Path,
        help="Path to a prepared Windows Python runtime directory to bundle.",
    )
    parser.add_argument(
        "--python-embed-zip",
        type=Path,
        help="Path to a Windows embeddable Python zip to extract into the package.",
    )
    parser.add_argument(
        "--lock-python",
        type=Path,
        default=DEFAULT_LOCK_PYTHON if DEFAULT_LOCK_PYTHON.exists() else None,
        help="Python interpreter used to resolve installed dependency versions for requirements-lock.txt.",
    )
    parser.add_argument(
        "--python-embed-url",
        default=DEFAULT_WINDOWS_EMBED_URL,
        help="Download URL for the Windows embeddable Python runtime zip.",
    )
    parser.add_argument(
        "--runtime-python-version",
        default=DEFAULT_WINDOWS_PYTHON_VERSION,
        help="Python version bundled into the Windows bootstrap runtime.",
    )
    parser.add_argument(
        "--download-cache-dir",
        type=Path,
        default=ROOT / "build" / "bootstrap-cache",
        help="Directory used to cache downloaded bootstrap runtime assets.",
    )
    parser.add_argument(
        "--get-pip-url",
        default=DEFAULT_GET_PIP_URL,
        help="Download URL for get-pip.py.",
    )
    parser.add_argument(
        "--allow-missing-runtime",
        action="store_true",
        help="Allow building a bootstrap skeleton package without a bundled Windows runtime.",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not create the final zip archive; only stage the output directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    _debug(f"args.lock_python={args.lock_python!r}")
    if args.python_embed_dir and args.python_embed_zip:
        raise SystemExit("Use only one of --python-embed-dir or --python-embed-zip.")
    build_bootstrap(
        output_dir=args.output_dir.resolve(),
        python_embed_dir=args.python_embed_dir.resolve() if args.python_embed_dir else None,
        python_embed_zip=args.python_embed_zip.resolve() if args.python_embed_zip else None,
        lock_python=_preserve_invocation_path(args.lock_python),
        runtime_python_version=args.runtime_python_version,
        runtime_download_url=args.python_embed_url if not args.python_embed_dir and not args.python_embed_zip else None,
        get_pip_url=args.get_pip_url,
        download_cache_dir=args.download_cache_dir.resolve(),
        allow_missing_runtime=args.allow_missing_runtime,
        archive=not args.no_archive,
    )


if __name__ == "__main__":
    main()
