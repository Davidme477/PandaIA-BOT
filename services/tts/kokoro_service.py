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
    language: str = "Español"
    language_code: str = DEFAULT_LANGUAGE_CODE


SPANISH_VOICES: tuple[VoiceOption, ...] = (
    VoiceOption("ef_dora", "Dora", "Femenina"),
    VoiceOption("em_alex", "Alex", "Masculina"),
    VoiceOption("em_santa", "Santa", "Masculina"),
)


class KokoroService:
    """Servicio único para listar voces y generar audio con Kokoro."""

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
        safe_code = code.strip()

        for voice in SPANISH_VOICES:
            if voice.code == safe_code:
                return voice

        raise KokoroServiceError(
            f"La voz '{safe_code}' no está disponible."
        )

    def _get_pipeline(self, language_code: str):
        safe_language = language_code.strip() or DEFAULT_LANGUAGE_CODE

        with self._pipeline_lock:
            pipeline = self._pipelines.get(safe_language)

            if pipeline is not None:
                return pipeline

            if not self.is_installed():
                raise KokoroServiceError(
                    "Kokoro no está instalado en el entorno actual."
                )

            try:
                from kokoro import KPipeline

                pipeline = KPipeline(lang_code=safe_language)
            except Exception as error:
                raise KokoroServiceError(
                    "No se pudo iniciar Kokoro. Verifica espeak-ng "
                    "y las dependencias del entorno."
                ) from error

            self._pipelines[safe_language] = pipeline
            return pipeline

    def generate_audio(
        self,
        *,
        text: str,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
    ) -> np.ndarray:
        safe_text = text.strip()

        if not safe_text:
            raise KokoroServiceError(
                "El texto para generar la voz está vacío."
            )

        if not 0.5 <= speed <= 2.0:
            raise KokoroServiceError(
                "La velocidad debe estar entre 0.5 y 2.0."
            )

        voice_option = self.get_voice(voice)
        pipeline = self._get_pipeline(voice_option.language_code)

        audio_parts: list[np.ndarray] = []

        try:
            generator = pipeline(
                safe_text,
                voice=voice_option.code,
                speed=speed,
            )

            for _, _, audio in generator:
                audio_array = np.asarray(audio, dtype=np.float32)

                if audio_array.size:
                    audio_parts.append(audio_array)

        except Exception as error:
            raise KokoroServiceError(
                f"Kokoro no pudo generar la voz: {error}"
            ) from error

        if not audio_parts:
            raise KokoroServiceError(
                "Kokoro no devolvió audio."
            )

        return np.concatenate(audio_parts)

    def save_wav(
        self,
        *,
        text: str,
        output_path: str | Path,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
    ) -> Path:
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        audio = self.generate_audio(
            text=text,
            voice=voice,
            speed=speed,
        )

        try:
            sf.write(
                destination,
                audio,
                SAMPLE_RATE,
                subtype="PCM_16",
            )
        except Exception as error:
            raise KokoroServiceError(
                f"No se pudo guardar el audio: {error}"
            ) from error

        return destination