from __future__ import annotations

from email.message import Message
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError, URLError

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path: sys.path.insert(0, str(path))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.views.gifts_view import SpotifyAuthWorker
from services.spotify.client import SpotifyAPIError, SpotifyClient
from services.spotify.credential_store import MemoryCredentialStore
from services.spotify.local_store import SpotifyLocalStore
from services.spotify.runtime import SpotifyRuntime


class Response:
    def __init__(self, data: object): self.data = json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self): return self.data


def wait_for(app, predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate(): return
        time.sleep(.01)
    raise AssertionError("Spotify no terminó a tiempo")


class RuntimeClient:
    def __init__(self, store, *, premium=True, device=True, error=None, gate=None):
        self.store = store; self.premium = premium; self.device = device
        self.error = error; self.gate = gate; self.reconnect_calls = 0
    def reconnect(self):
        self.reconnect_calls += 1
        if self.gate: self.gate.wait(1)
        if self.error: raise self.error
        if not self.premium: raise SpotifyAPIError("Premium requerido", status=403)
        return {"account": {"id": "cuenta", "display_name": "Cuenta", "product": "premium"},
                "device": {"id": "d", "name": "PC", "is_active": True} if self.device else None}
    def account_and_device(self): return self.reconnect()
    def playback(self): return {}
    def playback_queue(self): return {"currently_playing": None, "queue": []}


class SpotifyReconnectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def make_store(self, directory, refresh="refresh-token"):
        credentials = MemoryCredentialStore(refresh)
        store = SpotifyLocalStore(Path(directory) / "spotify_local.json", credentials)
        store.save_client_id("local-client-id")
        return store, credentials

    def test_refresh_reconnects_and_access_token_is_memory_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store, credentials = self.make_store(directory)
            calls = []
            def opener(request, **_kwargs):
                calls.append(request.full_url)
                if request.full_url.endswith("/api/token"):
                    return Response({"access_token": "temporary-access", "expires_in": 3600})
                if request.full_url.endswith("/me"): return Response({"id": "a", "product": "premium"})
                return Response({"devices": [{"id": "d", "is_active": True}]})
            data = SpotifyClient(store, opener).reconnect()
            self.assertEqual(data["device"]["id"], "d")
            self.assertEqual(credentials.get(), "refresh-token")
            disk = (Path(directory) / "spotify_local.json").read_text(encoding="utf-8")
            self.assertNotIn("temporary-access", disk)
            self.assertNotIn("refresh-token", disk)
            self.assertEqual(calls[0], "https://accounts.spotify.com/api/token")

    def test_expired_access_token_is_renewed(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _credentials = self.make_store(directory)
            store.save({"access_token": "expired", "expires_at": time.time() - 1})
            calls = []
            def opener(request, **_kwargs):
                calls.append(request.full_url)
                if request.full_url.endswith("/api/token"):
                    return Response({"access_token": "renewed", "expires_in": 3600})
                return Response({"id": "a", "product": "premium"})
            SpotifyClient(store, opener).request("GET", "/me")
            self.assertIn("renewed", store.load()["access_token"])
            self.assertEqual(calls.count("https://accounts.spotify.com/api/token"), 1)

    def test_premium_no_device_and_non_premium_states(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _ = self.make_store(directory)
            client = RuntimeClient(store, device=False)
            runtime = SpotifyRuntime({}, client); states = []
            runtime.state_changed.connect(lambda state, message: states.append((state, message)))
            runtime.reconnect(); wait_for(self.app, lambda: any(s == "Sin dispositivo activo" for s, _ in states))
            self.assertTrue(runtime.spotify_ready); runtime.stop()

        with tempfile.TemporaryDirectory() as directory:
            store, _ = self.make_store(directory)
            runtime = SpotifyRuntime({}, RuntimeClient(store, premium=False)); states = []
            runtime.state_changed.connect(lambda state, message: states.append((state, message)))
            runtime.reconnect(); wait_for(self.app, lambda: any(s == "Premium requerido" for s, _ in states))
            self.assertFalse(runtime.spotify_ready); runtime.stop()

    def test_revoked_refresh_is_deleted_but_offline_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            store, credentials = self.make_store(directory)
            headers = Message()
            revoked = lambda *_a, **_k: (_ for _ in ()).throw(
                HTTPError("url", 400, "revoked", headers, io.BytesIO(b"revoked"))
            )
            with self.assertRaises(SpotifyAPIError) as caught:
                SpotifyClient(store, revoked).reconnect()
            self.assertEqual(caught.exception.status, 401)
            self.assertEqual(credentials.get(), "")

        with tempfile.TemporaryDirectory() as directory:
            store, credentials = self.make_store(directory)
            offline = lambda *_a, **_k: (_ for _ in ()).throw(URLError("offline"))
            with self.assertRaises(SpotifyAPIError) as caught:
                SpotifyClient(store, offline).reconnect()
            self.assertEqual(caught.exception.status, 0)
            self.assertEqual(credentials.get(), "refresh-token")

    def test_change_account_replaces_refresh_and_disconnect_cleans_everything(self):
        self.assertTrue(SpotifyAuthWorker("client", show_dialog=True).show_dialog)
        with tempfile.TemporaryDirectory() as directory:
            store, credentials = self.make_store(directory, "old-refresh")
            store.save_authorization({"refresh_token": "new-refresh", "scopes": ["user-read-private"]})
            self.assertEqual(credentials.get(), "new-refresh")
            client = RuntimeClient(store)
            runtime = SpotifyRuntime({}, client); runtime.spotify_ready = True
            runtime.disconnect(); runtime.stop()
            self.assertEqual(credentials.get(), "")
            self.assertNotIn("account_id", store.load())
            self.assertFalse(runtime.spotify_ready)

    def test_duplicate_reconnect_is_prevented(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _ = self.make_store(directory)
            gate = threading.Event(); client = RuntimeClient(store, gate=gate)
            runtime = SpotifyRuntime({}, client)
            self.assertTrue(runtime.reconnect())
            self.assertFalse(runtime.reconnect())
            gate.set(); wait_for(self.app, lambda: client.reconnect_calls == 1)
            runtime.stop(); self.assertEqual(client.reconnect_calls, 1)

    def test_errors_and_metadata_do_not_expose_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            store, _ = self.make_store(directory, "never-log-this-refresh")
            client = RuntimeClient(store, error=SpotifyAPIError("Spotify no disponible"))
            runtime = SpotifyRuntime({}, client); messages = []
            runtime.state_changed.connect(lambda state, message: messages.append(state + message))
            runtime.reconnect(); wait_for(self.app, lambda: bool(messages))
            runtime.stop()
            self.assertNotIn("never-log-this-refresh", "".join(messages))


if __name__ == "__main__": unittest.main()
