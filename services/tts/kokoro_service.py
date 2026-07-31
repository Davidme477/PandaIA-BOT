from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np
import soundfile as sf

SAMPLE_RATE = 24_000
DEFAULT_LANGUAGE_CODE = "e"
DEFAULT_VOICE = "ef_dora"


class KokoroServiceError(RuntimeError):
    """Error controlado al generar audio con Kokoro."""


@dataclass(frozen=True)
class VoiceOption:
    code: str
    display_name: str
    gender: str
    style: str
    language: str = "Español"
    language_code: str = DEFAULT_LANGUAGE_CODE


SPANISH_VOICES = (
    VoiceOption("ef_dora", "Dora", "Femenina", "Clara y expresiva"),
    VoiceOption("em_alex", "Alex", "Masculina", "Natural y tranquila"),
    VoiceOption("em_santa", "Santa", "Masculina", "Profunda y cálida"),
)


class KokoroService:
    def __init__(self) -> None:
        self._pipelines: dict[str, object] = {}
        self._pipeline_lock = Lock()

    @staticmethod
    def is_installed() -> bool:
        return (
            importlib.util.find_spec("kokoro") is not None
            and importlib.util.find_spec("soundfile") is not None
        )

    @staticmethod
    def list_voices() -> list[VoiceOption]:
        return list(SPANISH_VOICES)

    @staticmethod
    def get_voice(code: str) -> VoiceOption:
        for voice in SPANISH_VOICES:
            if voice.code == code.strip():
                return voice
        raise KokoroServiceError(f"La voz '{code}' no está disponible.")

    def _get_pipeline(self, language_code: str):
        language_code = language_code.strip() or DEFAULT_LANGUAGE_CODE
        with self._pipeline_lock:
            pipeline = self._pipelines.get(language_code)
            if pipeline is not None:
                return pipeline
            if not self.is_installed():
                raise KokoroServiceError("Kokoro no está instalado.")
            try:
                from kokoro import KPipeline
                pipeline = KPipeline(lang_code=language_code)
            except Exception as error:
                raise KokoroServiceError(
                    "No se pudo iniciar Kokoro. Verifica espeak-ng."
                ) from error
            self._pipelines[language_code] = pipeline
            return pipeline

    def generate_audio(
        self,
        *,
        text: str,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
        volume: float = 1.0,
    ) -> np.ndarray:
        text = text.strip()
        if not text:
            raise KokoroServiceError("El texto está vacío.")
        if not 0.5 <= speed <= 2.0:
            raise KokoroServiceError("La velocidad debe estar entre 0.5 y 2.0.")
        if not 0.0 <= volume <= 1.0:
            raise KokoroServiceError("El volumen debe estar entre 0 y 1.")

        option = self.get_voice(voice)
        pipeline = self._get_pipeline(option.language_code)
        parts: list[np.ndarray] = []

        try:
            for _, _, audio in pipeline(
                text,
                voice=option.code,
                speed=speed,
            ):
                array = np.asarray(audio, dtype=np.float32)
                if array.size:
                    parts.append(array)
        except Exception as error:
            raise KokoroServiceError(
                f"Kokoro no pudo generar la voz: {error}"
            ) from error

        if not parts:
            raise KokoroServiceError("Kokoro no devolvió audio.")

        audio = np.concatenate(parts)
        return np.clip(audio * volume, -1.0, 1.0).astype(
            np.float32,
            copy=False,
        )

    def save_wav(
        self,
        *,
        text: str,
        output_path: str | Path,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
        volume: float = 1.0,
    ) -> Path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        audio = self.generate_audio(
            text=text,
            voice=voice,
            speed=speed,
            volume=volume,
        )
        try:
            sf.write(destination, audio, SAMPLE_RATE, subtype="PCM_16")
        except Exception as error:
            raise KokoroServiceError(
                f"No se pudo guardar el audio: {error}"
            ) from error
        return destination