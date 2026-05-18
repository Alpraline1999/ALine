"""Windows bootstrap launcher for ALine."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent
BOOTSTRAP_DIR = PACKAGE_ROOT / "bootstrap"


class BootstrapError(RuntimeError):
    """Raised when bootstrap cannot proceed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_manifest() -> dict[str, object]:
    manifest_path = BOOTSTRAP_DIR / "bootstrap_manifest.json"
    if not manifest_path.exists():
        raise BootstrapError(f"bootstrap manifest not found: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


MANIFEST = _load_manifest()
LOG_PATH = PACKAGE_ROOT / str(MANIFEST["log_file"])
BASE_PYTHON = PACKAGE_ROOT / str(MANIFEST["base_python"])
REQUIREMENTS_FILE = PACKAGE_ROOT / str(MANIFEST["requirements_file"])
ENTRYPOINT = PACKAGE_ROOT / str(MANIFEST["entrypoint"])
STATE_PATH = PACKAGE_ROOT / str(MANIFEST["state_file"])
RUNTIME_MODE = str(MANIFEST.get("runtime_mode") or "venv").strip().lower()
LAUNCH_PYTHON = PACKAGE_ROOT / str(MANIFEST.get("launch_python") or MANIFEST["base_python"])
GET_PIP_PATH = PACKAGE_ROOT / str(MANIFEST.get("get_pip_file") or "bootstrap/get-pip.py")
ENV_DIR = PACKAGE_ROOT / str(MANIFEST.get("runtime_dir") or "runtime/env")
ENV_PYTHON = ENV_DIR / "Scripts" / "python.exe"
EMBED_PTH = PACKAGE_ROOT / str(MANIFEST.get("embedded_pth") or "")
EMBED_SITE_DIR = PACKAGE_ROOT / str(MANIFEST.get("embedded_site_dir") or "runtime/python/Lib/site-packages")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    _ensure_parent(LOG_PATH)
    line = f"[{_utc_now()}] {message}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    log("RUN " + " ".join(cmd))
    result = subprocess.run(cmd, text=True, capture_output=True)
    if result.stdout:
        log("STDOUT " + result.stdout.strip())
    if result.stderr:
        log("STDERR " + result.stderr.strip())
    if check and result.returncode != 0:
        raise BootstrapError(f"command failed ({result.returncode}): {' '.join(cmd)}")
    return result


def _requirements_hash() -> str:
    return hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()


def _read_state() -> dict[str, object]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_state() -> None:
    _ensure_parent(STATE_PATH)
    payload = {
        "app_version": MANIFEST["app_version"],
        "requirements_hash": _requirements_hash(),
        "updated_at": _utc_now(),
    }
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _env_is_current() -> bool:
    python_path = BASE_PYTHON if RUNTIME_MODE == "embedded" else ENV_PYTHON
    if not python_path.exists():
        return False
    state = _read_state()
    return (
        state.get("app_version") == MANIFEST["app_version"]
        and state.get("requirements_hash") == _requirements_hash()
    )


def _ensure_base_runtime() -> None:
    if not BASE_PYTHON.exists():
        raise BootstrapError(
            "bundled Python runtime is missing. Re-download the Windows bootstrap package "
            "or use the full offline package."
        )


def _create_env() -> None:
    if ENV_DIR.exists():
        log(f"reuse existing env directory: {ENV_DIR}")
    else:
        ENV_DIR.mkdir(parents=True, exist_ok=True)
    _run([str(BASE_PYTHON), "-m", "venv", str(ENV_DIR)])


def _ensure_pip() -> None:
    python_path = BASE_PYTHON if RUNTIME_MODE == "embedded" else ENV_PYTHON
    if python_path.exists():
        pip_result = _run([str(python_path), "-m", "pip", "--version"], check=False)
        if pip_result.returncode == 0:
            return
    ensurepip_result = _run([str(python_path), "-m", "ensurepip", "--upgrade"], check=False)
    if ensurepip_result.returncode == 0:
        return
    if not GET_PIP_PATH.exists():
        raise BootstrapError("pip is unavailable and bootstrap/get-pip.py is missing")
    _run([str(python_path), str(GET_PIP_PATH)])


def _ensure_embedded_site() -> None:
    if not EMBED_PTH:
        raise BootstrapError("embedded runtime mode requires embedded_pth in manifest")
    if not EMBED_PTH.exists():
        raise BootstrapError(f"embedded runtime ._pth file is missing: {EMBED_PTH}")
    EMBED_SITE_DIR.mkdir(parents=True, exist_ok=True)
    existing = [line.rstrip("\r\n") for line in EMBED_PTH.read_text(encoding="utf-8").splitlines()]
    wanted = ["python312.zip", ".", "Lib", "Lib/site-packages", "import site"]
    merged: list[str] = []
    seen: set[str] = set()
    for line in existing + wanted:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text == "#import site":
            text = "import site"
        if text not in seen:
            merged.append(text)
            seen.add(text)
    EMBED_PTH.write_text("\n".join(merged) + "\n", encoding="utf-8")


def _pip_install_args() -> list[str]:
    python_path = BASE_PYTHON if RUNTIME_MODE == "embedded" else ENV_PYTHON
    args = [str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)]
    primary = str(MANIFEST.get("pip_index_url") or "").strip()
    if primary:
        args.extend(["--index-url", primary])
    for extra in MANIFEST.get("extra_index_urls", []):
        extra_text = str(extra or "").strip()
        if extra_text:
            args.extend(["--extra-index-url", extra_text])
    return args


def _install_requirements() -> None:
    python_path = BASE_PYTHON if RUNTIME_MODE == "embedded" else ENV_PYTHON
    _run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    _run(_pip_install_args())


def _verify_runtime() -> None:
    modules = [str(item) for item in MANIFEST.get("critical_imports", [])]
    snippet = "\n".join([f"import {name}" for name in modules])
    python_path = BASE_PYTHON if RUNTIME_MODE == "embedded" else ENV_PYTHON
    _run([str(python_path), "-c", snippet])


def _launch_app() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("QT_QPA_PLATFORM", "windows")
    cmd = [str(LAUNCH_PYTHON), str(ENTRYPOINT)]
    log("LAUNCH " + " ".join(cmd))
    return subprocess.call(cmd, env=env, cwd=str(PACKAGE_ROOT))


def main() -> int:
    try:
        log("bootstrap start")
        _ensure_base_runtime()
        if not _env_is_current():
            log("runtime env is missing or stale; rebuilding")
            if RUNTIME_MODE == "embedded":
                _ensure_embedded_site()
            else:
                _create_env()
            _ensure_pip()
            _install_requirements()
            _verify_runtime()
            _write_state()
        else:
            log("runtime env is current")
        return _launch_app()
    except BootstrapError as exc:
        log("FATAL " + str(exc))
        print()
        print("ALine bootstrap failed.")
        print(str(exc))
        print(f"See log: {LOG_PATH}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
