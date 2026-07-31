from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from services.tiktok.live_state import LiveState, LiveStats, format_count, format_elapsed


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class LiveStateTests(unittest.TestCase):
    def test_initial_state_is_zero_and_activity_is_empty(self) -> None:
        state = LiveState()
        self.assertEqual(state.snapshot(), LiveStats())
        self.assertEqual(state.activities(), [])

    def test_updates_current_viewers(self) -> None:
        state = LiveState()
        self.assertEqual(state.update_viewers(37).viewers, 37)
        self.assertEqual(state.update_viewers(12).viewers, 12)

    def test_likes_prefer_total_and_do_not_duplicate_it(self) -> None:
        state = LiveState()
        state.update_likes(total=100, count=5)
        state.update_likes(total=100, count=5)
        self.assertEqual(state.snapshot().likes, 100)

    def test_likes_accumulate_increments_without_total(self) -> None:
        state = LiveState()
        state.update_likes(count=3)
        state.update_likes(count=4)
        self.assertEqual(state.snapshot().likes, 7)

    def test_only_valid_comments_are_counted(self) -> None:
        state = LiveState()
        state.add_comment("   ", "@nadie")
        state.add_comment("Hola", "@ana")
        self.assertEqual(state.snapshot().comments, 1)

    def test_normal_gift_adds_real_quantity(self) -> None:
        state = LiveState()
        state.add_gift(name="Rosa", user="@ana", quantity=3, streaking=False)
        self.assertEqual(state.snapshot().gifts, 3)

    def test_streak_gift_is_only_counted_when_finished(self) -> None:
        state = LiveState()
        state.add_gift(name="Rosa", user="@ana", quantity=1, streaking=True)
        state.add_gift(name="Rosa", user="@ana", quantity=5, streaking=False)
        self.assertEqual(state.snapshot().gifts, 5)

    def test_clock_starts_and_stops_with_connection(self) -> None:
        clock = FakeClock()
        state = LiveState(clock=clock)
        state.connect()
        clock.value = 65
        self.assertEqual(state.snapshot().elapsed_seconds, 65)
        state.disconnect()
        clock.value = 120
        self.assertEqual(state.snapshot().elapsed_seconds, 65)

    def test_formats_counts_and_elapsed_time(self) -> None:
        self.assertEqual(format_count(1234567), "1,234,567")
        self.assertEqual(format_elapsed(3661), "01:01:01")

    def test_new_connection_resets_all_values_and_activity(self) -> None:
        state = LiveState()
        state.update_viewers(20)
        state.update_likes(count=5)
        state.add_comment("Hola", "@ana")
        state.connect()
        self.assertEqual(state.snapshot(), LiveStats())
        self.assertEqual(state.activities(), [])

    def test_real_activity_types_are_inserted(self) -> None:
        state = LiveState()
        state.add_comment("Hola", "@ana")
        state.add_gift(name="Rosa", user="@bea", quantity=2, streaking=False)
        state.add_follow("@cora")
        self.assertEqual(
            [activity.title for activity in state.activities()],
            ["Nuevo seguidor", "Regalo Rosa", "Hola"],
        )

    def test_activity_is_newest_first_and_limited_to_four(self) -> None:
        state = LiveState()
        for index in range(6):
            state.add_comment(f"Comentario {index}", f"@user{index}")
        self.assertEqual(len(state.activities()), 4)
        self.assertEqual(state.activities()[0].title, "Comentario 5")
        self.assertEqual(state.activities()[-1].title, "Comentario 2")


if __name__ == "__main__":
    unittest.main()
