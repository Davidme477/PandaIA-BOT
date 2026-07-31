from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from services.live.comment_response_queue import CommentResponseQueue
from services.live.runtime_controls import RuntimeControls, stop_button_enabled
from services.live.session_memory import SessionMemory


class FakeOllama:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def generate(self, *, model: str, prompt: str, system_prompt: str = "") -> str:
        self.calls.append({"model": model, "prompt": prompt, "system": system_prompt})
        return f"respuesta-{len(self.calls)}"


class FakeVoice:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def speak(self, **values: object) -> None:
        self.calls.append(values)


def wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("No se alcanzó el estado esperado")


class BotControlsTests(unittest.TestCase):
    def make_queue(self, **settings: object) -> tuple[CommentResponseQueue, FakeOllama, FakeVoice]:
        dashboard = {
            "model": "modelo",
            "personality": "Alegre",
            "language": "Español",
            "respond_comments": True,
            "read_gifts": True,
            "use_memory": True,
            "automatic_responses": True,
            "autonomous_mode": False,
        }
        dashboard.update(settings)
        ollama, voice = FakeOllama(), FakeVoice()
        queue = CommentResponseQueue(
            dashboard_settings=dashboard,
            tts_settings={"engine": "fake", "voice": "voz", "speed": 1.0, "volume": 1.0},
            ollama=ollama,
            voice_manager=voice,
            autonomous_interval=0.04,
        )
        return queue, ollama, voice

    def test_respond_comments_can_be_enabled_and_disabled_live(self) -> None:
        queue, ollama, _ = self.make_queue(respond_comments=False)
        self.assertFalse(queue.enqueue_comment("ana", "hola"))
        queue.update_setting("respond_comments", True)
        self.assertTrue(queue.enqueue_comment("ana", "hola otra vez"))
        wait_for(lambda: len(ollama.calls) == 1)
        queue.stop()

    def test_automatic_responses_answers_every_comment(self) -> None:
        queue, ollama, _ = self.make_queue(automatic_responses=True)
        queue.enqueue_comment("ana", "comentario normal")
        wait_for(lambda: len(ollama.calls) == 1)
        queue.stop()

    def test_manual_filter_skips_normal_comment(self) -> None:
        queue, ollama, _ = self.make_queue(automatic_responses=False)
        self.assertFalse(queue.enqueue_comment("ana", "comentario normal"))
        queue.stop()
        self.assertEqual(ollama.calls, [])

    def test_manual_filter_accepts_panda_mention_and_question(self) -> None:
        queue, ollama, _ = self.make_queue(automatic_responses=False)
        queue.enqueue_comment("ana", "PandaIA salúdame")
        queue.enqueue_comment("bea", "¿Cómo estás?")
        wait_for(lambda: len(ollama.calls) == 2)
        queue.stop()

    def test_read_gifts_can_be_enabled_and_disabled_live(self) -> None:
        queue, ollama, _ = self.make_queue(read_gifts=False)
        self.assertFalse(queue.enqueue_gift("ana", "Rosa", 2))
        queue.update_setting("read_gifts", True)
        self.assertTrue(queue.enqueue_gift("ana", "Rosa", 2))
        wait_for(lambda: len(ollama.calls) == 1)
        queue.stop()
        self.assertIn("@ana", ollama.calls[0]["prompt"])
        self.assertIn("2 x Rosa", ollama.calls[0]["prompt"])

    def test_streaking_gift_does_not_enqueue_duplicate_thanks(self) -> None:
        queue, ollama, _ = self.make_queue()
        self.assertFalse(queue.enqueue_gift("ana", "Rosa", 1, streaking=True))
        queue.enqueue_gift("ana", "Rosa", 5, streaking=False)
        wait_for(lambda: len(ollama.calls) == 1)
        queue.stop()

    def test_fifo_includes_comments_gifts_and_autonomous_work(self) -> None:
        queue, ollama, voice = self.make_queue(autonomous_mode=True)
        queue.set_connected(True)
        queue.enqueue_comment("ana", "hola")
        queue.enqueue_gift("bea", "Rosa", 1)
        wait_for(lambda: len(voice.calls) >= 3)
        queue.stop()
        self.assertIn("@ana", ollama.calls[0]["prompt"])
        self.assertIn("Agradece a @bea", ollama.calls[1]["prompt"])
        self.assertIn("intervención espontánea", ollama.calls[2]["prompt"])

    def test_memory_is_separate_and_limited(self) -> None:
        memory = SessionMemory(max_users=2, max_exchanges=2)
        memory.add("ana", "a1", "r1")
        memory.add("ana", "a2", "r2")
        memory.add("ana", "a3", "r3")
        memory.add("bea", "b1", "rb1")
        memory.add("cora", "c1", "rc1")
        self.assertNotIn("a1", memory.context("ana"))
        self.assertEqual(memory.context("bea"), "Usuario: b1\nPandaIA: rb1")
        self.assertEqual(memory.user_count(), 2)

    def test_disabled_memory_is_not_saved_or_sent(self) -> None:
        queue, ollama, _ = self.make_queue(use_memory=False)
        queue.enqueue_comment("ana", "hola")
        wait_for(lambda: len(ollama.calls) == 1)
        queue.stop()
        self.assertNotIn("Contexto previo", ollama.calls[0]["prompt"])
        self.assertEqual(queue.memory.user_count(), 0)

    def test_enabled_memory_is_sent_only_to_same_user(self) -> None:
        queue, ollama, _ = self.make_queue(use_memory=True)
        queue.enqueue_comment("ana", "primer mensaje")
        wait_for(lambda: len(ollama.calls) == 1)
        queue.enqueue_comment("bea", "mensaje de bea")
        wait_for(lambda: len(ollama.calls) == 2)
        queue.enqueue_comment("ana", "segundo mensaje")
        wait_for(lambda: len(ollama.calls) == 3)
        queue.stop()
        self.assertNotIn("Contexto previo", ollama.calls[1]["prompt"])
        self.assertIn("primer mensaje", ollama.calls[2]["prompt"])
        self.assertNotIn("mensaje de bea", ollama.calls[2]["prompt"])

    def test_autonomous_mode_requires_connection_and_can_be_cancelled(self) -> None:
        queue, ollama, _ = self.make_queue(autonomous_mode=True)
        queue.start()
        time.sleep(0.07)
        self.assertEqual(ollama.calls, [])
        queue.set_connected(True)
        queue.update_setting("autonomous_mode", False)
        time.sleep(0.07)
        queue.stop()
        self.assertEqual(ollama.calls, [])

    def test_autonomous_mode_activates_after_inactivity(self) -> None:
        queue, ollama, _ = self.make_queue(autonomous_mode=True)
        queue.set_connected(True)
        wait_for(lambda: len(ollama.calls) == 1)
        queue.stop()

    def test_stop_clears_memory_queue_and_thread_and_allows_new_session(self) -> None:
        queue, ollama, _ = self.make_queue()
        queue.memory.add("ana", "hola", "respuesta")
        queue.set_connected(True)
        queue.stop()
        self.assertEqual(queue.pending_count(), 0)
        self.assertEqual(queue.memory.user_count(), 0)
        wait_for(lambda: not queue.is_running())
        queue.set_connected(True)
        queue.enqueue_comment("ana", "hola")
        wait_for(lambda: len(ollama.calls) == 1)
        queue.stop()

    def test_runtime_controls_are_updated_without_mutating_source(self) -> None:
        source = {"respond_comments": True}
        controls = RuntimeControls(source, {})
        controls.update_dashboard("respond_comments", False)
        self.assertTrue(source["respond_comments"])
        self.assertFalse(controls.enabled("respond_comments"))

    def test_stop_button_state(self) -> None:
        self.assertFalse(stop_button_enabled("disconnected"))
        self.assertTrue(stop_button_enabled("connecting"))
        self.assertTrue(stop_button_enabled("connected"))
        self.assertFalse(stop_button_enabled("disconnecting"))


if __name__ == "__main__":
    unittest.main()
