from __future__ import annotations

import threading
import uuid

from services.overlay.events import post_overlay_event


GIFT_DEFAULTS: dict[str, object] = {
    "animations_enabled": True,
    "assignments": {},
    "overlay": {"show_animations": True, "show_current": True, "show_next": True, "show_requester": True},
}


class GiftAnimationManager:
    def __init__(self, settings: dict[str, object] | None = None, sender=post_overlay_event) -> None:
        self.settings = {**GIFT_DEFAULTS, **(settings or {})}
        self.sender = sender
        self.lock = threading.RLock()

    def enabled(self) -> bool:
        with self.lock:
            return bool(self.settings.get("animations_enabled", True))

    def update_settings(self, values: dict[str, object]) -> None:
        with self.lock:
            self.settings.update(values)

    def handle_gift(self, *, gift_id: str, gift_name: str, quantity: int, username: str,
                    image_url: str = "", event_id: str = "", test: bool = False) -> bool:
        if not self.enabled():
            return False
        assignments = self.settings.get("assignments", {})
        assignment = assignments.get(gift_id, {}) if isinstance(assignments, dict) else {}
        if isinstance(assignment, dict) and assignment.get("active") is False:
            return False
        animation = str(assignment.get("animation", "Resplandor circular")) if isinstance(assignment, dict) else "Resplandor circular"
        duration_text = str(assignment.get("duration", "4.2 s")) if isinstance(assignment, dict) else "4.2 s"
        try:
            duration_ms = int(float(duration_text.lower().replace("s", "").strip()) * 1000)
        except ValueError:
            duration_ms = 4200
        return self.sender({
            "type": "gift", "gift_id": gift_id, "gift_name": gift_name,
            "quantity": quantity, "username": username, "image_url": image_url,
            "animation": animation, "event_id": event_id or uuid.uuid4().hex, "test": test,
            "duration_ms": max(500, min(duration_ms, 30000)),
        })
