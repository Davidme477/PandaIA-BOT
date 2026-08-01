from __future__ import annotations

import threading
import time
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from services.live_watchdog.alarm import AlertCycle
from services.live_watchdog.detector import ConsecutiveWarningDetector, find_live_studio
from services.live_watchdog.telegram import TelegramClient, TelegramError, TelegramLocalStore, redact_secret

WATCHDOG_DEFAULTS = {"enabled": False, "process_hint": "TikTok Live Studio", "attach_screenshot": False,
                     "repeat_interval": 60, "repeat_duration": 240}


class LiveWatchdog(QThread):
    status_changed = Signal(str, str, str, str); alert_logged = Signal(str)
    banner_changed = Signal(bool, str); telegram_changed = Signal(str, str)

    def __init__(self, settings=None, *, store=None, clock=time.monotonic,
                 process_finder=find_live_studio, text_reader=None, alarm_callback=None) -> None:
        super().__init__(); self.settings = {**WATCHDOG_DEFAULTS, **(settings or {})}
        self.store = store or TelegramLocalStore(); self.clock = clock; self.process_finder = process_finder
        self.text_reader = text_reader or self._read_accessible_text; self.alarm_callback = alarm_callback or self._beep
        self._async_alarm = alarm_callback is None; self.state_lock = threading.RLock()
        self.stop_event = threading.Event(); self.enabled_event = threading.Event(); self.detector = ConsecutiveWarningDetector()
        self.cycle = AlertCycle(); self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="PandaIA-Telegram")
        self.live_expected = False; self.manual_disconnect = False; self._process_seen = False
        self._poll_pending = False
        if self.settings["enabled"]: self.enabled_event.set()

    def run(self) -> None:
        while not self.stop_event.wait(2.5):
            if not self.enabled_event.is_set(): continue
            try: self._check_once()
            except Exception as error: self.status_changed.emit("Error de detección", "", self._now(), redact_secret(error))

    def _check_once(self) -> None:
        found, name = self.process_finder(str(self.settings["process_hint"]))
        if not found:
            if self._process_seen and self.live_expected and not self.manual_disconnect:
                self.trigger_alert("Cierre inesperado de TikTok Live Studio", "process_closed")
            self._process_seen = False; self.status_changed.emit("Buscando TikTok Live Studio", "", self._now(), "")
            self._repeat_if_due("TikTok Live Studio"); self._poll_acknowledgement(); return
        self._process_seen = True; self.status_changed.emit("Supervisando", name, self._now(), "")
        match = self.detector.inspect(self.text_reader(name))
        if match: self.cycle.observe_present(); self.trigger_alert(match.kind, match.event_id)
        elif self.cycle.event_id and not self.cycle.attended and self.cycle.observe_missing(): self.stop_alarm("La advertencia desapareció.")
        self._repeat_if_due(name)
        self._poll_acknowledgement()

    def trigger_alert(self, kind: str, event_id: str = "simulation") -> None:
        with self.state_lock: fresh = self.cycle.start(event_id, self.clock())
        if fresh:
            self.status_changed.emit("Advertencia detectada", "TikTok Live Studio", self._now(), kind)
            self.banner_changed.emit(True, f"TikTok requiere atención — {kind}"); self.alert_logged.emit(f"{self._now()} — {kind}")
        self._repeat_if_due("TikTok Live Studio", kind)

    def _repeat_if_due(self, process_name: str, kind: str = "") -> None:
        with self.state_lock:
            due, final = self.cycle.due(self.clock(), int(self.settings["repeat_interval"]), int(self.settings["repeat_duration"]))
        if not due: return
        if self._async_alarm: self.executor.submit(self.alarm_callback)
        else: self.alarm_callback()
        warning = kind or "TikTok Live Studio solicita confirmar actividad."
        suffix = "\nLa ventana de validación podría estar por expirar." if final else ""
        message = (f"🚨 ALERTA PANDAIA\n\n{warning}\n\nTipo: {warning}\nHora: {self._now()}\nPC: {process_name} detectado\n\n"
                   "Revisa tu computadora para evitar que el live finalice.\n\n"
                   "Este botón silencia la alarma, pero no confirma la advertencia dentro de TikTok." + suffix)
        self._submit_telegram(message, self.cycle.event_id)

    def _submit_telegram(self, message: str, alert_id: str) -> None:
        local = self.store.load(); token, chat_id = str(local.get("bot_token", "")), str(local.get("chat_id", ""))
        if not token or not chat_id: return
        def send():
            try:
                client = TelegramClient(token); client.send_message(chat_id, message, alert_id=alert_id)
                if bool(self.settings.get("attach_screenshot")):
                    photo = self._capture_tiktok_window()
                    if photo: client.send_photo(chat_id, photo, "Advertencia visible en TikTok Live Studio")
            except TelegramError as error: self.telegram_changed.emit("Error de Telegram", redact_secret(error, token))
        self.executor.submit(send)

    def save_token(self, token: str) -> None:
        token = token.strip()
        def work():
            try:
                TelegramClient(token).validate(); values = self.store.load(); values["bot_token"] = token
                self.store.save(values); self.telegram_changed.emit("Token guardado", str(values.get("chat_name", "")))
            except TelegramError as error: self.telegram_changed.emit("Error de Telegram", redact_secret(error, token))
        self.executor.submit(work)

    def detect_chat(self) -> None:
        local = self.store.load(); token = str(local.get("bot_token", ""))
        if not token: self.telegram_changed.emit("No configurado", "Guarda primero el token."); return
        self.telegram_changed.emit("Buscando chat", "")
        def work():
            try:
                chat_id, name, offset = TelegramClient(token).detect_private_chat(int(local.get("update_offset", 0)))
                local.update({"chat_id": chat_id, "chat_name": name, "update_offset": offset}); self.store.save(local)
                self.telegram_changed.emit("Chat conectado", name)
            except TelegramError as error: self.telegram_changed.emit("Error de Telegram", redact_secret(error, token))
        self.executor.submit(work)

    def test_telegram(self) -> None:
        self._submit_telegram("🚨 ALERTA PANDAIA\n\nEsta es una alerta de prueba. No se realizó ninguna acción en TikTok.", "test")

    def disconnect_telegram(self) -> None: self.store.clear(); self.telegram_changed.emit("No configurado", "")

    def _poll_acknowledgement(self) -> None:
        if self._poll_pending or not self.cycle.event_id or self.cycle.attended: return
        local = self.store.load(); token = str(local.get("bot_token", ""))
        if not token: return
        self._poll_pending = True
        def work():
            try:
                updates = list(TelegramClient(token).call("getUpdates", {"offset": int(local.get("update_offset", 0)), "timeout": 0}) or [])
                for update in updates:
                    callback = update.get("callback_query") or {}; data = str(callback.get("data", ""))
                    if data == f"watchdog_ack:{self.cycle.event_id}": self.stop_alarm("Alarma atendida desde Telegram.")
                if updates:
                    local["update_offset"] = max(int(item.get("update_id", 0)) for item in updates) + 1; self.store.save(local)
            except TelegramError: pass
            finally: self._poll_pending = False
        self.executor.submit(work)

    def set_enabled(self, enabled: bool) -> None:
        self.settings["enabled"] = bool(enabled)
        if enabled: self.enabled_event.set(); self.status_changed.emit("Buscando TikTok Live Studio", "", self._now(), "")
        else: self.enabled_event.clear(); self.stop_alarm("Vigilante desactivado."); self.status_changed.emit("Desactivado", "", self._now(), "")
    def update_settings(self, values) -> None: self.settings.update(values)
    def set_live_state(self, connected: bool, *, manual: bool = False) -> None:
        was_expected = self.live_expected; self.live_expected = connected; self.manual_disconnect = manual
        if was_expected and not connected and not manual and self.enabled_event.is_set():
            self.status_changed.emit("Live desconectado", "TikTok Live Studio", self._now(), "Desconexión inesperada")
            self.trigger_alert("TikTok Live se desconectó inesperadamente.", "live_disconnected")
    def stop_alarm(self, reason="Alarma atendida.") -> None:
        with self.state_lock: self.cycle.acknowledge()
        self.banner_changed.emit(False, ""); self.status_changed.emit("Alarma atendida", "", self._now(), reason)
    def test_alarm(self) -> None:
        if self._async_alarm: self.executor.submit(self.alarm_callback)
        else: self.alarm_callback()
        self.banner_changed.emit(True, "Prueba: TikTok requiere atención")
    def simulate_warning(self) -> None: self.trigger_alert("Advertencia simulada", f"simulation-{int(self.clock())}")
    def shutdown(self) -> None:
        self.stop_event.set(); self.enabled_event.clear(); self.cycle.acknowledge(); self.executor.shutdown(wait=False, cancel_futures=True)
        if self.isRunning(): self.wait(4000)
    @staticmethod
    def _now(): return datetime.now().strftime("%H:%M:%S")
    @staticmethod
    def _beep():
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION); winsound.Beep(1200, 500)
        except (ImportError, RuntimeError, OSError): pass
    @staticmethod
    def _read_accessible_text(_process_name):
        try:
            from pywinauto import Desktop
            windows = Desktop(backend="uia").windows(title_re=".*TikTok.*Live.*Studio.*")
            if not windows: return ""
            accessible = " ".join(str(item.window_text()) for item in windows[0].descendants() if item.window_text())
            if accessible.strip(): return accessible
        except Exception: pass
        # OCR local y opcional: si falta la dependencia, la supervisión UIA continúa sin fallar.
        try:
            from PIL import Image
            import pytesseract
            photo = LiveWatchdog._capture_tiktok_window()
            return pytesseract.image_to_string(Image.open(io.BytesIO(photo)), lang="spa") if photo else ""
        except Exception: return ""

    @staticmethod
    def _capture_tiktok_window() -> bytes:
        """Captura exclusivamente el rectángulo de Live Studio; nunca la pantalla completa."""
        try:
            from PIL import ImageGrab
            from pywinauto import Desktop
            windows = Desktop(backend="uia").windows(title_re=".*TikTok.*Live.*Studio.*")
            if not windows: return b""
            rectangle = windows[0].rectangle(); image = ImageGrab.grab(
                bbox=(rectangle.left, rectangle.top, rectangle.right, rectangle.bottom))
            output = io.BytesIO(); image.save(output, format="PNG"); return output.getvalue()
        except Exception: return b""
