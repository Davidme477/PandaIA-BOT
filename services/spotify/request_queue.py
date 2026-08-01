from __future__ import annotations

import re
import threading
import time
import uuid
from collections import Counter

from services.spotify.models import MusicRequest, RequestStatus, Track, utc_now


DEFAULTS: dict[str, object] = {
    "requests_enabled": False, "command": "M", "max_pending": 20,
    "max_per_user": 2, "user_cooldown": 120, "allow_explicit": False,
    "block_duplicates": True, "only_when_tiktok_connected": True,
    "announce_tts": False,
}


def music_query(comment: str, command: str = "M") -> str | None:
    match = re.fullmatch(rf"\s*{re.escape(command)}\s+(.+?)\s*", comment, re.IGNORECASE)
    if not match:
        return None
    query = match.group(1).strip()
    return query if len(query) >= 3 else None


class MusicRequestQueue:
    def __init__(self, settings: dict[str, object] | None = None, clock=time.monotonic) -> None:
        self.settings = {**DEFAULTS, **(settings or {})}
        self.clock = clock
        self.lock = threading.RLock()
        self.items: list[MusicRequest] = []
        self.last_request: dict[str, float] = {}

    def validate(self, username: str, track: Track) -> str:
        with self.lock:
            pending = [item for item in self.items if item.status in {RequestStatus.PENDING, RequestStatus.SENDING, RequestStatus.SPOTIFY_QUEUE}]
            if len(pending) >= int(self.settings["max_pending"]):
                return "La cola musical está llena."
            user = username.casefold()
            if Counter(item.username.casefold() for item in pending)[user] >= int(self.settings["max_per_user"]):
                return "Alcanzaste el máximo de solicitudes pendientes."
            elapsed = self.clock() - self.last_request.get(user, float("-inf"))
            if elapsed < int(self.settings["user_cooldown"]):
                return f"Espera {int(self.settings['user_cooldown']) - int(elapsed)} segundos para volver a solicitar."
            if track.explicit and not bool(self.settings["allow_explicit"]):
                return "El contenido explícito está bloqueado."
            if bool(self.settings["block_duplicates"]) and any(item.track.uri == track.uri for item in pending):
                return "Esa canción ya está en la cola."
            return ""

    def add(self, username: str, track: Track) -> MusicRequest:
        error = self.validate(username, track)
        if error:
            raise ValueError(error)
        request = MusicRequest(uuid.uuid4().hex, username, track, utc_now())
        with self.lock:
            self.items.append(request)
            self.last_request[username.casefold()] = self.clock()
        return request

    def snapshot(self) -> tuple[MusicRequest, ...]:
        with self.lock:
            return tuple(self.items)

    def update(self, request_id: str, status: RequestStatus, error: str = "") -> None:
        with self.lock:
            self.items = [item.with_status(status, error) if item.request_id == request_id else item for item in self.items]

    def remove_pending(self, request_id: str) -> bool:
        with self.lock:
            before = len(self.items)
            self.items = [item for item in self.items if not (item.request_id == request_id and item.status == RequestStatus.PENDING)]
            return len(self.items) != before

    def clear_pending(self) -> int:
        with self.lock:
            before = len(self.items)
            self.items = [item for item in self.items if item.status != RequestStatus.PENDING]
            return before - len(self.items)
