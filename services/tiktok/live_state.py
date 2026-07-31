from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class LiveStats:
    viewers: int = 0
    likes: int = 0
    gifts: int = 0
    comments: int = 0
    elapsed_seconds: int = 0


@dataclass(frozen=True)
class LiveActivity:
    icon: str
    title: str
    user: str
    amount: str = ""


def format_count(value: int) -> str:
    return f"{max(0, int(value)):,}"


def format_elapsed(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class LiveState:
    """Estado de una sesión real de TikTok protegido para callbacks concurrentes."""

    def __init__(self, *, clock=monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._stats = LiveStats()
        self._connected_at: float | None = None
        self._activities: list[LiveActivity] = []

    def reset(self) -> LiveStats:
        with self._lock:
            self._stats = LiveStats()
            self._connected_at = None
            self._activities.clear()
            return self._stats

    def connect(self) -> LiveStats:
        with self._lock:
            self._stats = LiveStats()
            self._activities.clear()
            self._connected_at = self._clock()
            return self._stats

    def disconnect(self) -> LiveStats:
        with self._lock:
            self._refresh_elapsed()
            self._connected_at = None
            return self._stats

    def snapshot(self) -> LiveStats:
        with self._lock:
            self._refresh_elapsed()
            return self._stats

    def update_viewers(self, total: int) -> LiveStats:
        return self._replace(viewers=max(0, int(total)))

    def update_likes(self, *, total: int = 0, count: int = 0) -> LiveStats:
        with self._lock:
            likes = max(self._stats.likes, int(total)) if total > 0 else (
                self._stats.likes + max(0, int(count))
            )
            self._stats = self._copy(likes=likes)
            return self._stats

    def add_comment(self, comment: str, user: str) -> LiveStats:
        if not comment.strip():
            return self.snapshot()
        with self._lock:
            self._stats = self._copy(comments=self._stats.comments + 1)
            self._add_activity(LiveActivity("💬", comment.strip(), user))
            return self._stats

    def add_gift(self, *, name: str, user: str, quantity: int, streaking: bool) -> LiveStats:
        if streaking:
            return self.snapshot()
        quantity = max(1, int(quantity))
        with self._lock:
            self._stats = self._copy(gifts=self._stats.gifts + quantity)
            self._add_activity(LiveActivity("🎁", f"Regalo {name}", user, f"x{quantity}"))
            return self._stats

    def add_follow(self, user: str) -> None:
        with self._lock:
            self._add_activity(LiveActivity("👤", "Nuevo seguidor", user))

    def activities(self) -> list[LiveActivity]:
        with self._lock:
            return list(self._activities)

    def _replace(self, **changes: int) -> LiveStats:
        with self._lock:
            self._stats = self._copy(**changes)
            return self._stats

    def _copy(self, **changes: int) -> LiveStats:
        values = {
            "viewers": self._stats.viewers,
            "likes": self._stats.likes,
            "gifts": self._stats.gifts,
            "comments": self._stats.comments,
            "elapsed_seconds": self._stats.elapsed_seconds,
        }
        values.update(changes)
        return LiveStats(**values)

    def _refresh_elapsed(self) -> None:
        if self._connected_at is not None:
            self._stats = self._copy(
                elapsed_seconds=max(0, int(self._clock() - self._connected_at))
            )

    def _add_activity(self, activity: LiveActivity) -> None:
        self._activities.insert(0, activity)
        del self._activities[4:]
