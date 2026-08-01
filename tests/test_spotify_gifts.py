from __future__ import annotations

from email.message import Message
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path: sys.path.insert(0, str(path))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.views.dashboard_view import DashboardView
from app.views.main_window import MainWindow
from core.app_controller import PandaWorker
from overlay.server import app, event_queue, queue_lock
from services.overlay.events import OVERLAY_URL, sanitize_event, sanitize_text
from services.overlay.gift_animations import GiftAnimationManager
from services.spotify.client import SpotifyAPIError, SpotifyClient
from services.spotify.local_store import SpotifyLocalStore
from services.spotify.models import RequestStatus, Track
from services.spotify.oauth import code_challenge, generate_code_verifier, refresh_access_token, validate_state
from services.spotify.request_queue import MusicRequestQueue, music_query
from services.spotify.runtime import SpotifyRuntime
from services.tiktok.live_state import LiveState


class Response:
    def __init__(self, data: object, status: int = 200):
        self.data = json.dumps(data).encode(); self.status = status
    def __enter__(self): return self
    def __exit__(self, *_args): return None
    def read(self): return self.data


class FakeSpotify:
    def __init__(self, track: Track | None = None):
        self.track = track; self.searches = []; self.queued = []
    def search_track(self, query): self.searches.append(query); return self.track
    def add_to_queue(self, uri, device_id=""): self.queued.append((uri, device_id))
    def playback(self): return {}
    def playback_queue(self): return {"currently_playing": None, "queue": []}


class SpotifyGiftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def track(self, *, uri="spotify:track:1", explicit=False):
        return Track(uri, "Si me muero", "Carlos Rivera", 201000, explicit)

    def test_music_command_parser_is_strict(self):
        self.assertEqual(music_query("a/Carlos Rivera Si me muero"), "Carlos Rivera Si me muero")
        self.assertEqual(music_query("A / canción"), "canción")
        for value in ("a Carlos", "amo esta canción", "a/", "a /", "am canción"):
            self.assertIsNone(music_query(value), value)

    def test_music_command_is_consumed_before_ollama(self):
        worker = PandaWorker("u", {"command_only_mode": True}, {}, {"command": "a/"}, music_callback=lambda _u, _text: True)
        called = []
        worker.response_queue.enqueue = lambda *args: called.append(args)
        worker.forward_comment("ana", "a/artista canción")
        self.assertEqual(called, [])
        worker.forward_comment("ana", "mensaje normal")
        self.assertEqual(called, [])
        worker.response_queue.stop()

    def test_queue_limits_cooldown_duplicates_explicit_and_capacity(self):
        queue = MusicRequestQueue({"max_pending": 2, "max_per_user": 1, "user_cooldown": 120})
        queue.add("ana", self.track())
        self.assertIn("máximo", queue.validate("ana", self.track(uri="spotify:2")))
        cooldown = MusicRequestQueue({"max_pending": 5, "max_per_user": 5, "user_cooldown": 120, "block_duplicates": False})
        cooldown.add("ana", self.track()); self.assertIn("Espera", cooldown.validate("ana", self.track(uri="spotify:2")))
        duplicate = MusicRequestQueue({"max_pending": 5, "max_per_user": 5, "user_cooldown": 0})
        duplicate.add("ana", self.track()); self.assertIn("ya está", duplicate.validate("bea", self.track()))
        explicit = MusicRequestQueue({"allow_explicit": False}); self.assertIn("explícito", explicit.validate("ana", self.track(explicit=True)))
        capacity = MusicRequestQueue({"max_pending": 1, "max_per_user": 5, "user_cooldown": 0})
        capacity.add("ana", self.track()); self.assertIn("llena", capacity.validate("bea", self.track(uri="spotify:2")))

    def test_queue_is_thread_safe_and_states_are_explicit(self):
        queue = MusicRequestQueue({"max_pending": 100, "max_per_user": 100, "user_cooldown": 0, "block_duplicates": False})
        threads = [threading.Thread(target=queue.add, args=(f"u{i}", self.track(uri=f"spotify:{i}"))) for i in range(30)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(queue.snapshot()), 30)
        first = queue.snapshot()[0]
        for status in RequestStatus:
            queue.update(first.request_id, status); self.assertEqual(queue.snapshot()[0].status, status)

    def test_search_without_results_is_rejected(self):
        runtime = SpotifyRuntime({"requests_enabled": True, "only_when_tiktok_connected": False}, FakeSpotify(None))
        messages = []; runtime.state_changed.connect(lambda state, message: messages.append((state, message)))
        self.assertTrue(runtime.submit_comment("ana", "a/canción inexistente"))
        deadline = time.time() + 2
        while not messages and time.time() < deadline: self.app.processEvents(); time.sleep(.01)
        runtime.stop(); self.assertIn("No se encontró", messages[0][1])

    def test_pkce_and_state(self):
        verifier = generate_code_verifier(); challenge = code_challenge(verifier)
        self.assertGreaterEqual(len(verifier), 43); self.assertNotIn("=", challenge)
        self.assertTrue(validate_state("seguro", "seguro")); self.assertFalse(validate_state("seguro", "falso"))

    def test_refresh_token_and_atomic_private_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SpotifyLocalStore(Path(directory) / "spotify_local.json")
            store.save({"client_id": "id", "access_token": "secret", "refresh_token": "refresh", "ignored": "x"})
            self.assertNotIn("ignored", store.load())
            refreshed = refresh_access_token("id", "refresh", opener=lambda *_a, **_k: Response({"access_token": "new", "expires_in": 3600}))
            self.assertEqual(refreshed["access_token"], "new")
            store.clear_tokens(); self.assertEqual(store.load(), {"client_id": "id"})

    def test_http_errors_are_sanitized_and_cover_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SpotifyLocalStore(Path(directory) / "local.json")
            store.save({"client_id": "client-secret-value", "access_token": "token-secret-value", "expires_at": time.time() + 1000})
            for status in (401, 403, 404, 429):
                headers = Message(); headers["Retry-After"] = "3"
                def failing(*_args, current=status, **_kwargs):
                    raise HTTPError("url", current, "failure", headers, None)
                output = io.StringIO()
                with patch("sys.stdout", output):
                    with self.assertRaises(SpotifyAPIError) as caught: SpotifyClient(store, failing).request("GET", "/me")
                self.assertEqual(caught.exception.status, status)
                self.assertNotIn("token-secret-value", output.getvalue() + str(caught.exception))
            client = SpotifyClient(store, lambda *_a, **_k: (_ for _ in ()).throw(URLError("offline")))
            with self.assertRaises(SpotifyAPIError): client.request("GET", "/me")

    def test_premium_and_missing_device_are_distinct(self):
        class Client(SpotifyClient):
            def __init__(self, premium=True, device=None): self.premium, self.device = premium, device
            def request(self, _method, path, data=None):
                if path == "/me": return {"id": "a", "product": "premium" if self.premium else "free"}
                return {"devices": [self.device] if self.device else []}
        with self.assertRaises(SpotifyAPIError) as error: Client(False).account_and_device()
        self.assertEqual(error.exception.status, 403)
        self.assertIsNone(Client(True).account_and_device()["device"])
        self.assertEqual(Client(True, {"id": "d", "is_active": True}).account_and_device()["device"]["id"], "d")

    def test_gift_animation_enable_disable_test_and_stats(self):
        sent = []; manager = GiftAnimationManager(sender=lambda event: sent.append(event) or True)
        state = LiveState(); before = state.snapshot()
        self.assertTrue(manager.handle_gift(gift_id="5655", gift_name="Rose", quantity=2, username="ana", test=True))
        self.assertTrue(sent[0]["test"]); self.assertEqual(state.snapshot(), before)
        manager.update_settings({"animations_enabled": False})
        self.assertFalse(manager.handle_gift(gift_id="5655", gift_name="Rose", quantity=1, username="ana"))

    def test_overlay_accepts_only_gifts_without_music_using_queue_space(self):
        self.assertEqual(OVERLAY_URL, "http://127.0.0.1:5050/overlay")
        self.assertNotIn("<", sanitize_text("<script>alert(1)</script>"))
        with self.assertRaises(ValueError): sanitize_event({"type": "music_request", "title": "Tema"})
        with queue_lock: event_queue.clear()
        with queue_lock: event_queue.append({"type": "gift", "gift_id": "1", "gift_name": "Rose"})
        for event_type in ("music_request", "playback"):
            response = app.test_client().post("/api/events", json={"type": event_type, "title": "Tema", "username": "ana"})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json()["ok"], False)
        event = app.test_client().get("/api/events/next").get_json()["event"]
        self.assertEqual(event["type"], "gift")
        self.assertIsNone(app.test_client().get("/api/events/next").get_json()["event"])

    def test_accidental_music_in_queue_is_discarded_before_gift(self):
        with queue_lock:
            event_queue.clear(); event_queue.append({"type": "music_request", "title": "No mostrar"})
            event_queue.append({"type": "gift", "gift_id": "2", "gift_name": "TikTok"})
        payload = app.test_client().get("/api/events/next").get_json()
        self.assertEqual(payload["event"]["type"], "gift"); self.assertEqual(payload["remaining_events"], 0)

    def test_overlay_template_is_transparent_and_has_no_music_module(self):
        html = app.test_client().get("/overlay").get_data(as_text=True)
        css = (PROJECT_DIR / "overlay/static/css/overlay.css").read_text(encoding="utf-8")
        self.assertNotIn("music-module", html); self.assertIn("background: transparent", css)

    def test_gift_and_test_gift_reach_overlay(self):
        from unittest.mock import patch
        cached = Path("cache/gifts/rose.png")
        with patch("overlay.server.get_gift_image", return_value=cached), patch(
            "overlay.server.get_overlay_image_url", return_value="/gift-assets/rose.png"
        ):
            with queue_lock: event_queue.clear()
            response = app.test_client().post("/api/events", json={"type":"gift","gift_id":"1","gift_name":"Rose","quantity":2})
            self.assertEqual(response.status_code, 200); self.assertEqual(app.test_client().get("/api/events/next").get_json()["event"]["type"], "gift")
            response = app.test_client().post("/api/test/gift", json={"gift_id":"1","gift_name":"Rose"})
            self.assertEqual(response.status_code, 200); self.assertEqual(app.test_client().get("/api/events/next").get_json()["event"]["type"], "gift")

    def test_spotify_local_file_is_ignored(self):
        ignore = (PROJECT_DIR / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("config/spotify_local.json", ignore)

    def test_runtime_closes_cleanly(self):
        runtime = SpotifyRuntime({}, FakeSpotify())
        runtime.stop(); self.assertFalse(runtime.thread.is_alive())

    def test_real_spotify_queue_endpoint_and_origin_mapping(self):
        captured = []
        with tempfile.TemporaryDirectory() as directory:
            store = SpotifyLocalStore(Path(directory) / "local.json")
            store.save({"access_token": "token", "expires_at": time.time() + 1000})
            def opener(request, **_kwargs):
                captured.append(request.full_url)
                return Response({"currently_playing": None, "queue": []})
            self.assertEqual(SpotifyClient(store, opener).playback_queue()["queue"], [])
        self.assertEqual(captured, ["https://api.spotify.com/v1/me/player/queue"])
        runtime = SpotifyRuntime({}, FakeSpotify())
        request = runtime.requests.add("ana", self.track())
        emitted = []; runtime.spotify_queue_changed.connect(emitted.append)
        runtime._publish_spotify_queue({"currently_playing": {"uri": request.track.uri, "name": request.track.title,
            "artists": [{"name": request.track.artist}], "duration_ms": request.track.duration_ms},
            "queue": [{"uri": "spotify:manual", "name": "Manual", "artists": [{"name": "Artista"}], "duration_ms": 1000}]})
        self.app.processEvents(); runtime.stop()
        self.assertIn("@ana", emitted[0][0]["origin"])
        self.assertEqual(emitted[0][1]["origin"], "Añadida manualmente en Spotify")

    def test_local_test_request_uses_spotify_worker_only(self):
        fake = FakeSpotify(self.track())
        runtime = SpotifyRuntime({}, fake)
        self.assertTrue(runtime.submit_local_request("Carlos Rivera Si me muero"))
        deadline = time.time() + 2
        while not runtime.requests.snapshot() and time.time() < deadline: self.app.processEvents(); time.sleep(.01)
        runtime.stop(); self.assertEqual(runtime.requests.snapshot()[0].username, "Prueba local")

    def test_gifts_view_is_dark_responsive_and_reachable(self):
        from main import load_stylesheet
        self.app.setStyleSheet(load_stylesheet())
        with patch.object(DashboardView, "load_ollama_models", lambda self: None): window = MainWindow()
        window.resize(1366, 768); window.show(); window.change_page(6); self.app.processEvents()
        self.assertIs(window.pages.currentWidget(), window.gifts_view)
        self.assertEqual(window.gifts_view.horizontalScrollBarPolicy().value, 1)
        color = window.gifts_view.viewport().grab().toImage().pixelColor(2, 2)
        self.assertLess(color.red() + color.green() + color.blue(), 180)
        self.assertEqual(window.gifts_view.spotify_queue_table.columnCount(), 5)
        self.assertEqual(window.gifts_view.clear_queue.text(), "Limpiar solicitudes pendientes")
        self.assertEqual(window.gifts_view.pause_track.text(), "Pausar")
        self.assertEqual(window.gifts_view.resume_track.text(), "Reanudar")
        window.close()


if __name__ == "__main__": unittest.main()
