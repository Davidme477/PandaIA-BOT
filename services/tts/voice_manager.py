from __future__ import annotations

from collections.abc import Iterable

from services.tts.base_engine import EngineOption, TTSEngine, TTSEngineError, VoiceOption


class VoiceManager:
    def __init__(self, engines: Iterable[TTSEngine] | None = None) -> None:
        self._engines: dict[str, TTSEngine] = {}
        if engines is None:
            engines = self._default_engines()
        for engine in engines:
            self.register_engine(engine)

    @staticmethod
    def _default_engines() -> list[TTSEngine]:
        from services.tts.kokoro_service import KokoroService
        from services.tts.windows_tts_service import WindowsTTSService

        return [KokoroService(), WindowsTTSService()]

    def register_engine(self, engine: TTSEngine) -> None:
        code = engine.engine_id.strip().lower()
        if not code:
            raise TTSEngineError("El motor debe tener un código.")
        if code in self._engines:
            raise TTSEngineError(f"Motor duplicado: {code}")
        self._engines[code] = engine

    def list_engines(self) -> list[EngineOption]:
        return [
            EngineOption(code, item.display_name, item.is_available())
            for code, item in self._engines.items()
        ]

    def is_engine_available(self, engine: str) -> bool:
        item = self._engines.get(self._normalize(engine))
        return item is not None and item.is_available()

    def get_engine(self, engine: str, *, require_available: bool = False) -> TTSEngine:
        code = self._normalize(engine)
        item = self._engines.get(code)
        if item is None:
            raise TTSEngineError(f"Motor no registrado: {code}")
        if require_available and not item.is_available():
            raise TTSEngineError(f"El motor '{code}' no está disponible.")
        return item

    def list_voices(self, engine: str) -> list[VoiceOption]:
        return self.get_engine(engine, require_available=True).list_voices()

    def get_voice(self, engine: str, voice: str) -> VoiceOption:
        return self.get_engine(engine, require_available=True).get_voice(voice)

    def preview(
        self, *, engine: str, text: str, voice: str, speed: float, volume: float
    ) -> str:
        return self.get_engine(engine, require_available=True).preview(
            text=text, voice=voice, speed=speed, volume=volume
        )

    @staticmethod
    def _normalize(engine: str) -> str:
        return engine.strip().lower()
