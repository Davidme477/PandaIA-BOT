from __future__ import annotations

import queue
import threading
import time

from PySide6.QtCore import QObject, Signal

from services.spotify.client import SpotifyAPIError, SpotifyClient
from services.spotify.local_store import SpotifyLocalStore
from services.spotify.models import RequestStatus
from services.spotify.request_queue import DEFAULTS, MusicRequestQueue, music_query


class SpotifyRuntime(QObject):
    state_changed = Signal(str, str)
    account_changed = Signal(object)
    queue_changed = Signal(object)
    playback_changed = Signal(object)
    overlay_event = Signal(object)

    def __init__(self, settings: dict[str, object] | None = None, client: SpotifyClient | None = None,
                 announce_callback=None) -> None:
        super().__init__()
        self.settings = {**DEFAULTS, **(settings or {})}
        self.store = SpotifyLocalStore()
        self.client = client or SpotifyClient(self.store)
        self.requests = MusicRequestQueue(self.settings)
        self.announce_callback = announce_callback
        self.connected_tiktok = False
        self.jobs: queue.Queue[tuple[str, str] | None] = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, name="PandaIA-Spotify", daemon=True)
        self.last_poll = 0.0
        self.prepared_for_uri = ""
        self.thread.start()

    def submit_comment(self, username: str, comment: str) -> bool:
        query = music_query(comment, str(self.settings.get("command", "M")))
        if query is None:
            return False
        if not bool(self.settings.get("requests_enabled")):
            self.state_changed.emit("Desconectado", "Las solicitudes musicales están desactivadas.")
            return True
        if bool(self.settings.get("only_when_tiktok_connected")) and not self.connected_tiktok:
            self.state_changed.emit("Desconectado", "Las solicitudes solo se aceptan durante el live.")
            return True
        self.jobs.put((username, query))
        return True

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
                self.overlay_event.emit({
                    "type": "music_request", "title": track.title, "artist": track.artist,
                    "username": username, "request_id": request.request_id,
                })
                if bool(self.settings.get("announce_tts")) and self.announce_callback is not None:
                    self.announce_callback(f"Solicitud aceptada: {track.title}, de {track.artist}")
            except (SpotifyAPIError, ValueError) as error:
                self.state_changed.emit("Error de Spotify", str(error))

    def request_action(self, action: str) -> None:
        self.jobs.put(("__action__", action))

    def _perform_action(self, action: str) -> None:
        try:
            if action == "refresh":
                self.refresh()
            elif action in {"next", "pause", "resume"}:
                getattr(self.client, action)()
                self.refresh()
        except SpotifyAPIError as error:
            self.state_changed.emit("Error de Spotify", str(error))

    def _monitor_if_due(self) -> None:
        if time.monotonic() - self.last_poll < 8 or not self.store.load().get("access_token"):
            return
        self.last_poll = time.monotonic()
        try:
            playback = self.client.playback()
            self.playback_changed.emit(playback)
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
                self.overlay_event.emit({
                    "type": "playback", "title": item.get("name", ""),
                    "artist": ", ".join(a.get("name", "") for a in item.get("artists", [])),
                    "duration_ms": item.get("duration_ms", 0),
                })
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
        except SpotifyAPIError as error:
            self.requests.update(pending.request_id, RequestStatus.ERROR, str(error))
        self.queue_changed.emit(self.requests.snapshot())
        return True

    def refresh(self) -> None:
        try:
            data = self.client.account_and_device()
            account, device = data["account"], data["device"]
            self.account_changed.emit({
                "name": account.get("display_name") or account.get("id", ""),
                "id": account.get("id", ""), "device": device,
            })
            if device is None:
                self.state_changed.emit("Sin dispositivo activo", "Abre Spotify y reproduce una canción para activar el dispositivo.")
            else:
                self.state_changed.emit("Conectado", "Spotify Premium conectado.")
            self.playback_changed.emit(self.client.playback())
        except SpotifyAPIError as error:
            state = "Premium requerido" if error.status == 403 else "Cuenta no autorizada" if error.status == 401 else "Error de Spotify"
            self.state_changed.emit(state, str(error))

    def disconnect(self) -> None:
        self.store.clear_tokens()
        self.state_changed.emit("Desconectado", "Cuenta local desconectada.")
        self.account_changed.emit({})

    def stop(self) -> None:
        self.stop_event.set()
        self.jobs.put(None)
        self.thread.join(timeout=3)
