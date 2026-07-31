from __future__ import annotations

from threading import Thread

from overlay.server import run_server


class OverlayService:
    def __init__(self) -> None:
        self._thread: Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        if self.is_running:
            return False

        self._thread = Thread(
            target=run_server,
            name="PandaIAOverlayServer",
            daemon=True,
        )
        self._thread.start()

        return True