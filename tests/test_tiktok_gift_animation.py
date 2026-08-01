from __future__ import annotations

import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PROJECT_DIR = Path(__file__).resolve().parents[1]
SITE_PACKAGES = PROJECT_DIR / ".venv" / "Lib" / "site-packages"
for path in (PROJECT_DIR, SITE_PACKAGES):
    if str(path) not in sys.path: sys.path.insert(0, str(path))

from services.overlay.gift_animations import GiftAnimationManager
from services.tiktok.tiktok_service import TikTokService


def gift_event() -> SimpleNamespace:
    image = SimpleNamespace(url_list=["https://example.invalid/rose.png"], url="")
    gift = SimpleNamespace(id="5655", name="Rose", type=0, image=image)
    return SimpleNamespace(gift=gift, streaking=False, repeat_count=3,
                           user=SimpleNamespace(unique_id="ana"), id="event-42")


class TikTokGiftAnimationTests(unittest.TestCase):
    def _handler(self, service: TikTokService):
        return next(iter(service.client._events["GiftEvent"]))

    def test_real_tiktok_callback_uses_exact_named_data(self):
        captured = []
        manager = GiftAnimationManager(sender=lambda payload: captured.append(payload) or True)
        service = TikTokService("cuenta", gift_animation_callback=manager.handle_gift)
        service._live_connected = True
        with patch("services.tiktok.tiktok_service.get_gift_image", return_value=None):
            asyncio.run(self._handler(service)(gift_event()))
        self.assertEqual(list(captured[0])[:7],
                         ["type", "gift_id", "gift_name", "quantity", "username", "image_url", "animation"])
        self.assertEqual(captured[0]["gift_id"], "5655")
        self.assertEqual(captured[0]["gift_name"], "Rose")
        self.assertEqual(captured[0]["quantity"], 3)
        self.assertEqual(captured[0]["username"], "ana")
        self.assertEqual(captured[0]["image_url"], "https://example.invalid/rose.png")
        self.assertEqual(captured[0]["event_id"], "event-42")

    def test_overlay_exception_does_not_stop_gift_processing_or_cache(self):
        activities, stats, gifts, cache_calls = [], [], [], []
        def broken(**_values): raise RuntimeError("overlay caído")
        service = TikTokService("cuenta", activity_callback=lambda *values: activities.append(values),
                                stats_callback=lambda value: stats.append(value), gift_callback=lambda *values: gifts.append(values),
                                gift_animation_callback=broken)
        service._live_connected = True
        def cache(**values): cache_calls.append(values); return None
        with patch("services.tiktok.tiktok_service.get_gift_image", side_effect=cache):
            asyncio.run(self._handler(service)(gift_event()))
        self.assertTrue(activities); self.assertTrue(stats); self.assertEqual(gifts, [("ana", "Rose", 3)])
        self.assertEqual(cache_calls[0]["gift_id"], "5655")


if __name__ == "__main__": unittest.main()
