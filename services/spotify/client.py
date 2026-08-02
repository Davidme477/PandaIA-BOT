from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.spotify.local_store import SpotifyLocalStore
from services.spotify.models import Track
from services.spotify.oauth import SCOPES, SpotifyAuthError, refresh_access_token


class SpotifyAPIError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, retry_after: int = 0) -> None:
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


class SpotifyClient:
    API = "https://api.spotify.com/v1"

    def __init__(self, store: SpotifyLocalStore | None = None, opener=urlopen) -> None:
        self.store = store or SpotifyLocalStore()
        self.opener = opener

    def _credentials(self, *, force_refresh: bool = False) -> dict[str, object]:
        values = self.store.load()
        if not values.get("refresh_token") and not values.get("access_token"):
            raise SpotifyAPIError(
                "La autorización venció o fue revocada. Vuelve a conectar Spotify.", status=401
            )
        if force_refresh or not values.get("access_token") or float(values.get("expires_at", 0) or 0) <= time.time() + 30:
            try:
                refreshed = refresh_access_token(
                    str(values.get("client_id", "")), str(values.get("refresh_token", "")), self.opener
                )
            except SpotifyAuthError as error:
                if error.permanent:
                    self.store.clear_tokens()
                    raise SpotifyAPIError(
                        "La autorización venció o fue revocada. Vuelve a conectar Spotify.", status=401
                    ) from None
                raise SpotifyAPIError("Spotify no está disponible temporalmente.") from None
            values.update(refreshed)
            values["expires_at"] = time.time() + int(refreshed.get("expires_in", 3600))
            self.store.save(values)
        return values

    def reconnect(self) -> dict[str, object]:
        values = self.store.load()
        granted_value = values.get("scopes", [])
        granted = set(
            granted_value.split() if isinstance(granted_value, str) else granted_value
            if isinstance(granted_value, list) else []
        )
        if granted and not set(SCOPES.split()).issubset(granted):
            self.store.clear_tokens()
            raise SpotifyAPIError(
                "Faltan permisos obligatorios. Vuelve a conectar Spotify.", status=401
            )
        self._credentials(force_refresh=True)
        return self.account_and_device()

    def request(
        self, method: str, path: str, data: object | None = None, *, retry_auth: bool = True
    ) -> object:
        token = str(self._credentials()["access_token"])
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = Request(self.API + path, data=body, method=method, headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json",
        })
        try:
            with self.opener(request, timeout=15) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as error:
            if error.code == 401 and retry_auth and self.store.load().get("refresh_token"):
                try:
                    self._credentials(force_refresh=True)
                except SpotifyAPIError:
                    raise
                return self.request(method, path, data, retry_auth=False)
            retry = int(error.headers.get("Retry-After", "0") or 0)
            messages = {401: "Cuenta no autorizada.", 403: "Spotify Premium requerido o acción no autorizada.",
                        404: "No hay un dispositivo Spotify activo.", 429: "Spotify limitó temporalmente las solicitudes."}
            raise SpotifyAPIError(messages.get(error.code, "Error de Spotify."), status=error.code, retry_after=retry) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise SpotifyAPIError("No se pudo conectar con Spotify.") from None

    def account_and_device(self) -> dict[str, object]:
        account = self.request("GET", "/me")
        if not isinstance(account, dict) or account.get("product") != "premium":
            raise SpotifyAPIError(
                "Conexión no permitida: esta cuenta no dispone de Spotify Premium o no está autorizada.", status=403
            )
        devices = self.request("GET", "/me/player/devices")
        items = devices.get("devices", []) if isinstance(devices, dict) else []
        active = next((item for item in items if item.get("is_active")), None)
        return {"account": account, "device": active}

    def playback(self) -> dict[str, object]:
        value = self.request("GET", "/me/player")
        return value if isinstance(value, dict) else {}

    def playback_queue(self) -> dict[str, object]:
        value = self.request("GET", "/me/player/queue")
        return value if isinstance(value, dict) else {"currently_playing": None, "queue": []}

    def search_track(self, query: str) -> Track | None:
        data = self.request("GET", "/search?" + urlencode({"q": query, "type": "track", "limit": 10}))
        items = data.get("tracks", {}).get("items", []) if isinstance(data, dict) else []
        query_tokens = set(query.casefold().split())
        best: tuple[float, dict] | None = None
        for item in items:
            artists = ", ".join(str(a.get("name", "")) for a in item.get("artists", []))
            candidate = f"{artists} {item.get('name', '')}".casefold()
            score = len(query_tokens & set(candidate.split())) / max(1, len(query_tokens))
            if best is None or score > best[0]:
                best = (score, item)
        if best is None or best[0] < 0.45:
            return None
        item = best[1]
        return Track(
            uri=str(item.get("uri", "")), title=str(item.get("name", "")),
            artist=", ".join(str(a.get("name", "")) for a in item.get("artists", [])),
            duration_ms=int(item.get("duration_ms", 0)), explicit=bool(item.get("explicit", False)),
        )

    def add_to_queue(self, uri: str, device_id: str = "") -> None:
        suffix = "?" + urlencode({k: v for k, v in {"uri": uri, "device_id": device_id}.items() if v})
        self.request("POST", "/me/player/queue" + suffix)

    def next(self) -> None:
        self.request("POST", "/me/player/next")

    def pause(self) -> None:
        self.request("PUT", "/me/player/pause")

    def resume(self) -> None:
        self.request("PUT", "/me/player/play")
