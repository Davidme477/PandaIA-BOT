from __future__ import annotations

from dataclasses import dataclass, field
import unittest

from services.tts.base_engine import TTSEngine, TTSEngineError, VoiceOption
from services.tts.voice_manager import VoiceManager


@dataclass
class FakeEngine(TTSEngine):
    engine_id: str = "fake"
    display_name: str = "Motor falso"
    available: bool = True
    preview_calls: list[dict[str, object]] = field(default_factory=list)

    def is_available(self) -> bool:
        return self.available

    def list_voices(self) -> list[VoiceOption]:
        return [VoiceOption("voz", "Voz", "Neutral", "Prueba", "Español")]

    def get_voice(self, code: str) -> VoiceOption:
        voice = self.list_voices()[0]
        if code != voice.code:
            raise TTSEngineError("Voz desconocida")
        return voice

    def preview(
        self, *, text: str, voice: str, speed: float, volume: float
    ) -> str:
        self.preview_calls.append(
            {"text": text, "voice": voice, "speed": speed, "volume": volume}
        )
        return "vista-previa"


class VoiceManagerTests(unittest.TestCase):
    def test_registers_and_lists_engines(self) -> None:
        manager = VoiceManager([FakeEngine()])
        self.assertEqual(manager.list_engines()[0].code, "fake")
        self.assertTrue(manager.list_engines()[0].available)

    def test_lists_voices_through_registered_engine(self) -> None:
        voices = VoiceManager([FakeEngine()]).list_voices(" FAKE ")
        self.assertEqual([voice.code for voice in voices], ["voz"])

    def test_delegates_preview_to_registered_engine(self) -> None:
        engine = FakeEngine()
        result = VoiceManager([engine]).preview(
            engine="fake", text="Hola", voice="voz", speed=1.2, volume=0.8
        )
        self.assertEqual(result, "vista-previa")
        self.assertEqual(
            engine.preview_calls,
            [{"text": "Hola", "voice": "voz", "speed": 1.2, "volume": 0.8}],
        )

    def test_unknown_engine_raises_common_error(self) -> None:
        with self.assertRaisesRegex(TTSEngineError, "no registrado"):
            VoiceManager([]).list_voices("desconocido")

    def test_unavailable_engine_raises_common_error(self) -> None:
        with self.assertRaisesRegex(TTSEngineError, "no está disponible"):
            VoiceManager([FakeEngine(available=False)]).list_voices("fake")

    def test_duplicate_engine_codes_are_rejected(self) -> None:
        with self.assertRaisesRegex(TTSEngineError, "duplicado"):
            VoiceManager([FakeEngine(), FakeEngine(engine_id=" FAKE ")])


if __name__ == "__main__":
    unittest.main()
