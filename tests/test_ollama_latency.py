from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.dialogs.personality_dialog import PersonalityDialog, PersonalityPreviewWorker
from services.ollama.ollama_service import OllamaService
from services.ollama.response_length import (
    RESPONSE_LENGTHS, finalize_ollama_response, generation_token_limit,
)


class Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self) -> bytes: return self.payload


class RecordingOpener:
    def __init__(self, responses=None) -> None:
        self.responses = list(responses or [{"response": "Respuesta natural y breve para todas las personas presentes en este live.", "load_duration": 0}])
        self.payloads: list[dict[str, object]] = []

    def __call__(self, request, timeout=0):
        self.payloads.append(json.loads(request.data.decode()))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return Response(value)


class OllamaLatencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_qwen3_disables_thinking_and_strips_internal_reasoning(self):
        opener = RecordingOpener([{
            "response": "<think>razonamiento privado</think>Respuesta segura y natural para compartir ahora con todo el público del live.",
            "load_duration": 0,
        }])
        answer = OllamaService(opener=opener).generate(
            model="qwen3:4b", prompt="hola", response_length="Corta"
        )
        self.assertIs(opener.payloads[0]["think"], False)
        self.assertNotIn("think", answer.casefold())
        self.assertNotIn("razonamiento privado", answer)

    def test_old_ollama_falls_back_to_no_think_once(self):
        unsupported = HTTPError("http://localhost", 400, "opción desconocida", {}, BytesIO(b"think unsupported"))
        opener = RecordingOpener([unsupported, {"response": "Respuesta breve y compatible para este live sin razonamiento interno visible."}])
        OllamaService(opener=opener).generate(model="qwen3:4b", prompt="hola")
        self.assertEqual(len(opener.payloads), 2)
        self.assertNotIn("think", opener.payloads[1])
        self.assertTrue(str(opener.payloads[1]["prompt"]).startswith("/no_think\n"))

    def test_token_limits_and_keep_alive_are_sent(self):
        for level, expected in (("Corta", 32), ("Normal", 64), ("Detallada", 96)):
            opener = RecordingOpener()
            OllamaService(opener=opener, keep_alive="10m").generate(
                model="modelo", prompt="hola", response_length=level
            )
            payload = opener.payloads[0]
            self.assertEqual(payload["keep_alive"], "10m")
            self.assertEqual(payload["options"]["num_predict"], expected)
            self.assertEqual(generation_token_limit(level), RESPONSE_LENGTHS[level].max_tokens)

    def test_valid_answer_and_local_sentence_trim_do_not_reformulate(self):
        calls = []
        valid = "Esta respuesta breve suena natural y funciona perfectamente durante nuestro live de hoy."
        self.assertEqual(
            finalize_ollama_response(valid, "Corta", reformulate=lambda *_: calls.append(1)), valid
        )
        long = valid + " Esta segunda frase contiene detalles adicionales que ya no hacen falta."
        self.assertEqual(
            finalize_ollama_response(long, "Corta", reformulate=lambda *_: calls.append(1)), valid
        )
        self.assertEqual(calls, [])

    def test_at_most_one_reformulation_and_thinking_never_reaches_result(self):
        calls = []
        result = finalize_ollama_response(
            "palabra " * 50,
            "Corta",
            reformulate=lambda *_: calls.append(1) or "<think>oculto</think>Respuesta natural breve para todas las personas que están mirando este live ahora.",
        )
        self.assertEqual(len(calls), 1)
        self.assertNotIn("oculto", result)

    def test_warmup_uses_keep_alive_without_prompt(self):
        opener = RecordingOpener([{"done": True}])
        OllamaService(opener=opener, keep_alive="10m").warmup("qwen3:4b")
        self.assertEqual(opener.payloads[0]["keep_alive"], "10m")
        self.assertNotIn("prompt", opener.payloads[0])

    def test_preview_timeout_reports_error_and_buttons_recover(self):
        failures = []

        class TimedOutService:
            def __init__(self, timeout): self.timeout = timeout
            def generate(self, **_values): raise TimeoutError("tiempo agotado")

        worker = PersonalityPreviewWorker(
            model="qwen3:4b", message="hola",
            settings={"personality": "Amigable", "response_length": "Corta"},
        )
        worker.failed.connect(failures.append)
        with patch("app.dialogs.personality_dialog.OllamaService", TimedOutService):
            worker.run()
        self.assertTrue(failures)

        dialog = PersonalityDialog(
            model="qwen3:4b", language="Español", custom_name="Prueba",
            custom_prompt="Responde con naturalidad.",
        )
        dialog.set_busy(True)
        dialog.preview_failed("El modelo tardó demasiado en responder.")
        dialog.preview_finished()
        self.assertTrue(dialog.test_button.isEnabled())
        self.assertIn("tardó demasiado", dialog.status_label.text())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
