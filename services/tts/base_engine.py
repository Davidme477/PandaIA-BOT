from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class TTSEngineError(RuntimeError):
    """Error controlado y común para los motores de texto a voz."""


@dataclass(frozen=True)
class VoiceOption:
    code: str
    display_name: str
    gender: str
    style: str
    language: str
    language_code: str = ""


@dataclass(frozen=True)
class EngineOption:
    code: str
    display_name: str
    available: bool


class TTSEngine(ABC):
    """Contrato que debe implementar cualquier motor de voz registrable."""

    engine_id: str
    display_name: str

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_voices(self) -> list[VoiceOption]:
        raise NotImplementedError

    @abstractmethod
    def get_voice(self, code: str) -> VoiceOption:
        raise NotImplementedError

    @abstractmethod
    def preview(
        self, *, text: str, voice: str, speed: float, volume: float
    ) -> str:
        raise NotImplementedError
