from __future__ import annotations

import queue
import threading
import time

from PySide6.QtCore import QObject, Signal

from services.spotify.client import SpotifyAPIError, SpotifyClient
from services.spotify.local_store import SpotifyLocalStore
from services.spotify.models import RequestStatus
from services.spotify.request_queue import MusicRequestQueue, music_query, spotify_defaults


class _TransientStore:
    def __init__(self) -> None: self.values: dict[str, object] = {}
    def load(self) -> dict[str, object]: return dict(self.values)
    def save(self, values: dict[str, object]) -> None: self.values.update(values)
    def has_authorization(self) -> bool: return False
    def clear_tokens(self) -> None: self.values.clear()


class SpotifyRuntime(QObject):
    state_changed = Signal(str, str)
    account_changed = Signal(object)
    queue_changed = Signal(object)
    playback_changed = Signal(object)
    spotify_queue_changed = Signal(object)

    def __init__(self, settings: dict[str, object] | None = None, client: SpotifyClient | None = None,
                 announce_callback=None) -> None:
        super().__init__()
        self.settings = spotify_defaults(dict(settings or {}))
        if client is None:
            self.store = SpotifyLocalStore()
            self.client = SpotifyClient(self.store)
        else:
            self.client = client
            client_store = getattr(client, "store", None)
            self.store = client_store if client_store is not None else _TransientStore()
        self.requests = MusicRequestQueue(self.settings)
        self.announce_callback = announce_callback
        self.connected_tiktok = False
        self.jobs: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="PandaIA-Spotify", daemon=True)
        self.last_poll = 0.0
        self.prepared_for_uri = ""
        self.spotify_ready = False
        self._reconnect_lock = threading.Lock()
        self._reconnect_pending = False
        self.thread.start()

    def submit_comment(self, username: str, comment: str) -> bool:
        query = music_query(comment, str(self.settings.get("command", "a/")))
        if query is None:
            return False
        if not bool(self.settings.get("requests_enabled")):
            self.state_changed.emit("Desconectado", "Las solicitudes musicales están desactivadas.")
            return True
        if not self.spotify_ready:
            self.state_changed.emit("Cuenta no autorizada", "Spotify todavía no está conectado.")
            return True
        if bool(self.settings.get("only_when_tiktok_connected")) and not self.connected_tiktok:
            self.state_changed.emit("Desconectado", "Las solicitudes solo se aceptan durante el live.")
            return True
        self.jobs.put((username, query))
        return True

    def submit_query(self, username: str, query: str) -> bool:
        if not bool(self.settings.get("requests_enabled")):
            self.state_changed.emit("Desconectado", "Solicitud musical ignorada: solicitudes desactivadas.")
            return True
        if not self.spotify_ready:
            self.state_changed.emit("Cuenta no autorizada", "Solicitud musical rechazada: Spotify está desconectado.")
            return True
        if bool(self.settings.get("only_when_tiktok_connected")) and not self.connected_tiktok:
            self.state_changed.emit("Desconectado", "Solicitud musical rechazada: TikTok no está conectado.")
            return True
        self.jobs.put((username, query)); return True

    def submit_local_request(self, query: str) -> bool:
        query = query.strip()
        if len(query) < 3:
            self.state_changed.emit("Error de Spotify", "Escribe artista y canción para la prueba local.")
            return False
        self.jobs.put(("Prueba local", query)); return True

    def set_tiktok_connected(self, connected: bool) -> None:
        self.connected_tiktok = connected

    def update_settings(self, values: dict[str, object]) -> None:
        self.settings.update(values)
        self.requests.settings.update(values)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.jobs.get(timeout=0.5)
            except queue.Empty:
                self._monitor_if_due()
                continue
            if job is None:
                break
            username, query = job
            if username == "__action__":
                self._perform_action(query)
                continue
            try:
                track = self.client.search_track(query)
                if track is None:
                    self.state_changed.emit("Error de Spotify", f"No se encontró una coincidencia fiable para: {query}")
                    continue
                request = self.requests.add(username, track)
                self.queue_changed.emit(self.requests.snapshot())
                if bool(self.settings.get("announce_tts")) and self.announce_callback is not None:
                    self.announce_callback(f"Solicitud aceptada: {track.title}, de {track.artist}")
            except (SpotifyAPIError, ValueError) as error:
                self.state_changed.emit("Error de Spotify", str(error))

    def request_action(self, action: str) -> None:
        self.jobs.put(("__action__", action))

    def reconnect(self) -> bool:
        if not self.store.has_authorization():
            self.state_changed.emit(
                "Cuenta no autorizada",
                "La autorización venció o fue revocada. Vuelve a conectar Spotify.",
            )
            return False
        with self._reconnect_lock:
            if self._reconnect_pending:
                return False
            self._reconnect_pending = True
        self.state_changed.emit("Reconectando Spotify…", "Renovando la autorización guardada.")
        self.jobs.put(("__action__", "reconnect"))
        return True

    def _perform_action(self, action: str) -> None:
        try:
            if action == "reconnect":
                self.refresh(self.client.reconnect())
            elif action == "refresh":
                self.refresh()
            elif action in {"next", "pause", "resume"}:
                getattr(self.client, action)()
                self.refresh()
        except SpotifyAPIError as error:
            self._publish_connection_error(error)
        finally:
            if action == "reconnect":
                with self._reconnect_lock:
                    self._reconnect_pending = False

    def _monitor_if_due(self) -> None:
        if time.monotonic() - self.last_poll < 8 or not self.spotify_ready:
            return
        self.last_poll = time.monotonic()
        try:
            playback = self.client.playback()
            self.playback_changed.emit(playback)
            self._publish_spotify_queue(self.client.playback_queue())
            item = playback.get("item") if isinstance(playback, dict) else None
            if isinstance(item, dict):
                uri = str(item.get("uri", ""))
                for request in self.requests.snapshot():
                    if request.status == RequestStatus.PLAYING and request.track.uri != uri:
                        self.requests.update(request.request_id, RequestStatus.FINISHED)
                for request in self.requests.snapshot():
                    if request.track.uri == uri and request.status != RequestStatus.PLAYING:
                        self.requests.update(request.request_id, RequestStatus.PLAYING)
                        self.queue_changed.emit(self.requests.snapshot())
                remaining = int(item.get("duration_ms", 0)) - int(playback.get("progress_ms", 0))
                if remaining <= 30000 and self.prepared_for_uri != uri:
                    self.send_next(str(playback.get("device", {}).get("id", "")))
                    self.prepared_for_uri = uri
                elif remaining > 30000 and self.prepared_for_uri != uri:
                    self.prepared_for_uri = ""
        except SpotifyAPIError as error:
            if error.status == 429:
                self.last_poll = time.monotonic() + max(1, error.retry_after)
            elif error.status in {401, 403, 404}:
                self.state_changed.emit("Error de Spotify", str(error))

    def send_next(self, device_id: str = "") -> bool:
        pending = next((item for item in self.requests.snapshot() if item.status == RequestStatus.PENDING), None)
        if pending is None:
            return False
        self.requests.update(pending.request_id, RequestStatus.SENDING)
        self.queue_changed.emit(self.requests.snapshot())
        try:
            self.client.add_to_queue(pending.track.uri, device_id)
            self.requests.update(pending.request_id, RequestStatus.SPOTIFY_QUEUE)
            self._publish_spotify_queue(self.client.playback_queue())
        except SpotifyAPIError as error:
            self.requests.update(pending.request_id, RequestStatus.ERROR, str(error))
        self.queue_changed.emit(self.requests.snapshot())
        return True

    def refresh(self, data: dict[str, object] | None = None) -> None:
        try:
            data = data or self.client.account_and_device()
            account, device = data["account"], data["device"]
            self.spotify_ready = True
            self.store.save({"account_id": account.get("id", "")})
            self.account_changed.emit({
                "name": account.get("display_name") or account.get("id", ""),
                "id": account.get("id", ""), "device": device,
            })
            if device is None:
                self.state_changed.emit(
                    "Sin dispositivo activo", "Spotify conectado, pero sin dispositivo activo."
                )
            else:
                self.state_changed.emit("Conectado", "Spotify conectado.")
            try:
                self.playback_changed.emit(self.client.playback())
                self._publish_spotify_queue(self.client.playback_queue())
            except SpotifyAPIError as playback_error:
                if playback_error.status != 404:
                    raise
                self.playback_changed.emit({})
                self.spotify_queue_changed.emit([])
        except SpotifyAPIError as error:
            self._publish_connection_error(error)

    def _publish_connection_error(self, error: SpotifyAPIError) -> None:
        self.spotify_ready = False
        if error.status == 403:
            self.state_changed.emit(
                "Premium requerido", "La cuenta conectada no dispone de Spotify Premium."
            )
        elif error.status == 401:
            message = str(error)
            if "permisos" not in message.casefold():
                message = "La autorización venció o fue revocada. Vuelve a conectar Spotify."
            self.state_changed.emit(
                "Cuenta no autorizada", message,
            )
        else:
            self.state_changed.emit(
                "Spotify sin conexión", "Spotify no está disponible temporalmente."
            )

    def _publish_spotify_queue(self, data: dict[str, object]) -> None:
        requested = {item.track.uri: item.username for item in self.requests.snapshot()}
        tracks = []
        current = data.get("currently_playing") if isinstance(data, dict) else None
        for position, item in enumerate(([current] if isinstance(current, dict) else []) + list(data.get("queue", []) if isinstance(data, dict) else [])):
            if not isinstance(item, dict): continue
            uri = str(item.get("uri", "")); artists = ", ".join(str(a.get("name", "")) for a in item.get("artists", []))
            username = requested.get(uri, "")
            is_current = position == 0 and isinstance(current, dict)
            tracks.append({
                "position": 0 if is_current else position + (0 if isinstance(current, dict) else 1), "current": is_current,
                "uri": uri, "title": str(item.get("name", "")), "artist": artists,
                "duration_ms": int(item.get("duration_ms", 0)),
                "origin": f"Solicitada por @{username.lstrip('@')}" if username else "Añadida manualmente en Spotify",
            })
        self.spotify_queue_changed.emit(tracks)

    def disconnect(self) -> None:
        self.store.clear_tokens()
        self.spotify_ready = False
        self.requests = MusicRequestQueue(self.settings)
        self.state_changed.emit("Desconectado", "Cuenta local desconectada.")
        self.account_changed.emit({})
        self.queue_changed.emit([])
        self.spotify_queue_changed.emit([])
        self.playback_changed.emit({})

    def stop(self) -> None:
        self.stop_event.set()
        self.jobs.put(None)
        self.thread.join(timeout=3)
