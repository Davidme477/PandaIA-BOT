from __future__ import annotations

from pathlib import Path
from threading import RLock
import time

from config.settings_store import read_settings, write_settings_atomic
from services.spotify.credential_store import WindowsCredentialStore
from core.app_paths import get_paths


SPOTIFY_LOCAL_FILE = get_paths().spotify_file
PUBLIC_KEYS = {"client_id", "scopes", "account_id", "authorized_at"}


class SpotifyLocalStore:
    """Metadatos locales más tokens de sesión exclusivamente en memoria."""

    def __init__(self, path: Path = SPOTIFY_LOCAL_FILE, credential_store=None) -> None:
        self.path = path
        self.credentials = credential_store or WindowsCredentialStore()
        self._session: dict[str, object] = {}
        self._lock = RLock()

    def load(self) -> dict[str, object]:
        with self._lock:
            public = {
                key: value for key, value in read_settings(self.path).items() if key in PUBLIC_KEYS
            }
            refresh_token = self.credentials.get()
            if refresh_token:
                public["refresh_token"] = refresh_token
            public.update(self._session)
            return public

    def save(self, values: dict[str, object]) -> None:
        with self._lock:
            refresh_token = str(values.get("refresh_token", "")).strip()
            if refresh_token:
                self.credentials.set(refresh_token)
            for key in ("access_token", "expires_at"):
                if key in values:
                    self._session[key] = values[key]
            current = read_settings(self.path)
            public = {key: current[key] for key in PUBLIC_KEYS if key in current}
            public.update({key: value for key, value in values.items() if key in PUBLIC_KEYS})
            write_settings_atomic(self.path, public)

    def save_client_id(self, client_id: str) -> None:
        self.save({"client_id": client_id.strip()})

    def has_authorization(self) -> bool:
        return bool(self.load().get("client_id") and self.credentials.get())

    def save_authorization(self, values: dict[str, object]) -> None:
        data = dict(values)
        data.setdefault("authorized_at", int(time.time()))
        self.save(data)

    def clear_tokens(self) -> None:
        with self._lock:
            self.credentials.clear()
            self._session.clear()
            current = read_settings(self.path)
            client_id = str(current.get("client_id", "")).strip()
            write_settings_atomic(self.path, {"client_id": client_id} if client_id else {})
