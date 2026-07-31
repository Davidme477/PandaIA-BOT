from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from services.tts.kokoro_service import KokoroService
from services.tts.windows_tts_service import WindowsTTSService


PREVIEW_FILE = Path("temp/kokoro/voice_preview.wav")


@dataclass(frozen=True)
class EngineOption:
    code: str
    display_name: str
    available: bool


class VoiceManager:
    def __init__(self) -> None:
        self.kokoro = KokoroService()
        self.windows = WindowsTTSService()

    def list_engines(self) -> list[EngineOption]:
        return [
            EngineOption("kokoro", "Kokoro", self.kokoro.is_installed()),
            EngineOption("windows", "Windows SAPI", self.windows.is_available()),
        ]

    def is_engine_available(self, engine: str) -> bool:
        return {
            "kokoro": self.kokoro.is_installed(),
            "windows": self.windows.is_available(),
        }.get(engine.strip().lower(), False)

    def list_voices(self, engine: str):
        engine = engine.strip().lower()
        if engine == "kokoro":
            return self.kokoro.list_voices()
        if engine == "windows":
            return self.windows.list_voices()
        raise RuntimeError(f"Motor no registrado: {engine}")

    def get_voice(self, engine: str, voice: str):
        engine = engine.strip().lower()
        if engine == "kokoro":
            return self.kokoro.get_voice(voice)
        if engine == "windows":
            return self.windows.get_voice(voice)
        raise RuntimeError(f"Motor no registrado: {engine}")

    def preview(
        self,
        *,
        engine: str,
        text: str,
        voice: str,
        speed: float,
        volume: float,
    ) -> str:
        engine = engine.strip().lower()

        if engine == "kokoro":
            path = self.kokoro.save_wav(
                text=text,
                output_path=PREVIEW_FILE,
                voice=voice,
                speed=speed,
                volume=volume,
            )
            if sys.platform == "win32":
                import winsound
                winsound.PlaySound(str(path.resolve()), winsound.SND_FILENAME)
            return str(path)

        if engine == "windows":
            self.windows.speak(
                text=text,
                voice=voice,
                speed=speed,
                volume=volume,
            )
            return "Windows SAPI"

        raise RuntimeError(f"Motor no registrado: {engine}")