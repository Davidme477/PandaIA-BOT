from __future__ import annotations

import time
import uuid
from threading import RLock

from services.overlay.events import post_overlay_event


def _value(
    obj: object,
    name: str,
    default: object = "",
) -> object:
    if isinstance(obj, dict):
        return obj.get(name, default)

    return getattr(obj, name, default)


def _avatar(user: object) -> str:
    for name in (
        "avatar_thumb",
        "avatar_medium",
        "avatar_larger",
        "avatar",
    ):
        image = _value(user, name)
        urls = _value(image, "url_list", [])

        if urls:
            return str(urls[0])

        direct = _value(image, "url")

        if direct:
            return str(direct)

    return ""


class LikeRankingManager:
    """Top 3 de likes acumulados durante el live actual."""

    def __init__(
        self,
        *,
        sender=post_overlay_event,
        clock=time.monotonic,
        publish_interval: float = 1.5,
    ) -> None:
        self.sender = sender
        self.clock = clock
        self.publish_interval = max(
            0.5,
            float(publish_interval),
        )
        self.lock = RLock()
        self.rows: dict[str, dict[str, object]] = {}
        self.last_publish = 0.0
        self.last_fingerprint = ""

    def reset(self) -> None:
        with self.lock:
            self.rows.clear()
            self.last_publish = 0.0
            self.last_fingerprint = ""

    def observe(
        self,
        user: object,
        count: int,
    ) -> bool:
        likes = max(0, int(count or 0))

        if likes <= 0:
            return False

        unique_id = str(
            _value(user, "unique_id") or
            _value(user, "uniqueId") or
            ""
        ).strip()

        user_id = str(
            _value(user, "id") or
            _value(user, "user_id") or
            unique_id
        ).strip()

        if not user_id:
            return False

        nickname = str(
            _value(user, "nickname") or
            unique_id or
            "Seguidor"
        ).strip()

        with self.lock:
            previous = self.rows.get(
                user_id,
                {},
            )

            total = (
                max(
                    0,
                    int(previous.get("likes", 0)),
                ) +
                likes
            )

            self.rows[user_id] = {
                "user_id": user_id,
                "unique_id": unique_id,
                "nickname": nickname,
                "avatar": _avatar(user),
                "likes": total,
            }

            return self._maybe_publish_locked()

    def top(
        self,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        with self.lock:
            return sorted(
                self.rows.values(),
                key=lambda row: (
                    -int(row.get("likes", 0)),
                    str(row.get("user_id", "")),
                ),
            )[:limit]

    def event(self) -> dict[str, object]:
        return {
            "type": "like_leaderboard",
            "event_id": uuid.uuid4().hex,
            "members": self.top(),
            "duration_ms": 0,
            "position": "Izquierda",
            "scale": 100,
            "mode": "Siempre visible",
        }

    def publish(
        self,
        *,
        force: bool = False,
    ) -> bool:
        with self.lock:
            return self._publish_locked(force=force)

    def _fingerprint(
        self,
        rows: list[dict[str, object]],
    ) -> str:
        return "|".join(
            (
                f"{row.get('user_id', '')}:"
                f"{int(row.get('likes', 0))}"
            )
            for row in rows
        )

    def _maybe_publish_locked(self) -> bool:
        now = self.clock()

        if (
            now - self.last_publish <
            self.publish_interval
        ):
            return False

        return self._publish_locked()

    def _publish_locked(
        self,
        *,
        force: bool = False,
    ) -> bool:
        rows = sorted(
            self.rows.values(),
            key=lambda row: (
                -int(row.get("likes", 0)),
                str(row.get("user_id", "")),
            ),
        )[:3]

        if not rows:
            return False

        fingerprint = self._fingerprint(rows)

        if (
            not force and
            fingerprint == self.last_fingerprint
        ):
            return False

        payload = {
            "type": "like_leaderboard",
            "event_id": uuid.uuid4().hex,
            "members": rows,
            "duration_ms": 0,
            "position": "Izquierda",
            "scale": 100,
            "mode": "Siempre visible",
        }

        sent = bool(self.sender(payload))

        if sent:
            self.last_publish = self.clock()
            self.last_fingerprint = fingerprint

        return sent