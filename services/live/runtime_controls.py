from __future__ import annotations

from collections.abc import Mapping
from threading import Lock


def stop_button_enabled(connection_state: str) -> bool:
    return connection_state in {"connecting", "connected"}


class RuntimeControls:
    """Configuración mutable protegida para la UI y los trabajadores."""

    def __init__(
        self,
        dashboard: Mapping[str, object],
        tts: Mapping[str, object],
    ) -> None:
        self._lock = Lock()
        self._dashboard = dict(dashboard)
        self._tts = dict(tts)

    def update_dashboard(self, key: str, value: object) -> None:
        with self._lock:
            self._dashboard[key] = value

    def update_tts(self, values: Mapping[str, object]) -> None:
        with self._lock:
            self._tts = dict(values)

    def snapshot(self) -> tuple[dict[str, object], dict[str, object]]:
        with self._lock:
            return dict(self._dashboard), dict(self._tts)

    def enabled(self, key: str, default: bool = True) -> bool:
        with self._lock:
            return bool(self._dashboard.get(key, default))
