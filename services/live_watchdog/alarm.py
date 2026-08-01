from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AlertCycle:
    event_id: str = ""; started_at: float = 0; last_sent_at: float = -1; attended: bool = False; missing_reads: int = 0; final_sent: bool = False

    def start(self, event_id: str, now: float) -> bool:
        if self.event_id == event_id and not self.attended: return False
        self.event_id, self.started_at, self.last_sent_at = event_id, now, -1
        self.attended, self.missing_reads, self.final_sent = False, 0, False
        return True

    def due(self, now: float, interval: int = 60, duration: int = 240) -> tuple[bool, bool]:
        if not self.event_id or self.attended: return False, False
        elapsed = max(0, now - self.started_at)
        if elapsed >= duration:
            if self.final_sent: return False, False
            self.final_sent = True; self.last_sent_at = now; return True, True
        if self.last_sent_at >= 0 and now - self.last_sent_at < interval: return False, False
        self.last_sent_at = now
        return True, False

    def acknowledge(self) -> None: self.attended = True
    def observe_missing(self, required: int = 2) -> bool:
        self.missing_reads += 1
        if self.missing_reads >= required: self.acknowledge(); return True
        return False
    def observe_present(self) -> None: self.missing_reads = 0
