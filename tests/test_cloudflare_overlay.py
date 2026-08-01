from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path: sys.path.insert(0, str(path))

import overlay.server as overlay_server
from overlay.server import app, client_cursors, enqueue_gift, event_queue, queue_lock
from services.overlay.cloudflare_tunnel import CloudflareTunnel, extract_quick_tunnel_url, find_cloudflared


class HealthResponse:
    status = 200
    def __enter__(self): return self
    def __exit__(self, *_args): return None


class FakeProcess:
    def __init__(self, lines=()): self.stdout = iter(lines); self.returncode = None; self.terminated = False; self.killed = False
    def poll(self): return self.returncode
    def wait(self, timeout=None): self.returncode = 0; return 0
    def terminate(self): self.terminated = True; self.returncode = 0
    def kill(self): self.killed = True; self.returncode = -9


class CloudflareOverlayTests(unittest.TestCase):
    def setUp(self):
        self.previous_token = overlay_server.ACCESS_TOKEN; overlay_server.ACCESS_TOKEN = "token-seguro"
        with queue_lock: event_queue.clear(); client_cursors.clear()

    def tearDown(self): overlay_server.ACCESS_TOKEN = self.previous_token

    def test_cloudflared_detection_and_url_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / "cloudflared.exe"; executable.touch()
            with patch("services.overlay.cloudflare_tunnel.shutil.which", return_value=str(executable)):
                self.assertEqual(find_cloudflared(), executable)
        line = "INF Your quick Tunnel has been created! Visit https://Panda-123.trycloudflare.com now"
        self.assertEqual(extract_quick_tunnel_url(line), "https://panda-123.trycloudflare.com")
        self.assertEqual(extract_quick_tunnel_url("https://evil.example.com"), "")

    def test_external_get_requires_correct_token_and_disables_cache(self):
        client = app.test_client(); headers = {"CF-Connecting-IP": "203.0.113.8"}
        self.assertEqual(client.get("/overlay", headers=headers).status_code, 403)
        self.assertEqual(client.get("/overlay?access=incorrecto", headers=headers).status_code, 403)
        response = client.get("/overlay?access=token-seguro", headers=headers)
        self.assertEqual(response.status_code, 200); self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(client.get("/health?access=incorrecto").status_code, 403)
        self.assertEqual(client.get("/health?access=token-seguro").status_code, 200)

    def test_external_post_rejected_even_with_token_but_local_allowed(self):
        payload = {"type":"gift","gift_id":"1","gift_name":"Rose","image_url":"https://example.invalid/rose.png"}
        headers = {"CF-Connecting-IP": "203.0.113.8"}
        self.assertEqual(app.test_client().post("/api/events?access=token-seguro", json=payload, headers=headers).status_code, 403)
        with patch("overlay.server.get_gift_image", return_value=Path("cache/gifts/rose.png")), patch(
            "overlay.server.get_overlay_image_url", return_value="/gift-assets/rose.png"
        ):
            self.assertEqual(app.test_client().post("/api/events", json=payload).status_code, 200)

    def test_two_clients_receive_once_with_secure_polling(self):
        with queue_lock: enqueue_gift({"type":"gift","gift_id":"1","gift_name":"Rose"})
        client=app.test_client(); headers={"CF-Connecting-IP":"203.0.113.8"}
        url="/api/events/next?access=token-seguro&client_id="
        self.assertIsNotNone(client.get(url+"chrome",headers=headers).get_json()["event"])
        self.assertIsNotNone(client.get(url+"live-studio",headers=headers).get_json()["event"])
        self.assertIsNone(client.get(url+"chrome",headers=headers).get_json()["event"])

    def test_tunnel_command_has_no_shell_and_stops_cleanly(self):
        process=FakeProcess(["https://demo-123.trycloudflare.com\n"]); calls=[]; states=[]
        def factory(command, **kwargs): calls.append((command,kwargs)); return process
        tunnel=CloudflareTunnel("secret",finder=lambda:Path("cloudflared.exe"),opener=lambda *_a,**_k:HealthResponse(),process_factory=factory)
        tunnel.state_changed.connect(lambda *values:states.append(values)); tunnel.start()
        if tunnel.launcher: tunnel.launcher.join(timeout=1)
        if tunnel.reader: tunnel.reader.join(timeout=1)
        self.assertEqual(calls[0][0][1:], ["tunnel","--url","http://127.0.0.1:5050","--no-autoupdate"])
        self.assertIs(calls[0][1]["shell"],False); self.assertIn("/overlay?access=secret", tunnel.public_url)
        tunnel.stop(); self.assertTrue(process.terminated or process.poll() is not None)


if __name__ == "__main__": unittest.main()
