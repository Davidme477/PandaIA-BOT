from __future__ import annotations

import argparse
import ctypes
import gc
import json
import os
from pathlib import Path
import sys
import threading
import time

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


def rss_mb() -> float:
    counters = ProcessMemoryCounters(); counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.windll.kernel32; psapi = ctypes.windll.psapi
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / 1024 / 1024


def cpu_time() -> float:
    created = ctypes.c_ulonglong(); exited = ctypes.c_ulonglong()
    kernel_time = ctypes.c_ulonglong(); user_time = ctypes.c_ulonglong()
    kernel_api = ctypes.windll.kernel32; kernel_api.GetCurrentProcess.restype = ctypes.c_void_p
    kernel_api.GetProcessTimes.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    ]
    kernel_api.GetProcessTimes(
        kernel_api.GetCurrentProcess(), ctypes.byref(created), ctypes.byref(exited),
        ctypes.byref(kernel_time), ctypes.byref(user_time),
    )
    return (kernel_time.value + user_time.value) / 10_000_000


def child_processes() -> list[dict[str, object]]:
    import subprocess
    script = (
        f"Get-CimInstance Win32_Process -Filter \"ParentProcessId={os.getpid()}\" | "
        "Select-Object ProcessId,Name | ConvertTo-Json -Compress"
    )
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    output = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True,
        text=True, creationflags=flags, timeout=5,
    ).stdout.strip()
    if not output: return []
    values = json.loads(output)
    return [values] if isinstance(values, dict) else list(values)


def measure(settle_seconds: float) -> dict[str, object]:
    # La sonda nunca usa ni modifica la autorización real de Spotify.
    from services.spotify.local_store import SpotifyLocalStore
    SpotifyLocalStore.has_authorization = lambda _self: False
    SpotifyLocalStore.load = lambda _self: {}

    from app.views.main_window import MainWindow

    started = time.perf_counter()
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    startup = time.perf_counter() - started
    deadline = time.perf_counter() + settle_seconds
    while time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.01)
    cpu_started, wall_started = cpu_time(), time.perf_counter()
    time.sleep(1.0)
    cpu_percent = (cpu_time() - cpu_started) / (time.perf_counter() - wall_started) * 100
    threads = threading.enumerate()
    from services.tts.voice_manager import VoiceManager
    from services.tts.kokoro_service import KokoroService
    from services.tts.windows_tts_service import WindowsTTSService
    objects = gc.get_objects()
    overlay = getattr(window.controller, "overlay_process", None)
    children = ([{"ProcessId": overlay.pid, "Name": "python-overlay"}]
                if overlay is not None and overlay.poll() is None else [])
    result: dict[str, object] = {
        "startup_seconds": round(startup, 3),
        "rss_mb": round(rss_mb(), 1),
        "idle_cpu_percent": round(cpu_percent, 2),
        "python_thread_count": len(threads),
        "python_thread_names": [item.name for item in threads],
        "qt_timer_count": len(window.findChildren(QTimer)),
        "active_qt_timers": sum(item.isActive() for item in window.findChildren(QTimer)),
        "child_processes": children,
        "spotify_workers": sum(item.name == "PandaIA-Spotify" for item in threads),
        "ollama_workers": sum("ollama" in item.name.casefold() for item in threads),
        "tiktok_workers": sum("tiktok" in item.name.casefold() for item in threads),
        "cloudflare_workers": sum("cloudflare" in item.name.casefold() for item in threads),
        "voice_manager_instances": sum(isinstance(item, VoiceManager) for item in objects),
        "kokoro_instances": sum(isinstance(item, KokoroService) for item in objects),
        "kokoro_loaded_pipelines": sum(
            len(item._pipelines) for item in objects if isinstance(item, KokoroService)
        ),
        "windows_tts_instances": sum(isinstance(item, WindowsTTSService) for item in objects),
        "overlay_processes": sum("python" in str(item.get("Name", "")).casefold() for item in children),
        "watchdog_running": window.controller.live_watchdog.isRunning(),
        "spotify_running": window.controller.spotify_runtime.is_running(),
        "cloudflare_running": window.controller.cloudflare_tunnel.process is not None,
    }
    closing = time.perf_counter()
    window.close()
    app.processEvents()
    result["close_seconds"] = round(time.perf_counter() - closing, 3)
    time.sleep(0.5)
    result["threads_after_close"] = [item.name for item in threading.enumerate()]
    result["watchdog_running_after_close"] = window.controller.live_watchdog.isRunning()
    result["spotify_running_after_close"] = window.controller.spotify_runtime.is_running()
    result["cloudflare_running_after_close"] = window.controller.cloudflare_tunnel.process is not None
    result["new_children_after_close"] = (
        [{"ProcessId": overlay.pid, "Name": "python-overlay"}]
        if overlay is not None and overlay.poll() is None else []
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--settle", type=float, default=2.0)
    arguments = parser.parse_args()
    print(json.dumps(measure(arguments.settle), ensure_ascii=False, indent=2))
