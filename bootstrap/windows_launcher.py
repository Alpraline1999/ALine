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
ENV_DIR = PACKAGE_ROOT / str(MANIFEST["runtime_dir"])
ENV_PYTHON = ENV_DIR / "Scripts" / "python.exe"
REQUIREMENTS_FILE = PACKAGE_ROOT / str(MANIFEST["requirements_file"])
ENTRYPOINT = PACKAGE_ROOT / str(MANIFEST["entrypoint"])
STATE_PATH = PACKAGE_ROOT / str(MANIFEST["state_file"])


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
    if not ENV_PYTHON.exists():
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
    if ENV_PYTHON.exists():
        pip_result = _run([str(ENV_PYTHON), "-m", "pip", "--version"], check=False)
        if pip_result.returncode == 0:
            return
    ensurepip_result = _run([str(ENV_PYTHON), "-m", "ensurepip", "--upgrade"], check=False)
    if ensurepip_result.returncode == 0:
        return
    get_pip = BOOTSTRAP_DIR / "get-pip.py"
    if not get_pip.exists():
        raise BootstrapError("pip is unavailable and bootstrap/get-pip.py is missing")
    _run([str(ENV_PYTHON), str(get_pip)])


def _pip_install_args() -> list[str]:
    args = [str(ENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)]
    primary = str(MANIFEST.get("pip_index_url") or "").strip()
    if primary:
        args.extend(["--index-url", primary])
    for extra in MANIFEST.get("extra_index_urls", []):
        extra_text = str(extra or "").strip()
        if extra_text:
            args.extend(["--extra-index-url", extra_text])
    return args


def _install_requirements() -> None:
    _run([str(ENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"])
    _run(_pip_install_args())


def _verify_runtime() -> None:
    modules = [str(item) for item in MANIFEST.get("critical_imports", [])]
    snippet = "\n".join([f"import {name}" for name in modules])
    _run([str(ENV_PYTHON), "-c", snippet])


def _launch_app() -> int:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("QT_QPA_PLATFORM", "windows")
    cmd = [str(ENV_PYTHON), str(ENTRYPOINT)]
    log("LAUNCH " + " ".join(cmd))
    return subprocess.call(cmd, env=env, cwd=str(PACKAGE_ROOT))


def main() -> int:
    try:
        log("bootstrap start")
        _ensure_base_runtime()
        if not _env_is_current():
            log("runtime env is missing or stale; rebuilding")
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
