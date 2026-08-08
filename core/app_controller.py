from __future__ import annotations

import asyncio
import os
import secrets
import subprocess
import sys
import time
from threading import Lock, Thread
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QDialog

from app.dialogs.voice_dialog import VoiceDialog
from app.dialogs.personality_dialog import PersonalityDialog
from config.settings_store import read_settings, write_settings_atomic
from services.tiktok.tiktok_service import TikTokService
from services.tiktok.live_state import LiveStats
from services.live.comment_response_queue import CommentResponseQueue
from services.live.session_memory import MemorySnapshot
from services.tts.voice_manager import VoiceManager, get_voice_manager
from services.ollama.personalities import dashboard_defaults
from services.ollama.ollama_service import OllamaService
from services.spotify.runtime import SpotifyRuntime
from services.overlay.gift_animations import GIFT_DEFAULTS, GiftAnimationManager
from services.live.command_router import CommandRouter
from services.spotify.request_queue import spotify_defaults
from services.live_watchdog.runtime import LiveWatchdog, WATCHDOG_DEFAULTS
from services.overlay.cloudflare_tunnel import CloudflareTunnel
from services.tiktok.gift_image_service import prune_gift_cache
from services.tiktok.member_levels import DEFAULTS as MEMBER_LEVEL_DEFAULTS, MemberLevelManager
from core.app_paths import get_paths, is_frozen

OVERLAY_HEALTH_URL = "http://127.0.0.1:5050/health"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
CONFIG_FILE = get_paths().settings_file


