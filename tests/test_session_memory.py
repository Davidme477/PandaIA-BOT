from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from services.live.session_memory import MemorySnapshot, SessionMemory, memory_panel_values


class SessionMemoryTests(unittest.TestCase):
    def test_initial_snapshot_is_empty_and_disconnected(self) -> None:
        self.assertEqual(SessionMemory().snapshot(), MemorySnapshot())

    def test_counts_users_exchanges_and_last_user(self) -> None:
        memory = SessionMemory()
        memory.set_connected(True)
        memory.add("@ana", "hola", "respuesta")
        memory.add("@ana", "otra", "respuesta 2")
        memory.add("@bea", "hola", "respuesta 3")
        snapshot = memory.snapshot()
        self.assertEqual(snapshot.user_count, 2)
        self.assertEqual(snapshot.exchange_count, 3)
        self.assertEqual(snapshot.last_username, "@bea")

    def test_users_are_separate(self) -> None:
        memory = SessionMemory()
        memory.set_connected(True)
        memory.add("@ana", "secreto ana", "respuesta ana")
        memory.add("@bea", "secreto bea", "respuesta bea")
        self.assertIn("secreto ana", memory.context("@ana"))
        self.assertNotIn("secreto bea", memory.context("@ana"))

    def test_exchange_limit_updates_current_count(self) -> None:
        memory = SessionMemory(max_exchanges=2)
        memory.set_connected(True)
        for index in range(4):
            memory.add("@ana", f"c{index}", f"r{index}")
        self.assertEqual(memory.snapshot().exchange_count, 2)
        self.assertNotIn("c0", memory.context("@ana"))

    def test_user_limit_evicts_oldest_user_and_exchanges(self) -> None:
        memory = SessionMemory(max_users=2)
        memory.set_connected(True)
        memory.add("@ana", "a", "ra")
        memory.add("@bea", "b", "rb")
        memory.add("@cora", "c", "rc")
        snapshot = memory.snapshot()
        self.assertEqual(snapshot.user_count, 2)
        self.assertEqual(snapshot.exchange_count, 2)
        self.assertEqual(memory.context("@ana"), "")

    def test_clear_resets_all_private_values(self) -> None:
        memory = SessionMemory()
        memory.set_connected(True)
        memory.add("@ana", "hola", "respuesta")
        snapshot = memory.clear()
        self.assertEqual(snapshot.user_count, 0)
        self.assertEqual(snapshot.exchange_count, 0)
        self.assertEqual(snapshot.last_username, "")

    def test_disabling_clears_memory_and_reports_disabled(self) -> None:
        memory = SessionMemory()
        memory.set_connected(True)
        memory.add("@ana", "hola", "respuesta")
        snapshot = memory.set_enabled(False)
        self.assertFalse(snapshot.enabled)
        self.assertEqual(snapshot.user_count, 0)
        self.assertEqual(memory_panel_values(snapshot)["status"], "Desactivada")

    def test_new_connection_and_disconnect_are_empty(self) -> None:
        memory = SessionMemory()
        memory.set_connected(True)
        memory.add("@ana", "hola", "respuesta")
        disconnected = memory.set_connected(False)
        self.assertFalse(disconnected.connected)
        self.assertEqual(disconnected.exchange_count, 0)
        connected = memory.set_connected(True)
        self.assertTrue(connected.connected)
        self.assertEqual(connected.user_count, 0)

    def test_callback_receives_immutable_consistent_snapshots(self) -> None:
        received: list[MemorySnapshot] = []
        memory = SessionMemory(on_change=received.append)
        memory.set_connected(True)
        memory.add("@ana", "hola", "respuesta")
        self.assertEqual(received[-1], memory.snapshot())
        with self.assertRaises((AttributeError, TypeError)):
            received[-1].user_count = 99  # type: ignore[misc]

    def test_panel_values_cover_all_states_without_private_content(self) -> None:
        disconnected = memory_panel_values(MemorySnapshot())
        disabled = memory_panel_values(MemorySnapshot(enabled=False, connected=True))
        active = memory_panel_values(MemorySnapshot(
            connected=True, user_count=2, exchange_count=3, last_username="@ana"
        ))
        self.assertEqual(disconnected["status"], "Desconectada")
        self.assertEqual(disabled["status"], "Desactivada")
        self.assertEqual(active, {
            "status": "Activa", "users": "2 / 100", "exchanges": "3", "last_user": "@ana"
        })
        self.assertNotIn("comentario", " ".join(active.values()).casefold())
        self.assertNotIn("respuesta", " ".join(active.values()).casefold())


if __name__ == "__main__":
    unittest.main()
