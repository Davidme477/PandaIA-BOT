from __future__ import annotations

import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OVERLAY_URL = "http://127.0.0.1:5050/overlay"
OVERLAY_EVENTS_URL = "http://127.0.0.1:5050/api/events"
ALLOWED_TYPES = {"gift", "member_level_up", "member_level_leaderboard"}


def sanitize_text(value: object, limit: int = 160) -> str:
    text = str(value or "").replace("<", "").replace(">", "")
    return "".join(char for char in text if char.isprintable())[:limit]


def sanitize_event(payload: dict[str, object]) -> dict[str, object]:
    event_type = sanitize_text(payload.get("type"), 32).lower()
    if event_type not in ALLOWED_TYPES:
        raise ValueError("Tipo de evento de overlay no admitido.")
    clean: dict[str, object] = {"type": event_type}
    for key in ("gift_id", "gift_name", "username", "animation", "user_id", "unique_id", "nickname",
                "club_name", "message", "position", "mode"):
        if key in payload:
            clean[key] = sanitize_text(payload[key])
    for key in ("quantity", "duration_ms", "previous_level", "new_level", "timestamp", "volume", "scale"):
        if key in payload:
            clean[key] = max(0, int(payload[key]))
    for key in ("test", "sound"):
        if key in payload:
            clean[key] = bool(payload[key])
    if "image_url" in payload:
        image = sanitize_text(payload["image_url"], 500)
        if image.startswith(("/gift-assets/", "https://", "http://")):
            clean["image_url"] = image
    if "avatar_url" in payload:
        avatar = sanitize_text(payload["avatar_url"], 500)
        if avatar.startswith(("/gift-assets/", "https://", "http://", "data:image/")): clean["avatar_url"] = avatar
    if event_type == "member_level_leaderboard":
        members = payload.get("members", [])
        clean["members"] = [{key: sanitize_text(row.get(key), 160) if key in {"user_id", "unique_id", "nickname", "avatar"}
                             else max(0, int(row.get(key, 0))) for key in ("user_id", "unique_id", "nickname", "avatar", "current_level", "first_seen")}
                            for row in members[:3] if isinstance(row, dict)] if isinstance(members, list) else []
    clean["event_id"] = sanitize_text(payload.get("event_id") or uuid.uuid4().hex, 64)
    return clean


def post_overlay_event(payload: dict[str, object], opener=urlopen) -> bool:
    clean = sanitize_event(payload)
    request = Request(OVERLAY_EVENTS_URL, data=json.dumps(clean).encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with opener(request, timeout=5) as response:
            return 200 <= response.status < 300
    except (HTTPError, URLError, TimeoutError, OSError):
        return False
