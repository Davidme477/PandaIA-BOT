from __future__ import annotations

from pathlib import Path
import sys
from threading import Lock
import time
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from services.live.comment_response_queue import CommentResponseQueue


class FakeOllama:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.calls: list[dict[str, str]] = []
        self.failures = failures or set()

    def generate(self, *, model: str, prompt: str, system_prompt: str = "") -> str:
        self.calls.append({"model": model, "prompt": prompt, "system": system_prompt})
        for comment in self.failures:
            if comment in prompt:
                raise RuntimeError(f"falló {comment}")
        return f"respuesta-{len(self.calls)}"


class FakeVoiceManager:
    def __init__(self, fail_texts: set[str] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_texts = fail_texts or set()
        self.active = 0
        self.max_active = 0
        self._lock = Lock()

    def speak(self, **values: object) -> None:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.calls.append(values)
            if str(values["text"]) in self.fail_texts:
                raise RuntimeError("falló TTS")
            time.sleep(0.01)
        finally:
            with self._lock:
                self.active -= 1


def wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("La cola no terminó dentro del tiempo esperado")


class CommentResponseQueueTests(unittest.TestCase):
    def make_queue(
        self,
        *,
        enabled: bool = True,
        ollama: FakeOllama | None = None,
        voice: FakeVoiceManager | None = None,
        logs: list[str] | None = None,
    ) -> CommentResponseQueue:
        return CommentResponseQueue(
            dashboard_settings={
                "respond_comments": enabled,
                "model": "modelo-live",
                "personality": "Entusiasta",
                "language": "Español",
                "command_only_mode": False,
            },
            tts_settings={
                "engine": "windows",
                "voice": "Voz Uno",
                "speed": 1.25,
                "volume": 0.7,
            },
            ollama=ollama or FakeOllama(),
            voice_manager=voice or FakeVoiceManager(),
            log_callback=(logs if logs is not None else []).append,
        )

    def test_disabled_setting_does_not_call_ollama(self) -> None:
        ollama = FakeOllama()
        queue = self.make_queue(enabled=False, ollama=ollama)
        self.assertFalse(queue.enqueue("ana", "hola"))
        time.sleep(0.03)
        queue.stop()
        self.assertEqual(ollama.calls, [])

    def test_comment_goes_to_ollama_and_then_tts_with_saved_settings(self) -> None:
        ollama = FakeOllama()
        voice = FakeVoiceManager()
        queue = self.make_queue(ollama=ollama, voice=voice)
        queue.enqueue("ana", "hola panda")
        wait_for(lambda: len(voice.calls) == 1)
        queue.stop()

        self.assertEqual(ollama.calls[0]["model"], "modelo-live")
        self.assertIn("@ana", ollama.calls[0]["prompt"])
        self.assertIn("Entusiasta", ollama.calls[0]["system"])
        self.assertIn("Español", ollama.calls[0]["system"])
        self.assertEqual(voice.calls[0]["engine"], "windows")
        self.assertEqual(voice.calls[0]["voice"], "Voz Uno")
        self.assertEqual(voice.calls[0]["speed"], 1.25)
        self.assertEqual(voice.calls[0]["volume"], 0.7)

    def test_queue_preserves_order_and_never_overlaps_speech(self) -> None:
        ollama = FakeOllama()
        voice = FakeVoiceManager()
        queue = self.make_queue(ollama=ollama, voice=voice)
        for comment in ("uno", "dos", "tres"):
            queue.enqueue("ana", comment)
        wait_for(lambda: len(voice.calls) == 3)
        queue.stop()

        self.assertEqual(
            [call["text"] for call in voice.calls],
            ["respuesta-1", "respuesta-2", "respuesta-3"],
        )
        self.assertEqual(voice.max_active, 1)

    def test_recovers_after_ollama_and_tts_errors(self) -> None:
        logs: list[str] = []
        ollama = FakeOllama(failures={"malo-ollama"})
        voice = FakeVoiceManager(fail_texts={"respuesta-2"})
        queue = self.make_queue(ollama=ollama, voice=voice, logs=logs)
        for comment in ("malo-ollama", "malo-tts", "bueno"):
            queue.enqueue("ana", comment)
        wait_for(lambda: len(ollama.calls) == 3 and len(voice.calls) == 2)
        queue.stop()

        self.assertEqual(voice.calls[-1]["text"], "respuesta-3")
        self.assertTrue(any("Error de Ollama" in message for message in logs))
        self.assertTrue(any("Error del motor TTS" in message for message in logs))


if __name__ == "__main__":
    unittest.main()