class PandaWorker(QThread):
    status_changed = Signal(str, str)
    activity_received = Signal(str, str, str, str)
    live_stats_changed = Signal(object)
    live_session_reset = Signal()
    memory_changed = Signal(object)
    error_occurred = Signal(str)

    def __init__(
        self,
        username: str,
        dashboard_settings: dict[str, object],
        tts_settings: dict[str, object],
        gifts_settings: dict[str, object] | None = None,
        music_callback=None,
        gift_animation_callback=None,
        member_level_callback=None,
        voice_manager: VoiceManager | None = None,
    ) -> None:
        super().__init__()
        self.username = username
        self.tts_engine = str(tts_settings.get("engine", "kokoro"))
        self.loop: asyncio.AbstractEventLoop | None = None
        self.tiktok_service: TikTokService | None = None
        self.overlay_process: subprocess.Popen | None = None
        self.overlay_started_here = False
        self.stop_requested = False
        self.response_queue = CommentResponseQueue(
            dashboard_settings=dashboard_settings,
            tts_settings=tts_settings,
            log_callback=self.forward_log,
            memory_callback=self.forward_memory,
            voice_manager=voice_manager or get_voice_manager(),
        )
        self.music_callback = music_callback
        self.gift_animation_callback = gift_animation_callback
        self.member_level_callback = member_level_callback
        self.command_router = CommandRouter(
            chat_command=str(dashboard_settings.get("chat_command", "/")),
            music_command=str((gifts_settings or {}).get("command", "a/")),
        )
        self._last_ignored_log = 0.0
        self._last_live_stats_emit = 0.0
        self._latest_live_stats: LiveStats | None = None

    def run(self) -> None:
        try:
            self.status_changed.emit("overlay_starting", "Iniciando overlay...")
            self.ensure_overlay()
            self.status_changed.emit("overlay_ready", "Overlay activo.")

            if self.check_url(OLLAMA_TAGS_URL, 2):
                self.status_changed.emit("ollama_connected", "Ollama disponible.")
            else:
                self.status_changed.emit(
                    "ollama_unavailable",
                    "Ollama no responde en el puerto 11434.",
                )

            voice_manager = self.response_queue.voice_manager
            if voice_manager.is_engine_available(self.tts_engine):
                self.status_changed.emit(
                    "tts_available",
                    f"Motor TTS {self.tts_engine} disponible.",
                )
            else:
                self.status_changed.emit(
                    "tts_missing",
                    f"Motor TTS {self.tts_engine} no disponible.",
                )

            if self.stop_requested:
                return

            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.tiktok_service = TikTokService(
                username=self.username,
                status_callback=self.forward_tiktok_status,
                activity_callback=self.forward_activity,
                comment_callback=self.forward_comment,
                gift_callback=self.forward_gift,
                gift_animation_callback=self.forward_gift_animation,
                stats_callback=self.forward_live_stats,
                reset_callback=self.live_session_reset.emit,
                member_level_callback=self.member_level_callback,
            )
            self.status_changed.emit(
                "tiktok_connecting",
                f"Conectando con {self.username}...",
            )
            self.loop.run_until_complete(self.tiktok_service.connect())

        except Exception as error:
            self.error_occurred.emit(str(error))
        finally:
            self.close_loop()
            if self.overlay_started_here:
                self.stop_overlay()

    def ensure_overlay(self) -> None:
        for _ in range(30):
            if self.stop_requested:
                raise RuntimeError("Inicio cancelado.")
            if self.check_url(OVERLAY_HEALTH_URL, 1):
                return
            time.sleep(0.2)
        raise RuntimeError("El servidor local del overlay no respondió.")

    @staticmethod
    def check_url(url: str, timeout: float) -> bool:
        try:
            with urlopen(url, timeout=timeout) as response:
                return 200 <= response.status < 300
        except (URLError, TimeoutError, OSError):
            return False

    def forward_tiktok_status(self, status: str, message: str) -> None:
        if status == "tiktok_connected":
            self.response_queue.set_connected(True)
        elif status == "tiktok_disconnected":
            self.response_queue.set_connected(False)
        self.status_changed.emit(status, message)

    def forward_activity(self, icon: str, title: str, user: str, amount: str) -> None:
        self.activity_received.emit(icon, title, user, amount)

    def forward_comment(self, username: str, comment: str) -> None:
        route = self.command_router.route(comment)
        if route.kind == "music":
            self.forward_log("Solicitud musical detectada.")
            if self.music_callback is not None: self.music_callback(username, route.text)
            return
        if route.kind == "chat":
            self.forward_log("Comando de conversación detectado.")
            self.response_queue.enqueue_routed_comment(username, route.text)
            return
        if route.kind in {"empty_music", "empty_chat"}:
            self.forward_log("Comando vacío ignorado.")
            return
        dashboard, _tts = self.response_queue.controls.snapshot()
        if not bool(dashboard.get("command_only_mode", True)):
            self.response_queue.enqueue_comment(username, comment)
            return
        if time.monotonic() - self._last_ignored_log >= 15:
            self.forward_log("Comentario ignorado por no tener comando.")
            self._last_ignored_log = time.monotonic()

    def forward_gift(self, username: str, gift_name: str, quantity: int) -> None:
        self.response_queue.enqueue_gift(username, gift_name, quantity)

    def forward_gift_animation(self, gift_id: str, gift_name: str, username: str,
                               quantity: int, image_url: str, event_id: str) -> None:
        if self.gift_animation_callback is not None:
            self.gift_animation_callback(
                gift_id=gift_id, gift_name=gift_name, username=username,
                quantity=quantity, image_url=image_url, event_id=event_id,
            )

    def update_setting(self, key: str, value: object) -> None:
        self.response_queue.update_setting(key, value)
        if key == "chat_command": self.command_router.update(chat_command=str(value))

    def update_music_command(self, value: object) -> None:
        self.command_router.update(music_command=str(value))

    def update_tts_settings(self, values: dict[str, object]) -> None:
        self.response_queue.controls.update_tts(values)

    def forward_live_stats(self, stats: LiveStats) -> None:
        self._latest_live_stats = stats
        now = time.monotonic()
        if now - self._last_live_stats_emit >= 0.25:
            self.live_stats_changed.emit(stats)
            self._last_live_stats_emit = now
        else:
            # Mantiene cachada la última instantánea para no perder el último estado.
            return

    def forward_memory(self, snapshot: MemorySnapshot) -> None:
        if not self.stop_requested or not snapshot.connected:
            self.memory_changed.emit(snapshot)

    def forward_log(self, message: str) -> None:
        self.status_changed.emit("response_log", message)

    @Slot()
    def request_stop(self) -> None:
        self.stop_requested = True
        self.response_queue.stop(wait=False)
        if self.loop is not None and self.loop.is_running() and self.tiktok_service is not None:
            asyncio.run_coroutine_threadsafe(
                self.tiktok_service.disconnect(),
                self.loop,
            )

    def close_loop(self) -> None:
        if self.loop is None:
            return
        try:
            pending = asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            if pending:
                self.loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:
            pass
        finally:
            self.response_queue.stop()
            self.loop.close()
            self.loop = None

    def stop_overlay(self) -> None:
        if self.overlay_process is None or self.overlay_process.poll() is not None:
            return
        self.overlay_process.terminate()
        try:
            self.overlay_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.overlay_process.kill()


