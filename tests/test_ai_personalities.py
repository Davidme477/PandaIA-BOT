from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.error import URLError

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config.settings_store import read_settings, write_settings_atomic
from services.live.comment_response_queue import CommentResponseQueue
from services.ollama.ollama_service import OllamaService, OllamaServiceError
from services.ollama.personalities import (
    PERSONALITIES, build_system_prompt, dashboard_defaults,
    generate_personality_preview,
)


class FakeOllama:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def generate(self, *, model: str, prompt: str, system_prompt: str = "") -> str:
        self.calls.append({"model": model, "prompt": prompt, "system": system_prompt})
        return "respuesta"


class FakeVoice:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def speak(self, **values: object) -> None:
        self.calls.append(values)


class AIPersonalityTests(unittest.TestCase):
    def test_system_prompt_contains_each_personality_instructions(self) -> None:
        for option in PERSONALITIES:
            settings = {
                "personality": option.name,
                "language": "Español",
                "custom_personality_name": "Especial",
                "custom_personality_prompt": "Habla con serenidad.",
            }
            prompt = build_system_prompt(settings)
            expected = option.instructions or "Habla con serenidad."
            self.assertIn(expected, prompt)

    def test_custom_personality_name_and_prompt_are_real_instructions(self) -> None:
        prompt = build_system_prompt({
            "personality": "Personalizada",
            "language": "Portugués",
            "custom_personality_name": "Nocturna",
            "custom_personality_prompt": "Habla con un tono suave y musical.",
        })
        self.assertIn("Personalidad Nocturna", prompt)
        self.assertIn("tono suave y musical", prompt)

    def test_language_is_an_exclusive_real_instruction(self) -> None:
        for language in ("Español", "Inglés", "Portugués"):
            self.assertIn(
                f"Responde exclusivamente en {language}",
                build_system_prompt({"personality": "Profesional", "language": language}),
            )

    def test_queue_uses_dynamic_model_personality_and_language(self) -> None:
        ollama, voice = FakeOllama(), FakeVoice()
        queue = CommentResponseQueue(
            dashboard_settings={
                "model": "modelo-uno", "personality": "Amigable", "language": "Español",
                "respond_comments": True, "automatic_responses": True, "use_memory": False,
            },
            tts_settings={"engine": "fake", "voice": "voz", "speed": 1.0, "volume": 1.0},
            ollama=ollama, voice_manager=voice,
        )
        queue._process(queue_request("primero"))
        queue.update_setting("model", "modelo-dos")
        queue.update_setting("personality", "Romántica")
        queue.update_setting("language", "Portugués")
        queue._process(queue_request("segundo"))
        queue.stop()
        self.assertEqual([call["model"] for call in ollama.calls], ["modelo-uno", "modelo-dos"])
        self.assertIn("cálida, afectuosa", ollama.calls[1]["system"])
        self.assertIn("exclusivamente en Portugués", ollama.calls[1]["system"])

    def test_atomic_persistence_preserves_new_and_existing_options(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            data = {
                "dashboard": {
                    "model": "modelo", "personality": "Personalizada", "language": "Inglés",
                    "custom_personality_name": "Directa",
                    "custom_personality_prompt": "Responde directamente.",
                    "respond_comments": False,
                },
                "tts": {"engine": "windows"},
            }
            write_settings_atomic(path, data)
            self.assertEqual(read_settings(path), data)

    def test_old_configuration_gets_backward_compatible_defaults(self) -> None:
        settings = dashboard_defaults({"model": "viejo", "personality": "Entusiasta"})
        self.assertEqual(settings["model"], "viejo")
        self.assertEqual(settings["custom_personality_name"], "Mi personalidad")
        self.assertEqual(settings["custom_personality_prompt"], "")
        legacy = dashboard_defaults({"personality": "Amigable, divertida y carismática"})
        self.assertEqual(legacy["personality"], "Amigable")

    def test_ollama_unavailable_is_controlled(self) -> None:
        with patch("services.ollama.ollama_service.urlopen", side_effect=URLError("cerrado")):
            with self.assertRaises(OllamaServiceError):
                OllamaService(timeout=0.01).list_models()

    def test_personality_preview_calls_only_ollama_not_tts(self) -> None:
        ollama, voice = FakeOllama(), FakeVoice()
        answer = generate_personality_preview(
            ollama,
            model="modelo",
            message="hola",
            settings={"personality": "Divertida", "language": "Español"},
        )
        self.assertEqual(answer, "respuesta")
        self.assertEqual(len(ollama.calls), 1)
        self.assertEqual(voice.calls, [])


def queue_request(text: str):
    from services.live.comment_response_queue import ResponseRequest
    return ResponseRequest("comment", "ana", text)


if __name__ == "__main__":
    unittest.main()
