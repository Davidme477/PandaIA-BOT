from __future__ import annotations

import importlib.util
import json
import socket
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from core.app_paths import get_paths, initialize_user_data


def check_url(url: str, timeout: float = 0.7) -> bool:
    try:
        with urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (URLError, TimeoutError, OSError):
        return False


def overlay_port_available() -> bool:
    if check_url("http://127.0.0.1:5050/health"):
        return True
    sock = socket.socket()
    try:
        return sock.connect_ex(("127.0.0.1", 5050)) != 0
    finally:
        sock.close()


def collect_first_run_diagnostics() -> dict[str, object]:
    migration = initialize_user_data()
    paths = get_paths()
    models: list[str] = []
    try:
        with urlopen("http://127.0.0.1:11434/api/tags", timeout=0.7) as response:
            payload = json.loads(response.read().decode("utf-8"))
            models = [str(item.get("name", "")) for item in payload.get("models", []) if item.get("name")]
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        pass
    return {
        "data_root": str(paths.root),
        "writable": bool(migration["writable"]),
        "migrated": list(migration["migrated"]),
        "ollama": bool(models),
        "ollama_models": models,
        "windows_sapi": sys.platform == "win32",
        "kokoro": all(importlib.util.find_spec(name) is not None for name in ("kokoro", "numpy", "soundfile")),
        "overlay_port": overlay_port_available(),
    }


def marker_path() -> Path:
    return get_paths().config / "first_run.json"


def first_run_pending() -> bool:
    return not marker_path().exists()


def complete_first_run() -> None:
    marker_path().write_text(json.dumps({"completed": True}, indent=2) + "\n", encoding="utf-8")
