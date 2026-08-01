from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import urlopen

from PySide6.QtCore import QObject, Signal


QUICK_TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
INSTALL_COMMAND = "winget install --id Cloudflare.cloudflared"


def find_cloudflared(path_value: str | None = None) -> Path | None:
    found = shutil.which("cloudflared", path=path_value)
    candidates = [found, r"C:\Program Files\cloudflared\cloudflared.exe",
                  r"C:\Program Files (x86)\cloudflared\cloudflared.exe"]
    return next((Path(value) for value in candidates if value and Path(value).is_file()), None)


def extract_quick_tunnel_url(line: object) -> str:
    match = QUICK_TUNNEL_RE.search(str(line or ""))
    return match.group(0).lower() if match else ""


class CloudflareTunnel(QObject):
    state_changed = Signal(str, str, str)

    def __init__(self, access_token: str, *, finder=find_cloudflared, opener=urlopen,
                 process_factory=subprocess.Popen) -> None:
        super().__init__(); self.access_token = access_token; self.finder = finder
        self.opener = opener; self.process_factory = process_factory
        self.process: subprocess.Popen | None = None; self.reader: threading.Thread | None = None
        self.launcher: threading.Thread | None = None; self._lock = threading.Lock()
        self.public_url = ""
        self._stopping = False

    def start(self) -> None:
        with self._lock:
            if (self.process is not None and self.process.poll() is None) or (self.launcher is not None and self.launcher.is_alive()): return
            self.launcher = threading.Thread(target=self._start_process, name="PandaIA-Cloudflare-Start", daemon=True)
            self.launcher.start()

    def _start_process(self) -> None:
        executable = self.finder()
        if executable is None:
            self.state_changed.emit("Componente no instalado", "", "Se necesita Cloudflare Tunnel")
            return
        self.state_changed.emit("Iniciando servidor local", "", "Comprobando el overlay local.")
        try:
            health_url = f"http://127.0.0.1:5050/health?access={quote(self.access_token, safe='')}"
            with self.opener(health_url, timeout=2) as response:
                if not 200 <= response.status < 300: raise OSError(f"HTTP {response.status}")
        except (URLError, TimeoutError, OSError) as error:
            self.state_changed.emit("Error", "", f"El servidor local no está disponible: {error}"); return
        if self._stopping: return
        self.state_changed.emit("Creando enlace seguro", "", "Cloudflare está preparando la URL temporal.")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            self._stopping = False
            self.process = self.process_factory(
                [str(executable), "tunnel", "--url", "http://127.0.0.1:5050", "--no-autoupdate"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=flags, shell=False,
            )
        except OSError as error:
            self.state_changed.emit("Error", "", f"No se pudo iniciar cloudflared: {error}"); return
        self.reader = threading.Thread(target=self._read_output, name="PandaIA-Cloudflare", daemon=True); self.reader.start()

    def _read_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None: return
        last_detail = ""
        for line in process.stdout:
            clean_line = str(line).strip()
            if clean_line: last_detail = clean_line[-500:]
            public_base = extract_quick_tunnel_url(line)
            if public_base:
                self.public_url = f"{public_base}/overlay?access={self.access_token}"
                self.state_changed.emit("Enlace HTTPS activo", self.public_url, "")
        return_code = process.wait()
        if not self._stopping:
            state = "Error" if return_code else "Túnel desconectado"
            detail = f"cloudflared finalizó con código {return_code}."
            if last_detail: detail += f" {last_detail}"
            self.state_changed.emit(state, "", detail)

    def stop(self) -> None:
        process = self.process; self._stopping = True
        if process is not None and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=4)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
        self.process = None; self.public_url = ""
        if self.launcher is not None and self.launcher.is_alive(): self.launcher.join(timeout=3)
        self.launcher = None
        if self.reader is not None and self.reader.is_alive(): self.reader.join(timeout=2)
        self.reader = None; self.state_changed.emit("Túnel desconectado", "", "Enlace HTTPS detenido.")
