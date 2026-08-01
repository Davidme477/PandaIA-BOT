from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path: sys.path.insert(0, str(path))

from core.app_controller import PandaWorker
from services.live.command_router import CommandRouter, normalize_mobile_text
from services.live.comment_response_queue import CommentResponseQueue
from services.ollama.personalities import dashboard_defaults
from services.spotify.request_queue import spotify_defaults
from services.spotify.runtime import SpotifyRuntime


class FakeOllama:
    def __init__(self): self.calls = []
    def generate(self, **values): self.calls.append(values); return "respuesta"


class FakeVoice:
    def __init__(self): self.calls = []
    def speak(self, **values): self.calls.append(values)


class FakeSpotify:
    def search_track(self, _query): raise AssertionError("No debe buscar")


class CommandRouterTests(unittest.TestCase):
    def test_chat_variants_and_clean_text(self):
        router = CommandRouter()
        for value in ("/Hola", "/ Hola", "/   Hola", "／Hola", "／ Hola"):
            self.assertEqual(router.route(value).kind, "chat")
            self.assertEqual(router.route(value).text, "Hola")

    def test_empty_middle_and_url_slashes_are_not_chat(self):
        router = CommandRouter()
        for value in ("/", "/   ", "Hola / Panda", "https://example.com/ruta"):
            expected = "empty_chat" if value.strip().startswith("/") and not value.strip()[1:].strip() else "normal"
            self.assertEqual(router.route(value).kind, expected)

    def test_music_variants_unicode_and_invisible_spaces(self):
        router = CommandRouter()
        variants = (
            "a/Canción bonita", "a/ Canción bonita", "A/Canción bonita",
            "A / Canción bonita", "A /   Canción bonita", "ａ／Canción bonita",
            "a\u200b/\u00a0Canción   bonita",
        )
        for value in variants:
            route = router.route(value)
            self.assertEqual(route.kind, "music", value)
            self.assertEqual(route.text, "Canción bonita")

    def test_music_false_positives_and_empty_queries(self):
        router = CommandRouter()
        for value in ("a Carlos Rivera", "amo esta canción", "https://a/canción", "Ahora cantamos"):
            self.assertEqual(router.route(value).kind, "normal")
        for value in ("a/", "a /", "A /  x"):
            self.assertEqual(router.route(value).kind, "empty_music")

    def test_music_has_priority_and_normalization_is_safe(self):
        route = CommandRouter().route(" A / Carlos   Rivera ")
        self.assertEqual((route.kind, route.text), ("music", "Carlos Rivera"))
        self.assertEqual(normalize_mobile_text("  hola\u200b   mundo  "), "hola mundo")

    def test_worker_routes_before_conversation_queue(self):
        music = []; chat = []; normal = []
        worker = PandaWorker("u", {"command_only_mode": True}, {}, {"command": "a/"},
                             music_callback=lambda user, query: music.append((user, query)))
        worker.response_queue.enqueue_routed_comment = lambda *args: chat.append(args) or True
        worker.response_queue.enqueue_comment = lambda *args: normal.append(args) or True
        worker.forward_comment("Carlos", "A / Carlos Rivera   Si me muero")
        worker.forward_comment("David", "/ Cómo estás")
        worker.forward_comment("Ana", "Hola PandaIA")
        self.assertEqual(music, [("Carlos", "Carlos Rivera Si me muero")])
        self.assertEqual(chat, [("David", "Cómo estás")])
        self.assertEqual(normal, [])
        worker.response_queue.stop()

    def test_chat_reaches_ollama_memory_and_tts_cleanly(self):
        ollama, voice = FakeOllama(), FakeVoice()
        queue = CommentResponseQueue(
            dashboard_settings={"respond_comments": True, "command_only_mode": True, "chat_command": "/",
                "model": "modelo", "use_memory": True},
            tts_settings={"engine": "fake", "voice": "voz", "speed": 1, "volume": 1},
            ollama=ollama, voice_manager=voice,
        )
        queue.set_connected(True)
        self.assertTrue(queue.enqueue_comment("David", "/ Hola PandaIA"))
        deadline = time.time() + 1
        while not voice.calls and time.time() < deadline: time.sleep(.01)
        self.assertIn("@David", ollama.calls[0]["prompt"])
        self.assertIn("Hola PandaIA", ollama.calls[0]["prompt"])
        self.assertNotIn("/ Hola", ollama.calls[0]["prompt"])
        self.assertEqual(queue.memory.snapshot().exchange_count, 1)
        queue.stop()

    def test_normal_comment_never_reaches_ollama_in_command_mode(self):
        ollama = FakeOllama()
        queue = CommentResponseQueue(dashboard_settings={"respond_comments": True, "command_only_mode": True},
            tts_settings={}, ollama=ollama, voice_manager=FakeVoice())
        self.assertFalse(queue.enqueue_comment("Ana", "Hola PandaIA")); time.sleep(.05)
        self.assertEqual(ollama.calls, []); self.assertEqual(queue.memory.snapshot().exchange_count, 0)
        queue.stop()

    def test_music_never_reaches_ollama_or_conversation_memory(self):
        ollama = FakeOllama()
        queue = CommentResponseQueue(
            dashboard_settings={"respond_comments": True, "command_only_mode": True},
            tts_settings={}, ollama=ollama, voice_manager=FakeVoice(),
        )
        queue.set_connected(True)
        self.assertFalse(queue.enqueue_comment("Carlos", "a/Canción bonita"))
        self.assertEqual(ollama.calls, [])
        self.assertEqual(queue.memory.snapshot().exchange_count, 0)
        queue.stop()

    def test_dynamic_chat_command_and_legacy_mode(self):
        worker = PandaWorker("u", {"command_only_mode": True, "chat_command": "/"}, {}, {"command": "a/"})
        routed = []; worker.response_queue.enqueue_routed_comment = lambda _u, text: routed.append(text) or True
        worker.forward_comment("u", "/uno"); worker.update_setting("chat_command", "!"); worker.forward_comment("u", "!dos")
        self.assertEqual(routed, ["uno", "dos"]); worker.response_queue.stop()

    def test_defaults_and_safe_music_migration(self):
        dashboard = dashboard_defaults({})
        self.assertTrue(dashboard["command_only_mode"]); self.assertEqual(dashboard["chat_command"], "/")
        self.assertEqual(spotify_defaults({"command": "M"})["command"], "a/")
        self.assertEqual(spotify_defaults({"command": "tema/"})["command"], "tema/")

    def test_disabled_or_disconnected_spotify_consumes_without_search(self):
        runtime = SpotifyRuntime({"requests_enabled": False}, FakeSpotify())
        runtime.store.load = lambda: {}
        messages = []; runtime.state_changed.connect(lambda _state, message: messages.append(message))
        self.assertTrue(runtime.submit_query("ana", "canción válida"))
        runtime.update_settings({"requests_enabled": True, "only_when_tiktok_connected": False})
        self.assertTrue(runtime.submit_query("ana", "otra canción"))
        runtime.stop()
        self.assertTrue(any("desactivadas" in message for message in messages))
        self.assertTrue(any("desconectado" in message for message in messages))


if __name__ == "__main__": unittest.main()
