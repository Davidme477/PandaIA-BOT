from __future__ import annotations

import os
from pathlib import Path
import sys
import time
import types
import tempfile
import unittest
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path: sys.path.insert(0, str(path))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from app.views.dashboard_view import DashboardView
from app.views.main_window import MainWindow
from core.app_controller import AppController
from services.live.comment_response_queue import CommentResponseQueue
from services.spotify.runtime import SpotifyRuntime
from services.spotify.local_store import SpotifyLocalStore
from services.live_watchdog.runtime import LiveWatchdog
from services.tts.base_engine import TTSEngine, VoiceOption
from services.tts.kokoro_service import KokoroService
from services.tts.voice_manager import (
    VoiceManager, get_voice_manager, reset_shared_voice_manager,
)
from services.tiktok import gift_image_service


class CountingEngine(TTSEngine):
    def __init__(self, engine_id): self.engine_id = engine_id; self.calls = 0
    @property
    def display_name(self): return self.engine_id
    def is_available(self): return True
    def list_voices(self): return [VoiceOption("v", "V", "N", "", "Español")]
    def get_voice(self, _code): return self.list_voices()[0]
    def preview(self, **_values): self.calls += 1; return "ok"
    def speak(self, **_values): self.calls += 1


class FakeSpotify:
    def search_track(self, _query): return None
    def playback(self): return {}
    def playback_queue(self): return {"currently_playing": None, "queue": []}


class FakeProcess:
    pid = 1234
    def __init__(self): self.running = True
    def poll(self): return None if self.running else 0
    def terminate(self): self.running = False
    def wait(self, timeout=None): return 0


class PerformanceLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def tearDown(self): reset_shared_voice_manager()

    def test_kokoro_is_lazy_and_pipeline_loads_once(self):
        created = []
        class Pipeline:
            def __init__(self, lang_code): created.append(lang_code)
        engine = KokoroService()
        self.assertEqual(engine._pipelines, {})
        with patch.object(KokoroService, "is_installed", return_value=True), patch.dict(
            sys.modules, {"kokoro": types.SimpleNamespace(KPipeline=Pipeline)}
        ):
            self.assertIs(engine._get_pipeline("e"), engine._get_pipeline("e"))
        self.assertEqual(created, ["e"])

    def test_windows_engine_never_touches_kokoro(self):
        kokoro, windows = CountingEngine("kokoro"), CountingEngine("windows")
        manager = VoiceManager([kokoro, windows])
        manager.preview(engine="windows", text="hola", voice="v", speed=1, volume=1)
        self.assertEqual(kokoro.calls, 0); self.assertEqual(windows.calls, 1)

    def test_voice_manager_and_speech_queue_are_shared(self):
        first = get_voice_manager(); second = get_voice_manager()
        queue = CommentResponseQueue(dashboard_settings={}, tts_settings={})
        self.assertIs(first, second); self.assertIs(queue.voice_manager, first)
        queue.stop()

    def test_spotify_worker_is_lazy_unique_and_restartable(self):
        runtime = SpotifyRuntime({}, FakeSpotify())
        self.assertFalse(runtime.is_running())
        runtime.submit_local_request("artista canción")
        deadline = time.time() + 1
        while not runtime.is_running() and time.time() < deadline: time.sleep(.01)
        first = runtime.thread; runtime._ensure_thread(); self.assertIs(runtime.thread, first)
        runtime.stop(); self.assertFalse(runtime.is_running())
        runtime.submit_local_request("otra canción")
        self.assertIsNot(runtime.thread, first); runtime.stop()

    def test_overlay_start_is_guarded_and_cloudflare_is_manual(self):
        controller = AppController.__new__(AppController); QObject.__init__(controller)
        from threading import Lock
        controller._overlay_start_lock = Lock(); controller.overlay_process = None
        controller.overlay_access_token = "test-only"; created = []
        with patch("core.app_controller.PandaWorker.check_url", return_value=False), patch(
            "core.app_controller.subprocess.Popen", side_effect=lambda *_a, **_k: created.append(FakeProcess()) or created[-1]
        ):
            controller.start_overlay_server(); controller.start_overlay_server()
        self.assertEqual(len(created), 1)

        controller._overlay_start_thread = None
        with patch.object(controller, "start_overlay_server", side_effect=lambda: time.sleep(.15)):
            started = time.perf_counter(); controller.start_overlay_async()
            self.assertLess(time.perf_counter() - started, .05)
            controller._overlay_start_thread.join(1)

        with patch.object(AppController, "start_overlay_server"), patch(
            "services.overlay.cloudflare_tunnel.CloudflareTunnel.start"
        ) as tunnel_start, patch.object(DashboardView, "load_ollama_models"), patch.object(
            SpotifyLocalStore, "has_authorization", return_value=False
        ), patch.object(LiveWatchdog, "start"):
            window = MainWindow(); self.assertFalse(tunnel_start.called); window.close()

    def test_startup_does_not_refresh_ollama_or_duplicate_timers(self):
        with patch.object(AppController, "start_overlay_server"), patch.object(
            DashboardView, "load_ollama_models"
        ) as refresh, patch.object(SpotifyLocalStore, "has_authorization", return_value=False), patch.object(
            LiveWatchdog, "start"
        ):
            window = MainWindow()
            self.assertFalse(refresh.called)
            before = len(window.findChildren(QTimer))
            for _ in range(5): window.resize_timer.start()
            self.assertEqual(len(window.findChildren(QTimer)), before)
            window.close()

    def test_disabled_watchdog_and_cloudflare_do_not_start(self):
        settings = {
            "dashboard": {}, "tts": {"engine": "windows"}, "gifts": {},
            "live_watchdog": {"enabled": False},
        }
        with patch("core.app_controller.read_settings", return_value=settings), patch.object(
            LiveWatchdog, "start"
        ) as watchdog_start, patch("services.overlay.cloudflare_tunnel.CloudflareTunnel.start") as tunnel_start:
            controller = AppController()
            self.assertFalse(watchdog_start.called)
            self.assertFalse(tunnel_start.called)
            self.assertIsNone(controller.overlay_process)
            self.assertFalse(controller.spotify_runtime.is_running())
            controller.shutdown()

    def test_gift_cache_cleanup_is_bounded_and_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "gifts"; cache.mkdir()
            old = cache / "old.png"; old.write_bytes(b"image")
            unrelated = Path(directory) / "custom-animation.json"; unrelated.write_text("keep")
            old_time = time.time() - gift_image_service.MAX_CACHE_AGE_SECONDS - 10
            os.utime(old, (old_time, old_time))
            with patch.object(gift_image_service, "GIFT_CACHE_DIR", cache):
                gift_image_service._last_prune = 0
                self.assertEqual(gift_image_service.prune_gift_cache(), 1)
            self.assertFalse(old.exists()); self.assertTrue(unrelated.exists())


if __name__ == "__main__": unittest.main()
