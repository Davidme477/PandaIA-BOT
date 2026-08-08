from __future__ import annotations

import json
import threading
import uuid
from queue import Empty, Full, Queue
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OVERLAY_URL = "http://127.0.0.1:5050/overlay"
OVERLAY_EVENTS_URL = "http://127.0.0.1:5050/api/events"
OVERLAY_PUBLISH_QUEUE_LIMIT = 256

ALLOWED_TYPES = {
    "gift",
    "member_level_up",
    "member_level_leaderboard",
    "like_leaderboard",
}


def sanitize_text(value: object, limit: int = 160) -> str:
    text = (
        str(value or "")
        .replace("<", "")
        .replace(">", "")
    )

    return "".join(
        char
        for char in text
        if char.isprintable()
    )[:limit]


def _sanitize_ranking_rows(
    payload: dict[str, object],
    *,
    likes: bool,
) -> list[dict[str, object]]:
    rows = payload.get("members", [])

    if not isinstance(rows, list):
        return []

    result: list[dict[str, object]] = []

    for row in rows[:3]:
        if not isinstance(row, dict):
            continue

        item: dict[str, object] = {
            "user_id": sanitize_text(
                row.get("user_id"),
                160,
            ),
            "unique_id": sanitize_text(
                row.get("unique_id"),
                160,
            ),
            "nickname": sanitize_text(
                row.get("nickname"),
                160,
            ),
            "avatar": sanitize_text(
                row.get("avatar"),
                500,
            ),
        }

        if likes:
            item["likes"] = max(
                0,
                int(row.get("likes", 0)),
            )
        else:
            item["current_level"] = max(
                0,
                int(row.get("current_level", 0)),
            )
            item["first_seen"] = max(
                0,
                int(row.get("first_seen", 0)),
            )

        result.append(item)

    return result


def sanitize_event(
    payload: dict[str, object],
) -> dict[str, object]:
    event_type = sanitize_text(
        payload.get("type"),
        32,
    ).lower()

    if event_type not in ALLOWED_TYPES:
        raise ValueError(
            "Tipo de evento de overlay no admitido."
        )

    clean: dict[str, object] = {
        "type": event_type
    }

    text_keys = (
        "gift_id",
        "gift_name",
        "username",
        "animation",
        "user_id",
        "unique_id",
        "nickname",
        "club_name",
        "message",
        "position",
        "mode",
    )

    for key in text_keys:
        if key in payload:
            clean[key] = sanitize_text(
                payload[key]
            )

    integer_keys = (
        "quantity",
        "duration_ms",
        "previous_level",
        "new_level",
        "timestamp",
        "volume",
        "scale",
    )

    for key in integer_keys:
        if key in payload:
            clean[key] = max(
                0,
                int(payload[key]),
            )

    for key in ("test", "sound"):
        if key in payload:
            clean[key] = bool(payload[key])

    if "image_url" in payload:
        image = sanitize_text(
            payload["image_url"],
            500,
        )

        if image.startswith(
            (
                "/gift-assets/",
                "https://",
                "http://",
            )
        ):
            clean["image_url"] = image

    if "avatar_url" in payload:
        avatar = sanitize_text(
            payload["avatar_url"],
            500,
        )

        if avatar.startswith(
            (
                "/gift-assets/",
                "https://",
                "http://",
                "data:image/",
            )
        ):
            clean["avatar_url"] = avatar

    if event_type == "member_level_leaderboard":
        clean["members"] = _sanitize_ranking_rows(
            payload,
            likes=False,
        )

    if event_type == "like_leaderboard":
        clean["members"] = _sanitize_ranking_rows(
            payload,
            likes=True,
        )

    clean["event_id"] = sanitize_text(
        payload.get("event_id") or uuid.uuid4().hex,
        64,
    )

    return clean


_overlay_publish_queue: Queue[dict[str, object]] = Queue(maxsize=OVERLAY_PUBLISH_QUEUE_LIMIT)


def _overlay_publisher_worker() -> None:
    while True:
        try:
            payload = _overlay_publish_queue.get(block=True)
        except Empty:
            continue
        try:
            request = Request(
                OVERLAY_EVENTS_URL,
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=5) as response:
                    response_ok = 200 <= response.status < 300
            except (
                HTTPError,
                URLError,
                TimeoutError,
                OSError,
            ):
                response_ok = False
            if not response_ok:
                try:
                    pass
                except Exception:
                    pass
        finally:
            _overlay_publish_queue.task_done()


_overlay_publisher_thread = threading.Thread(
    target=_overlay_publisher_worker,
    name="pandaia-overlay-publisher",
    daemon=True,
)
_overlay_publisher_thread.start()


def post_overlay_event(
    payload: dict[str, object],
    opener=urlopen,
) -> bool:
    try:
        clean = sanitize_event(payload)
    except (ValueError, TypeError):
        return False

    try:
        _overlay_publish_queue.put_nowait(clean)
    except Full:
        return False

    return True