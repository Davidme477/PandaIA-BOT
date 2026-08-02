from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


REDIRECT_URI = "http://127.0.0.1:8765/callback"
SCOPES = (
    "user-modify-playback-state user-read-playback-state "
    "user-read-currently-playing user-read-private"
)


class SpotifyAuthError(RuntimeError):
    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.permanent = permanent


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def validate_state(expected: str, received: str) -> bool:
    return bool(expected and received and secrets.compare_digest(expected, received))


def _safe_error(status: int | None = None) -> SpotifyAuthError:
    suffix = f" (HTTP {status})" if status else ""
    return SpotifyAuthError(
        f"Spotify rechazó la autorización{suffix}. Reconecta la cuenta.", permanent=True
    )


def token_request(values: dict[str, str], opener=urlopen) -> dict[str, object]:
    request = Request(
        "https://accounts.spotify.com/api/token",
        data=urlencode(values).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with opener(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise _safe_error(error.code) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise SpotifyAuthError("Spotify no está disponible temporalmente.") from None
    if not isinstance(result, dict) or not result.get("access_token"):
        raise _safe_error()
    return result


def refresh_access_token(client_id: str, refresh_token: str, opener=urlopen) -> dict[str, object]:
    return token_request({
        "grant_type": "refresh_token", "refresh_token": refresh_token,
        "client_id": client_id,
    }, opener=opener)


class SpotifyOAuthPKCE:
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id.strip()
        self.cancel_event = threading.Event()
        self.server: HTTPServer | None = None

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.server is not None:
            try:
                urlopen(f"{REDIRECT_URI}?state=cancel", timeout=1).close()
            except Exception:
                pass

    def authorize(self, timeout: float = 180.0, *, show_dialog: bool = False) -> dict[str, object]:
        if not self.client_id:
            raise SpotifyAuthError("Configura primero el ID de cliente.")
        verifier, state = generate_code_verifier(), generate_state()
        result: dict[str, str] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(handler_self) -> None:  # noqa: N802
                parsed = urlparse(handler_self.path)
                values = parse_qs(parsed.query)
                if parsed.path != "/callback" or not validate_state(state, values.get("state", [""])[0]):
                    handler_self.send_response(400); handler_self.end_headers()
                    handler_self.wfile.write(b"Solicitud no valida. Puedes cerrar esta ventana.")
                    result["error"] = "state"
                    return
                result["code"] = values.get("code", [""])[0]
                result["error"] = values.get("error", [""])[0]
                handler_self.send_response(200); handler_self.end_headers()
                handler_self.wfile.write(b"Spotify conectado. Puedes volver a PandaIA.")

            def log_message(self, *_args) -> None:
                return

        try:
            self.server = HTTPServer(("127.0.0.1", 8765), Handler)
        except OSError:
            raise SpotifyAuthError("El puerto 8765 está ocupado. Cierra la otra aplicación e inténtalo de nuevo.") from None
        self.server.timeout = 0.5
        authorization_url = "https://accounts.spotify.com/authorize?" + urlencode({
            "client_id": self.client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
            "scope": SCOPES, "state": state, "code_challenge_method": "S256",
            "code_challenge": code_challenge(verifier), "show_dialog": "true" if show_dialog else "false",
        })
        webbrowser.open(authorization_url)
        deadline = time.monotonic() + timeout
        try:
            while not result and not self.cancel_event.is_set() and time.monotonic() < deadline:
                self.server.handle_request()
        finally:
            self.server.server_close()
            self.server = None
        if self.cancel_event.is_set():
            raise SpotifyAuthError("Autorización cancelada.")
        if not result.get("code"):
            raise SpotifyAuthError("Spotify no autorizó la cuenta.")
        return token_request({
            "grant_type": "authorization_code", "code": result["code"],
            "redirect_uri": REDIRECT_URI, "client_id": self.client_id,
            "code_verifier": verifier,
        })
