from __future__ import annotations

from collections import OrderedDict, deque
from threading import Lock


class SessionMemory:
    def __init__(self, *, max_users: int = 100, max_exchanges: int = 5) -> None:
        self.max_users = max_users
        self.max_exchanges = max_exchanges
        self._lock = Lock()
        self._users: OrderedDict[str, deque[tuple[str, str]]] = OrderedDict()

    def add(self, username: str, comment: str, answer: str) -> None:
        key = username.strip().casefold()
        with self._lock:
            history = self._users.pop(key, deque(maxlen=self.max_exchanges))
            history.append((comment, answer))
            self._users[key] = history
            while len(self._users) > self.max_users:
                self._users.popitem(last=False)

    def context(self, username: str) -> str:
        key = username.strip().casefold()
        with self._lock:
            history = list(self._users.get(key, ()))
        return "\n".join(
            f"Usuario: {comment}\nPandaIA: {answer}"
            for comment, answer in history
        )

    def clear(self) -> None:
        with self._lock:
            self._users.clear()

    def user_count(self) -> int:
        with self._lock:
            return len(self._users)
