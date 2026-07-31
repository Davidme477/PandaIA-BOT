from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class MemorySnapshot:
    enabled: bool = True
    connected: bool = False
    user_count: int = 0
    exchange_count: int = 0
    last_username: str = ""
    max_users: int = 100
    max_exchanges_per_user: int = 5


MemoryCallback = Callable[[MemorySnapshot], None]


def memory_panel_values(snapshot: MemorySnapshot) -> dict[str, str]:
    if not snapshot.connected:
        status = "Desconectada"
    elif not snapshot.enabled:
        status = "Desactivada"
    else:
        status = "Activa"
    return {
        "status": status,
        "users": f"{snapshot.user_count:,} / {snapshot.max_users:,}",
        "exchanges": f"{snapshot.exchange_count:,}",
        "last_user": snapshot.last_username or "Sin interacciones",
    }


class SessionMemory:
    def __init__(
        self,
        *,
        max_users: int = 100,
        max_exchanges: int = 5,
        on_change: MemoryCallback | None = None,
    ) -> None:
        self.max_users = max_users
        self.max_exchanges = max_exchanges
        self._lock = Lock()
        self._users: OrderedDict[str, deque[tuple[str, str]]] = OrderedDict()
        self._last_username = ""
        self._enabled = True
        self._connected = False
        self._on_change = on_change

    def set_callback(self, callback: MemoryCallback | None) -> None:
        with self._lock:
            self._on_change = callback

    def set_enabled(self, enabled: bool) -> MemorySnapshot:
        with self._lock:
            self._enabled = bool(enabled)
            if not self._enabled:
                self._clear_locked()
            snapshot, callback = self._snapshot_locked(), self._on_change
        self._emit(callback, snapshot)
        return snapshot

    def set_connected(self, connected: bool) -> MemorySnapshot:
        with self._lock:
            connected = bool(connected)
            changed = connected != self._connected or bool(self._users)
            self._connected = connected
            self._clear_locked()
            snapshot, callback = self._snapshot_locked(), self._on_change
        if changed:
            self._emit(callback, snapshot)
        return snapshot

    def add(self, username: str, comment: str, answer: str) -> MemorySnapshot:
        display_name = username.strip()
        key = display_name.casefold()
        with self._lock:
            if not self._enabled or not self._connected:
                return self._snapshot_locked()
            history = self._users.pop(key, deque(maxlen=self.max_exchanges))
            history.append((comment, answer))
            self._users[key] = history
            self._last_username = display_name
            while len(self._users) > self.max_users:
                self._users.popitem(last=False)
            snapshot, callback = self._snapshot_locked(), self._on_change
        self._emit(callback, snapshot)
        return snapshot

    def context(self, username: str) -> str:
        key = username.strip().casefold()
        with self._lock:
            history = list(self._users.get(key, ()))
        return "\n".join(
            f"Usuario: {comment}\nPandaIA: {answer}"
            for comment, answer in history
        )

    def clear(self) -> MemorySnapshot:
        with self._lock:
            self._clear_locked()
            snapshot, callback = self._snapshot_locked(), self._on_change
        self._emit(callback, snapshot)
        return snapshot

    def snapshot(self) -> MemorySnapshot:
        with self._lock:
            return self._snapshot_locked()

    def user_count(self) -> int:
        return self.snapshot().user_count

    def _snapshot_locked(self) -> MemorySnapshot:
        return MemorySnapshot(
            enabled=self._enabled,
            connected=self._connected,
            user_count=len(self._users),
            exchange_count=sum(len(history) for history in self._users.values()),
            last_username=self._last_username,
            max_users=self.max_users,
            max_exchanges_per_user=self.max_exchanges,
        )

    def _clear_locked(self) -> None:
        self._users.clear()
        self._last_username = ""

    @staticmethod
    def _emit(callback: MemoryCallback | None, snapshot: MemorySnapshot) -> None:
        if callback is not None:
            callback(snapshot)
