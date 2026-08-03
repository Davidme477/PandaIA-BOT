from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from overlay.server import app, client_cursors, client_seen, enqueue_event, event_queue, queue_lock
from services.overlay.events import sanitize_event
from services.tiktok.member_levels import (
    MemberLevelHistory, MemberLevelManager, MemberObservation, extract_member_observation,
)
from services.tiktok.tiktok_service import TikTokService
from config.settings_store import read_settings, write_settings_atomic


def observation(level: int, *, name: str = "Ana", avatar: str = "https://img/1.png") -> MemberObservation:
    return MemberObservation("42", "ana", name, avatar, level, "Club Panda", 7)


class MemberLevelTests(unittest.TestCase):
    def setUp(self):
        with queue_lock:
            event_queue.clear(); client_cursors.clear(); client_seen.clear()

    def test_extracts_member_and_keeps_gifter_separate(self):
        user = SimpleNamespace(id="42", unique_id="ana", nickname="Ana", avatar_thumb=SimpleNamespace(url_list=["https://img"]),
                               badges=[{"type": "gifter", "level": 48}, {"type": "fans_club_level", "level": 31, "club_name": "Panda"}])
        item = extract_member_observation(user)
        self.assertEqual((item.member_level, item.gifter_level, item.club_name), (31, 48, "Panda"))

    def test_donor_only_and_empty_level_are_not_members(self):
        user = {"id": "1", "unique_id": "x", "badges": [{"type": "gifter", "level": 50}]}
        self.assertIsNone(extract_member_observation(user))

    def test_first_equal_lower_jump_duplicate_and_profile_update(self):
        with tempfile.TemporaryDirectory() as folder:
            history = MemberLevelHistory(Path(folder) / "members.json", clock=lambda: 100)
            first, raised = history.observe(observation(30), event_id="a")
            self.assertFalse(raised); self.assertEqual(first["current_level"], 30)
            self.assertFalse(history.observe(observation(30), event_id="b")[1])
            self.assertFalse(history.observe(observation(29), event_id="c")[1])
            updated, raised = history.observe(observation(32, name="Ana Nueva", avatar="https://img/2.png"), event_id="d")
            self.assertTrue(raised); self.assertEqual((updated["previous_level"], updated["current_level"]), (30, 32))
            self.assertEqual((updated["nickname"], updated["avatar"]), ("Ana Nueva", "https://img/2.png"))
            self.assertFalse(history.observe(observation(32), event_id="d")[1])
            self.assertEqual(MemberLevelHistory(history.path).top()[0]["current_level"], 32)

    def test_missing_avatar_is_supported_and_clear_is_persistent(self):
        with tempfile.TemporaryDirectory() as folder:
            history = MemberLevelHistory(Path(folder) / "members.json")
            history.observe(observation(4, avatar="")); self.assertEqual(history.top()[0]["avatar"], "")
            history.clear(); self.assertEqual(history.count(), 0)

    def test_top_three_order_ties_and_small_rankings(self):
        with tempfile.TemporaryDirectory() as folder:
            tick = iter((10, 20, 30, 40))
            history = MemberLevelHistory(Path(folder) / "members.json", clock=lambda: next(tick))
            for user_id, name, level in (("a", "A", 20), ("b", "B", 30), ("c", "C", 30), ("d", "D", 10)):
                history.observe(MemberObservation(user_id, name.lower(), name, "", level))
            self.assertEqual([x["user_id"] for x in history.top()], ["b", "c", "a"])
            self.assertEqual(len(history.top(1)), 1); self.assertEqual(len(history.top(2)), 2)

    def test_manager_first_seen_no_animation_then_one_level_event(self):
        sent = []
        with tempfile.TemporaryDirectory() as folder:
            manager = MemberLevelManager({"member_ranking_enabled": False}, history=MemberLevelHistory(Path(folder) / "m.json"), sender=lambda event: sent.append(event) or True)
            user = {"id": "1", "unique_id": "ana", "nickname": "Ana", "member_level": 4}
            self.assertFalse(manager.observe_user(user, event_id="one")); user["member_level"] = 6
            self.assertTrue(manager.observe_user(user, event_id="two")); self.assertEqual(len(sent), 1)
            self.assertEqual((sent[0]["previous_level"], sent[0]["new_level"]), (4, 6))

    def test_simulated_events_do_not_touch_real_history(self):
        with tempfile.TemporaryDirectory() as folder:
            history = MemberLevelHistory(Path(folder) / "m.json"); manager = MemberLevelManager(history=history)
            manager.level_event({"user_id": "test", "current_level": 9, "previous_level": 8}, test=True)
            manager.ranking_event([{"user_id": "test", "current_level": 9}], test=True)
            self.assertEqual(history.count(), 0)

    def test_sanitization_and_music_exclusion(self):
        level = sanitize_event({"type": "member_level_up", "user_id": "1", "new_level": 5, "nickname": "<Ana>"})
        self.assertEqual(level["nickname"], "Ana")
        with self.assertRaises(ValueError): sanitize_event({"type": "music_request"})

    def test_member_configuration_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            values = {"gifts": {"member_ranking_mode": "Oculto", "member_level_sound": False}}
            write_settings_atomic(path, values)
            self.assertEqual(read_settings(path), values)

    def test_priority_broadcast_and_no_duplicates(self):
        with queue_lock:
            enqueue_event({"type": "gift", "gift_id": "1", "gift_name": "Rose"})
            enqueue_event({"type": "member_level_up", "user_id": "u", "new_level": 3})
        client = app.test_client()
        first_a = client.get("/api/events/next?client_id=a").get_json()["event"]
        first_b = client.get("/api/events/next?client_id=b").get_json()["event"]
        gift_a = client.get("/api/events/next?client_id=a").get_json()["event"]
        self.assertEqual(first_a["type"], "member_level_up"); self.assertEqual(first_a, first_b)
        self.assertEqual(gift_a["type"], "gift"); self.assertIsNone(client.get("/api/events/next?client_id=a").get_json()["event"])

    def test_overlay_markup_is_transparent_and_contains_both_stages(self):
        html = app.test_client().get("/overlay").get_data(as_text=True)
        css = Path("overlay/static/css/overlay.css").read_text(encoding="utf-8")
        self.assertIn("member-level-stage", html); self.assertIn("member-ranking-stage", html)
        self.assertIn("background: transparent", css)

    def test_tiktok_forwards_real_user_and_overlay_errors_are_isolated(self):
        calls = []
        service = TikTokService("cuenta", member_level_callback=lambda user, **values: calls.append((user, values)))
        user = SimpleNamespace(id="1", unique_id="ana", member_level=8)
        service.inspect_member_level(SimpleNamespace(user=user, id="event-8"))
        self.assertIs(calls[0][0], user); self.assertEqual(calls[0][1]["event_id"], "event-8")
        service.member_level_callback = lambda *_args, **_values: (_ for _ in ()).throw(RuntimeError("overlay"))
        service.inspect_member_level(SimpleNamespace(user=user, id="event-9"))


if __name__ == "__main__": unittest.main()