class AppController(QObject):
    bot_status_changed = Signal(str, str)
    tiktok_status_changed = Signal(str, str)
    ollama_status_changed = Signal(str, str)
    tts_status_changed = Signal(str, str, str)
    connection_state_changed = Signal(str, str)
    log_message = Signal(str)
    activity_received = Signal(str, str, str, str)
    live_stats_changed = Signal(object)
    live_session_reset = Signal()
    memory_changed = Signal(object)
    voice_settings_changed = Signal(str, str, str, float, float)
    dashboard_settings_changed = Signal(object)
    gifts_settings_changed = Signal(object)
    member_levels_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.worker: PandaWorker | None = None
        self._ollama_warmup_lock = Lock()
        self._ollama_warmup_thread: Thread | None = None
        self._overlay_start_lock = Lock()
        self._overlay_start_thread: Thread | None = None
        self._gift_services_activated = False
        self._gift_cache_thread: Thread | None = None
        self.current_username = ""
        self.voice_manager = get_voice_manager()
        self.overlay_access_token = secrets.token_urlsafe(32)
        self.overlay_process: subprocess.Popen | None = None
        self.cloudflare_tunnel = CloudflareTunnel(self.overlay_access_token)

        settings = self.read_settings()
        raw_dashboard = settings.get("dashboard", {})
        self.dashboard_settings = dashboard_defaults(
            raw_dashboard if isinstance(raw_dashboard, dict) else {}
        )
        self.tts_settings = self.normalize_tts(settings.get("tts", {}))
        raw_gifts = settings.get("gifts", {})
        self.gifts_settings = {**GIFT_DEFAULTS, **MEMBER_LEVEL_DEFAULTS, **(raw_gifts if isinstance(raw_gifts, dict) else {})}
        self.gifts_settings = spotify_defaults(self.gifts_settings)
        self.spotify_runtime = SpotifyRuntime(self.gifts_settings)
        self.spotify_runtime.state_changed.connect(self.forward_spotify_status)
        self.spotify_runtime.announce_callback = self.announce_music_request
        self.gift_animations = GiftAnimationManager(self.gifts_settings)
        self.member_levels = MemberLevelManager(self.gifts_settings)
        raw_watchdog = settings.get("live_watchdog", {})
        self.watchdog_settings = {**WATCHDOG_DEFAULTS, **(raw_watchdog if isinstance(raw_watchdog, dict) else {})}
        self.live_watchdog = LiveWatchdog(self.watchdog_settings)
        if bool(self.watchdog_settings.get("enabled")):
            self.live_watchdog.start()

    def publish_initial_state(self) -> None:
        self.publish_voice_settings()
        engine_code = str(self.tts_settings["engine"])
        engine = self.voice_manager.get_engine(engine_code)
        available = engine.is_available()
        self.tts_status_changed.emit(
            "DISPONIBLE" if available else "NO DISPONIBLE",
            "statusGreen" if available else "statusRed",
            engine.display_name,
        )

    @Slot(str)
    def connect_all(self, username: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            return

        self.current_username = username
        self.bot_status_changed.emit("INICIANDO", "statusRed")
        self.tiktok_status_changed.emit("CONECTANDO", "statusRed")
        self.ollama_status_changed.emit("VERIFICANDO", "statusRed")
        self.publish_initial_state()
        self.connection_state_changed.emit(
            "connecting",
            f"Preparando PandaIA para {username}...",
        )
        self.log_message.emit(f"Iniciando PandaIA para {username}.")
        self.live_session_reset.emit()
        self.live_stats_changed.emit(LiveStats())
        self.warmup_ollama_async()
        self.start_overlay_async()

        self.worker = PandaWorker(
            username,
            dict(self.dashboard_settings),
            dict(self.tts_settings),
            dict(self.gifts_settings),
            music_callback=self.spotify_runtime.submit_query,
            gift_animation_callback=self.gift_animations.handle_gift,
            member_level_callback=self.observe_member_level,
            voice_manager=self.voice_manager,
        )
        self.worker.status_changed.connect(self.handle_worker_status)
        self.worker.activity_received.connect(self.forward_activity)
        self.worker.live_stats_changed.connect(self.live_stats_changed.emit)
        self.worker.live_session_reset.connect(self.live_session_reset.emit)
        self.worker.memory_changed.connect(self.memory_changed.emit)
        self.worker.error_occurred.connect(self.handle_worker_error)
        self.worker.finished.connect(self.handle_worker_finished)
        self.worker.start()

    def start_overlay_server(self) -> None:
        with self._overlay_start_lock:
            if self.overlay_process is not None and self.overlay_process.poll() is None:
                return
            if PandaWorker.check_url(OVERLAY_HEALTH_URL, 0.5):
                return
            environment = os.environ.copy(); environment["PANDAIA_OVERLAY_ACCESS_TOKEN"] = self.overlay_access_token
            flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            try:
                command = [sys.executable, "--overlay-server"] if is_frozen() else [sys.executable, "-m", "overlay.server"]
                self.overlay_process = subprocess.Popen(
                    command, env=environment,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
                )
            except OSError as error:
                self.log_message.emit(f"No se pudo iniciar el servidor local del overlay: {error}")

    def start_overlay_async(self) -> None:
        if self._overlay_start_thread is not None and self._overlay_start_thread.is_alive():
            return
        self._overlay_start_thread = Thread(
            target=self.start_overlay_server, name="pandaia-overlay-start", daemon=True
        )
        self._overlay_start_thread.start()

    def activate_gifts_services(self) -> None:
        self.start_overlay_async()
        if not self._gift_services_activated:
            self._gift_services_activated = True
            self._gift_cache_thread = Thread(
                target=prune_gift_cache, name="pandaia-gift-cache", daemon=True
            )
            self._gift_cache_thread.start()

    @Slot(str, str)
    def forward_spotify_status(self, _state: str, message: str) -> None:
        self.log_message.emit(message)

    @Slot()
    def disconnect_all(self) -> None:
        if self.worker is None:
            self.set_disconnected("PandaIA ya está desconectado.")
            return

        self.connection_state_changed.emit(
            "disconnecting",
            "Desconectando PandaIA...",
        )
        self.bot_status_changed.emit("DETENIENDO", "statusRed")
        self.tiktok_status_changed.emit("DESCONECTANDO", "statusRed")
        self.log_message.emit("Desconectando PandaIA.")
        self.live_watchdog.set_live_state(False, manual=True)
        self.worker.request_stop()

    @Slot(str, object)
    def update_dashboard_setting(self, key: str, value: object) -> None:
        self.dashboard_settings[key] = value
        self.save_dashboard_settings()
        if self.worker is not None:
            self.worker.update_setting(key, value)
        if key in {"model", "respond_comments", "autonomous_mode"} and bool(value):
            self.warmup_ollama_async()

        setting_names = {
            "model": "Modelo de Ollama",
            "personality": "Personalidad",
            "language": "Idioma",
            "response_length": "Longitud de respuesta",
            "respond_comments": "Responder a comentarios",
            "read_gifts": "Leer regalos en voz alta",
            "use_memory": "Usar memoria",
            "command_only_mode": "Responder solo con comando /",
            "autonomous_mode": "Modo IA autónomo",
        }
        name = setting_names.get(key, key)
        status = "Activado" if value is True else "Desactivado" if value is False else str(value)
        self.log_message.emit(f"{name}: {status}")

    def warmup_ollama_async(self) -> None:
        model = str(self.dashboard_settings.get("model", "")).strip()
        if not model or not self._ollama_warmup_lock.acquire(blocking=False):
            return

        def run() -> None:
            try:
                OllamaService(timeout=5.0, logger=self.log_message.emit).warmup(model)
            except Exception as error:
                self.log_message.emit(f"Calentamiento de Ollama falló: modelo={model}, error={error}")
            finally:
                self._ollama_warmup_lock.release()

        self._ollama_warmup_thread = Thread(
            target=run, name="pandaia-controller-warmup", daemon=True
        )
        self._ollama_warmup_thread.start()

    @Slot()
    def edit_personality(self) -> None:
        dialog = PersonalityDialog(
            model=str(self.dashboard_settings.get("model", "")),
            language=str(self.dashboard_settings.get("language", "Español")),
            custom_name=str(
                self.dashboard_settings.get("custom_personality_name", "Mi personalidad")
            ),
            custom_prompt=str(self.dashboard_settings.get("custom_personality_prompt", "")),
            response_length=str(self.dashboard_settings.get("response_length", "Corta")),
            parent=self.parent(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.settings()
        self.dashboard_settings.update(values)
        self.save_dashboard_settings()
        if self.worker is not None:
            for key, value in values.items():
                self.worker.update_setting(key, value)
        self.dashboard_settings_changed.emit(dict(self.dashboard_settings))
        self.log_message.emit(
            f"Personalidad guardada: {values['custom_personality_name']}"
        )

    @Slot()
    def change_voice(self) -> None:
        dialog = VoiceDialog(
            current_engine=str(self.tts_settings["engine"]),
            current_voice=str(self.tts_settings["voice"]),
            current_speed=float(self.tts_settings["speed"]),
            current_volume=float(self.tts_settings["volume"]),
            manager=self.voice_manager,
            parent=self.parent(),
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.tts_settings = dialog.selected_settings()
        self.save_tts_settings()
        if self.worker is not None:
            self.worker.update_tts_settings(dict(self.tts_settings))
        self.publish_voice_settings()
        self.publish_initial_state()
        self.log_message.emit(
            "Motor y voz guardados: "
            f"{self.tts_settings['engine']} · "
            f"{self.tts_settings['display_name']}"
        )

    def publish_voice_settings(self) -> None:
        self.voice_settings_changed.emit(
            str(self.tts_settings["display_name"]),
            str(self.tts_settings["language"]),
            str(self.tts_settings["engine"]),
            float(self.tts_settings["speed"]),
            float(self.tts_settings["volume"]),
        )

    @Slot(str, str, str, str)
    def forward_activity(self, icon: str, title: str, user: str, amount: str) -> None:
        self.activity_received.emit(icon, title, user, amount)
        activity_text = f"{title} — {user}"
        if amount:
            activity_text += f" — {amount}"
        self.log_message.emit(activity_text)

    @Slot(str, str)
    def handle_worker_status(self, status: str, message: str) -> None:
        self.log_message.emit(message)

        if status == "ollama_connected":
            self.ollama_status_changed.emit("CONECTADO", "statusGreen")
        elif status == "ollama_unavailable":
            self.ollama_status_changed.emit("NO DISPONIBLE", "statusRed")
        elif status in {"tts_available", "tts_missing"}:
            self.publish_initial_state()
        elif status == "response_log":
            return
        elif status in {"overlay_starting", "overlay_ready", "tiktok_connecting"}:
            self.connection_state_changed.emit("connecting", message)
        elif status == "tiktok_connected":
            self.live_watchdog.set_live_state(True)
            self.spotify_runtime.set_tiktok_connected(True)
            self.bot_status_changed.emit("● CONECTADO", "statusGreen")
            self.tiktok_status_changed.emit("LIVE", "statusRed")
            self.connection_state_changed.emit("connected", message)
        elif status == "tiktok_disconnected":
            self.live_watchdog.set_live_state(False, manual=False)
            self.set_disconnected(message)

    @Slot(str)
    def handle_worker_error(self, error_message: str) -> None:
        message = f"No se pudo iniciar PandaIA: {error_message}"
        self.log_message.emit(message)
        self.bot_status_changed.emit("ERROR", "statusRed")
        self.tiktok_status_changed.emit("DESCONECTADO", "statusRed")
        self.connection_state_changed.emit("error", message)

    @Slot()
    def handle_worker_finished(self) -> None:
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self.set_disconnected(
            f"Desconectado de {self.current_username}."
            if self.current_username
            else "PandaIA desconectado."
        )

    def set_disconnected(self, message: str) -> None:
        self.spotify_runtime.set_tiktok_connected(False)
        self.bot_status_changed.emit("DESCONECTADO", "statusRed")
        self.tiktok_status_changed.emit("DESCONECTADO", "statusRed")
        self.connection_state_changed.emit("disconnected", message)
        self.log_message.emit(message)

    def save_dashboard_settings(self) -> None:
        settings = self.read_settings()
        settings["dashboard"] = self.dashboard_settings
        self.write_settings(settings)

    def save_tts_settings(self) -> None:
        settings = self.read_settings()
        settings["tts"] = self.tts_settings
        self.write_settings(settings)

    def update_gifts_settings(self, values: dict[str, object]) -> None:
        self.gifts_settings.update(values)
        self.spotify_runtime.update_settings(values)
        self.gift_animations.update_settings(values)
        self.member_levels.update_settings(values)
        if self.worker is not None: self.worker.update_music_command(values.get("command", "a/"))
        settings = self.read_settings()
        settings["gifts"] = self.gifts_settings
        self.write_settings(settings)
        self.gifts_settings_changed.emit(dict(self.gifts_settings))

    def observe_member_level(self, user: object, *, event_id: str = "") -> bool:
        sent = self.member_levels.observe_user(user, event_id=event_id)
        self.member_levels_changed.emit(self.member_levels.history.top(100))
        return sent

    def update_watchdog_settings(self, values: dict[str, object]) -> None:
        self.watchdog_settings.update(values); self.live_watchdog.update_settings(values)
        self.live_watchdog.set_enabled(bool(self.watchdog_settings.get("enabled")))
        if bool(self.watchdog_settings.get("enabled")) and not self.live_watchdog.isRunning():
            self.live_watchdog.start()
        settings = self.read_settings(); settings["live_watchdog"] = self.watchdog_settings; self.write_settings(settings)

    def open_live_studio(self) -> None:
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "TikTok LIVE Studio" / "TikTok LIVE Studio.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "TikTok LIVE Studio" / "TikTok LIVE Studio.exe",
        ]
        executable = next((path for path in candidates if path.is_file()), None)
        if executable is None: self.log_message.emit("No se encontró TikTok Live Studio. Ábrelo manualmente desde Windows."); return
        try: subprocess.Popen([str(executable)], creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as error: self.log_message.emit(f"No se pudo abrir TikTok Live Studio: {error}")

    def announce_music_request(self, text: str) -> None:
        try:
            self.voice_manager.speak(
                engine=str(self.tts_settings["engine"]), text=text,
                voice=str(self.tts_settings["voice"]), speed=float(self.tts_settings["speed"]),
                volume=float(self.tts_settings["volume"]),
            )
        except Exception as error:
            self.log_message.emit(f"No se pudo anunciar la solicitud musical: {error}")

    @staticmethod
    def normalize_tts(raw_settings: object) -> dict[str, object]:
        settings = raw_settings if isinstance(raw_settings, dict) else {}
        return {
            "engine": str(settings.get("engine", "kokoro")),
            "voice": str(settings.get("voice", "ef_dora")),
            "display_name": str(settings.get("display_name", "Dora")),
            "language": str(settings.get("language", "Español")),
            "gender": str(settings.get("gender", "Femenina")),
            "style": str(settings.get("style", "Clara y expresiva")),
            "speed": float(settings.get("speed", 1.0)),
            "volume": float(settings.get("volume", 1.0)),
        }

    @staticmethod
    def read_settings() -> dict:
        return read_settings(CONFIG_FILE)

    @staticmethod
    def write_settings(settings: dict) -> None:
        write_settings_atomic(CONFIG_FILE, settings)

    def shutdown(self) -> None:
        self.cloudflare_tunnel.stop()
        self.live_watchdog.shutdown()
        self.spotify_runtime.stop()
        if self._overlay_start_thread is not None and self._overlay_start_thread.is_alive():
            self._overlay_start_thread.join(timeout=1.0)
        if self._ollama_warmup_thread is not None and self._ollama_warmup_thread.is_alive():
            self._ollama_warmup_thread.join(timeout=5.5)
        if self._gift_cache_thread is not None and self._gift_cache_thread.is_alive():
            self._gift_cache_thread.join(timeout=1.0)
        if self.worker is not None:
            self.worker.request_stop()
            self.worker.wait(5000)
        if self.overlay_process is not None and self.overlay_process.poll() is None:
            self.overlay_process.terminate()
            try: self.overlay_process.wait(timeout=3)
            except subprocess.TimeoutExpired: self.overlay_process.kill(); self.overlay_process.wait(timeout=2)
