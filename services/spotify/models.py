from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum


class RequestStatus(StrEnum):
    PENDING = "Pendiente"
    SENDING = "Enviando"
    SPOTIFY_QUEUE = "En cola Spotify"
    PLAYING = "Reproduciendo"
    FINISHED = "Finalizada"
    ERROR = "Error"


@dataclass(frozen=True)
class Track:
    uri: str
    title: str
    artist: str
    duration_ms: int
    explicit: bool = False


@dataclass(frozen=True)
class MusicRequest:
    request_id: str
    username: str
    track: Track
    requested_at: str
    status: RequestStatus = RequestStatus.PENDING
    error: str = ""

    def with_status(self, status: RequestStatus, error: str = "") -> "MusicRequest":
        return replace(self, status=status, error=error)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
