from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QDialog

from app.dialogs.voice_dialog import VoiceDialog
from services.tiktok.tiktok_service import TikTokService
from services.tts.voice_manager import VoiceManager

OVERLAY_HEALTH_URL = "http://127.0.0.1:5050/health"
OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"
CONFIG_FILE = Path("config/settings.json")


class PandaWorker(QThread):
    status_changed = Signal(str, str)
    activity_received = Signal(str, str, str, str)
    error_occurred = Signal(str)

    def __init__(self, username: str) -> None:
        super().__init__()
        self.username = username
        self.loop: asyncio.AbstractEventLoop | None = None
        self.tiktok_service: TikTokService | None = None
        self.overlay_process: subprocess.Popen | None = None
        self.overlay_started_here = False
        self.stop_requested = False

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

            if VoiceManager().is_engine_available("kokoro"):
                self.status_changed.emit(
                    "kokoro_available",
                    "Kokoro TTS disponible.",
                )
            else:
                self.status_changed.emit(
                    "kokoro_missing",
                    "Kokoro TTS no está instalado.",
                )

            if self.stop_requested:
                return

            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.tiktok_service = TikTokService(
                username=self.username,
                status_callback=self.forward_tiktok_status,
                activity_callback=self.forward_activity,
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
        if self.check_url(OVERLAY_HEALTH_URL, 1):
            return

        project_root = Path(__file__).resolve().parents[1]
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.overlay_process = subprocess.Popen(
            [sys.executable, "-m", "overlay.server"],
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        self.overlay_started_here = True

        for _ in range(30):
            if self.stop_requested:
                raise RuntimeError("Inicio cancelado.")
            if self.check_url(OVERLAY_HEALTH_URL, 1):
                return
            if self.overlay_process is not None and self.overlay_process.poll() is not None:
                raise RuntimeError("El overlay se cerró durante el inicio.")
            time.sleep(0.2)

        raise RuntimeError("El overlay no respondió.")

    @staticmethod
    def check_url(url: str, timeout: float) -> bool:
        try:
            with urlopen(url, timeout=timeout) as response:
                return 200 <= response.status < 300
        except (URLError, TimeoutError, OSError):
            return False

    def forward_tiktok_status(self, status: str, message: str) -> None:
        self.status_changed.emit(status, message)

    def forward_activity(self, icon: str, title: str, user: str, amount: str) -> None:
        self.activity_received.emit(icon, title, user, amount)

    @Slot()
    def request_stop(self) -> None:
        self.stop_requested = True
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
    kokoro_status_changed = Signal(str, str)
    connection_state_changed = Signal(str, str)
    log_message = Signal(str)
    activity_received = Signal(str, str, str, str)
    voice_settings_changed = Signal(str, str, str, float, float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.worker: PandaWorker | None = None
        self.current_username = ""
        self.voice_manager = VoiceManager()

        settings = self.read_settings()
        self.dashboard_settings: dict[str, object] = dict(
            settings.get(
                "dashboard",
                {
                    "model": "llama3:8b",
                    "personality": "Amigable, divertida y carismática",
                    "language": "Español",
                    "respond_comments": True,
                    "read_gifts": True,
                    "use_memory": True,
                    "automatic_responses": True,
                    "autonomous_mode": True,
                },
            )
        )
        self.tts_settings = self.normalize_tts(settings.get("tts", {}))

    def publish_initial_state(self) -> None:
        self.publish_voice_settings()
        kokoro_available = self.voice_manager.is_engine_available("kokoro")
        self.kokoro_status_changed.emit(
            "DISPONIBLE" if kokoro_available else "NO INSTALADO",
            "statusGreen" if kokoro_available else "statusRed",
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

        self.worker = PandaWorker(username)
        self.worker.status_changed.connect(self.handle_worker_status)
        self.worker.activity_received.connect(self.forward_activity)
        self.worker.error_occurred.connect(self.handle_worker_error)
        self.worker.finished.connect(self.handle_worker_finished)
        self.worker.start()

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
        self.worker.request_stop()

    @Slot(str, object)
    def update_dashboard_setting(self, key: str, value: object) -> None:
        self.dashboard_settings[key] = value
        self.save_dashboard_settings()

        setting_names = {
            "model": "Modelo de Ollama",
            "personality": "Personalidad",
            "language": "Idioma",
            "respond_comments": "Responder a comentarios",
            "read_gifts": "Leer regalos en voz alta",
            "use_memory": "Usar memoria",
            "automatic_responses": "Respuestas automáticas",
            "autonomous_mode": "Modo IA autónomo",
        }
        name = setting_names.get(key, key)
        status = "Activado" if value is True else "Desactivado" if value is False else str(value)
        self.log_message.emit(f"{name}: {status}")

    @Slot()
    def edit_personality(self) -> None:
        current_personality = str(
            self.dashboard_settings.get(
                "personality",
                "Amigable, divertida y carismática",
            )
        )
        self.log_message.emit(
            "Editar personalidad seleccionado. "
            f"Personalidad actual: {current_personality}"
        )

    @Slot()
    def change_voice(self) -> None:
        dialog = VoiceDialog(
            current_engine=str(self.tts_settings["engine"]),
            current_voice=str(self.tts_settings["voice"]),
            current_speed=float(self.tts_settings["speed"]),
            current_volume=float(self.tts_settings["volume"]),
            parent=self.parent(),
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.tts_settings = dialog.selected_settings()
        self.save_tts_settings()
        self.publish_voice_settings()
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
        elif status == "kokoro_available":
            self.kokoro_status_changed.emit("DISPONIBLE", "statusGreen")
        elif status == "kokoro_missing":
            self.kokoro_status_changed.emit("NO INSTALADO", "statusRed")
        elif status in {"overlay_starting", "overlay_ready", "tiktok_connecting"}:
            self.connection_state_changed.emit("connecting", message)
        elif status == "tiktok_connected":
            self.bot_status_changed.emit("● CONECTADO", "statusGreen")
            self.tiktok_status_changed.emit("LIVE", "statusRed")
            self.connection_state_changed.emit("connected", message)
        elif status == "tiktok_disconnected":
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
        if not CONFIG_FILE.exists():
            return {}
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def write_settings(settings: dict) -> None:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps(settings, indent=4, ensure_ascii=False),
            encoding="utf-8",
        )

    def shutdown(self) -> None:
        if self.worker is None:
            return
        self.worker.request_stop()
        self.worker.wait(5000)