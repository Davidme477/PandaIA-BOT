from __future__ import annotations

from pathlib import Path

from config.settings_store import read_settings, write_settings_atomic


SPOTIFY_LOCAL_FILE = Path("config/spotify_local.json")
ALLOWED_KEYS = {
    "client_id", "access_token", "refresh_token", "expires_at", "scopes",
    "account_id", "account_name",
}


class SpotifyLocalStore:
    def __init__(self, path: Path = SPOTIFY_LOCAL_FILE) -> None:
        self.path = path

    def load(self) -> dict[str, object]:
        return {key: value for key, value in read_settings(self.path).items() if key in ALLOWED_KEYS}

    def save(self, values: dict[str, object]) -> None:
        current = self.load()
        current.update({key: value for key, value in values.items() if key in ALLOWED_KEYS})
        write_settings_atomic(self.path, current)

    def save_client_id(self, client_id: str) -> None:
        self.save({"client_id": client_id.strip()})

    def clear_tokens(self) -> None:
        client_id = str(self.load().get("client_id", ""))
        write_settings_atomic(self.path, {"client_id": client_id} if client_id else {})
