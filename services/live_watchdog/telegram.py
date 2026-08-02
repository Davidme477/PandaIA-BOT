from __future__ import annotations

import json
import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from core.app_paths import get_paths


TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")


def redact_secret(value: object, token: str = "") -> str:
    text = str(value)
    if token: text = text.replace(token, "[TOKEN OCULTO]")
    return TOKEN_RE.sub("[TOKEN OCULTO]", text)


class TelegramError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, retry_after: int = 0) -> None:
        super().__init__(message); self.status = status; self.retry_after = retry_after


class TelegramLocalStore:
    def __init__(self, path: Path | str | None = None) -> None:
        path = path or get_paths().telegram_file
        self.path = Path(path)

    def load(self) -> dict[str, object]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError): return {}

    def save(self, values: dict[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True); temporary_name = ""
        try:
            with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                   prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as temporary:
                temporary_name = temporary.name; json.dump(values, temporary, ensure_ascii=False, indent=2)
                temporary.write("\n"); temporary.flush(); os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
        finally:
            if temporary_name: Path(temporary_name).unlink(missing_ok=True)

    def clear(self) -> None: self.path.unlink(missing_ok=True)


class TelegramClient:
    def __init__(self, token: str, *, opener=urlopen, timeout: float = 10) -> None:
        self.token = token.strip(); self.opener = opener; self.timeout = timeout

    def call(self, method: str, values: dict[str, object] | None = None) -> object:
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        request = Request(url, data=urlencode(values or {}).encode(), method="POST")
        try:
            with self.opener(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            retry = int(error.headers.get("Retry-After", "0") or 0)
            raise TelegramError(self._http_message(error.code), status=error.code, retry_after=retry) from None
        except (URLError, TimeoutError, OSError) as error:
            raise TelegramError("Telegram no está disponible. Revisa Internet e inténtalo nuevamente.") from error
        except (ValueError, json.JSONDecodeError) as error:
            raise TelegramError("Telegram devolvió una respuesta inválida.") from error
        if not payload.get("ok"):
            status = int(payload.get("error_code", 0)); parameters = payload.get("parameters") or {}
            raise TelegramError(self._http_message(status), status=status,
                                retry_after=int(parameters.get("retry_after", 0)))
        return payload.get("result")

    @staticmethod
    def _http_message(status: int) -> str:
        return {401: "Token de Telegram inválido.", 403: "El bot fue bloqueado o no tiene permiso.",
                409: "Telegram detectó otro long polling activo.", 429: "Telegram limitó temporalmente los envíos."}.get(
                    status, f"Error controlado de Telegram ({status}).")

    def validate(self) -> dict: return dict(self.call("getMe") or {})

    def detect_private_chat(self, offset: int = 0) -> tuple[str, str, int]:
        updates = list(self.call("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": '["message"]'}) or [])
        candidates = []
        for update in updates:
            message = update.get("message") or {}; chat = message.get("chat") or {}
            if chat.get("type") != "private": continue
            text = str(message.get("text", "")).strip().casefold()
            priority = 1 if text in {"/start", "hola"} else 0
            name = " ".join(filter(None, (chat.get("first_name"), chat.get("last_name")))) or chat.get("username") or "Chat privado"
            candidates.append((priority, int(update.get("update_id", 0)), str(chat.get("id", "")), str(name)))
        if not candidates: raise TelegramError("Abre PandaIA Alertas en Telegram, pulsa Iniciar y envía Hola.")
        _priority, update_id, chat_id, name = max(candidates)
        return chat_id, name, update_id + 1

    def send_message(self, chat_id: str, text: str, *, alert_id: str = "") -> object:
        values: dict[str, object] = {"chat_id": chat_id, "text": text, "disable_notification": "false"}
        if alert_id:
            values["reply_markup"] = json.dumps({"inline_keyboard": [[{
                "text": "✅ Alarma atendida", "callback_data": f"watchdog_ack:{alert_id}"}]]})
        return self.call("sendMessage", values)

    def send_photo(self, chat_id: str, photo: bytes, caption: str) -> object:
        # Multipart mínimo para Bot API; la imagen ya debe estar recortada a TikTok.
        boundary = "PandaIAWatchdogBoundary"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"alerta.png\"\r\n"
                "Content-Type: image/png\r\n\r\n").encode() + photo + f"\r\n--{boundary}--\r\n".encode()
        request = Request(f"https://api.telegram.org/bot{self.token}/sendPhoto", data=body,
                          headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
        try:
            with self.opener(request, timeout=self.timeout) as response: payload = json.loads(response.read().decode())
        except Exception as error: raise TelegramError(redact_secret(error, self.token)) from None
        if not payload.get("ok"): raise TelegramError("No se pudo enviar la captura.")
        return payload.get("result")
