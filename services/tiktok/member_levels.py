from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock

from config.settings_store import read_settings, write_settings_atomic
from core.app_paths import get_paths
from services.overlay.events import post_overlay_event


MEMBER_LEVEL_FILE = get_paths().config / "member_levels.json"
MEMBER_KEYS = ("member_level", "fans_club_level", "fan_club_level", "fans_level")
MEMBER_HINTS = ("member", "fan_club", "fans_club", "fans", "member badge")
GIFTER_HINTS = ("gifter", "donor", "donator", "gift_level", "user_grade")
DEFAULTS: dict[str, object] = {
    "member_level_ups_enabled": True, "member_ranking_enabled": True,
    "member_ranking_mode": "Periódicamente", "member_ranking_interval": 600,
    "member_ranking_duration": 12, "member_ranking_position": "Superior",
    "member_ranking_scale": 100, "member_level_duration": 8,
    "member_level_sound": False, "member_level_volume": 50,
    "member_level_text": "¡FELICIDADES, @{user}!", "member_badge_diagnostics": False,
}


def _value(obj: object, name: str, default: object = "") -> object:
    if isinstance(obj, dict): return obj.get(name, default)
    return getattr(obj, name, default)


def _integer(value: object) -> int:
    try: return max(0, int(value or 0))
    except (TypeError, ValueError): return 0


def _avatar(user: object) -> str:
    for name in ("avatar_thumb", "avatar_medium", "avatar_larger", "avatar"):
        image = _value(user, name)
        urls = _value(image, "url_list", [])
        if urls: return str(urls[0])
        direct = _value(image, "url")
        if direct: return str(direct)
    return ""


def _iter_badges(user: object) -> list[object]:
    result: list[object] = []
    for name in ("badges", "badge_list", "display_badges", "user_badges"):
        value = _value(user, name, [])
        if isinstance(value, (list, tuple)): result.extend(value)
    info = _value(user, "user_attr") or _value(user, "user_attribute")
    if info:
        for name in ("badges", "badge_list"):
            value = _value(info, name, [])
            if isinstance(value, (list, tuple)): result.extend(value)
    return result


def _badge_signature(badge: object) -> str:
    parts = [_value(badge, key) for key in ("type", "name", "badge_name", "display_type", "scene_type")]
    return " ".join(str(value).casefold() for value in parts if value)


def _level_from(obj: object) -> int:
    for key in (*MEMBER_KEYS, "level", "badge_level"):
        level = _integer(_value(obj, key))
        if level: return level
    for nested_name in ("log_extra", "privilege_log_extra", "badge_detail"):
        nested = _value(obj, nested_name)
        level = _integer(_value(nested, "level"))
        if level: return level
    return 0


@dataclass(frozen=True)
class MemberObservation:
    user_id: str
    unique_id: str
    nickname: str
    avatar: str
    member_level: int
    club_name: str = ""
    gifter_level: int = 0


def extract_member_observation(user: object, *, diagnostics: bool = False) -> MemberObservation | None:
    member_level = 0; gifter_level = 0; club_name = ""
    for key in MEMBER_KEYS:
        member_level = member_level or _integer(_value(user, key))
    gifter_level = _integer(_value(user, "gifter_level") or _value(user, "gift_level"))
    club = _value(user, "fans_club_info") or _value(user, "fans_club")
    club_name = str(_value(club, "club_name") or _value(club, "name") or "")
    unrecognized: list[str] = []
    for badge in _iter_badges(user):
        signature = _badge_signature(badge)
        if any(hint in signature for hint in GIFTER_HINTS):
            gifter_level = max(gifter_level, _level_from(badge)); continue
        if any(hint in signature for hint in MEMBER_HINTS) or any(_integer(_value(badge, key)) for key in MEMBER_KEYS):
            member_level = max(member_level, _level_from(badge))
            club_name = str(_value(badge, "club_name") or _value(badge, "name") or club_name)
        elif diagnostics:
            fields = badge.keys() if isinstance(badge, dict) else getattr(badge, "__dict__", {}).keys()
            unrecognized.append(f"{type(badge).__name__}({','.join(sorted(str(x) for x in fields)[:8])})")
    if diagnostics and unrecognized:
        print("[MemberLevel] Insignias no reconocidas:", "; ".join(unrecognized[:5]))
    if not member_level: return None
    unique_id = str(_value(user, "unique_id") or _value(user, "uniqueId") or "").strip()
    user_id = str(_value(user, "id") or _value(user, "user_id") or unique_id).strip()
    if not user_id: return None
    observation = MemberObservation(user_id, unique_id, str(_value(user, "nickname") or unique_id),
                                    _avatar(user), member_level, club_name, gifter_level)
    print(f"Nivel de miembro detectado: @{observation.unique_id or observation.nickname} — nivel {member_level}")
    return observation


class MemberLevelHistory:
    def __init__(self, path: Path = MEMBER_LEVEL_FILE, *, clock=time.time) -> None:
        self.path = Path(path); self.clock = clock; self.lock = RLock()

    def _load(self) -> dict[str, dict[str, object]]:
        data = read_settings(self.path); users = data.get("users", {})
        return dict(users) if isinstance(users, dict) else {}

    def observe(self, item: MemberObservation, *, event_id: str = "") -> tuple[dict[str, object], bool]:
        with self.lock:
            users = self._load(); now = int(self.clock()); old = users.get(item.user_id)
            if not isinstance(old, dict):
                record = {**asdict(item), "previous_level": item.member_level, "current_level": item.member_level,
                          "first_seen": now, "last_seen": now, "last_event_id": event_id}
                users[item.user_id] = record; write_settings_atomic(self.path, {"users": users}); return record, False
            previous = _integer(old.get("current_level")); increased = item.member_level > previous
            record = {**old, **asdict(item), "previous_level": previous, "current_level": max(previous, item.member_level),
                      "last_seen": now}
            if event_id and event_id == old.get("last_event_id"): increased = False
            if increased: record["last_event_id"] = event_id
            users[item.user_id] = record; write_settings_atomic(self.path, {"users": users}); return record, increased

    def top(self, limit: int = 3) -> list[dict[str, object]]:
        users = list(self._load().values())
        return sorted(users, key=lambda row: (-_integer(row.get("current_level")), int(row.get("first_seen", 0)), str(row.get("user_id", ""))))[:limit]

    def count(self) -> int: return len(self._load())
    def clear(self) -> None: write_settings_atomic(self.path, {"users": {}})


class MemberLevelManager:
    def __init__(self, settings: dict[str, object] | None = None, *, history: MemberLevelHistory | None = None,
                 sender=post_overlay_event, clock=time.time) -> None:
        self.settings = {**DEFAULTS, **(settings or {})}; self.history = history or MemberLevelHistory()
        self.sender = sender; self.clock = clock; self.last_ranking = float(clock()); self.lock = RLock()

    def update_settings(self, values: dict[str, object]) -> None:
        with self.lock: self.settings.update(values)

    def observe_user(self, user: object, *, event_id: str = "") -> bool:
        item = extract_member_observation(user, diagnostics=bool(self.settings.get("member_badge_diagnostics")))
        if item is None: return False
        record, increased = self.history.observe(item, event_id=event_id)
        sent = False
        if increased and bool(self.settings.get("member_level_ups_enabled", True)):
            sent = self.sender(self.level_event(record, event_id=event_id))
        self.maybe_send_ranking()
        return bool(sent)

    def level_event(self, record: dict[str, object], *, event_id: str = "", test: bool = False) -> dict[str, object]:
        return {"type": "member_level_up", "event_id": event_id or uuid.uuid4().hex,
                "user_id": record.get("user_id", ""), "unique_id": record.get("unique_id", ""),
                "nickname": record.get("nickname", ""), "avatar_url": record.get("avatar", ""),
                "previous_level": record.get("previous_level", 0), "new_level": record.get("current_level", 0),
                "timestamp": int(self.clock()), "duration_ms": int(float(self.settings.get("member_level_duration", 8)) * 1000),
                "sound": bool(self.settings.get("member_level_sound", False)), "volume": int(self.settings.get("member_level_volume", 50)),
                "message": str(self.settings.get("member_level_text", "¡FELICIDADES, @{user}!")), "test": test}

    def ranking_event(self, members: list[dict[str, object]] | None = None, *, test: bool = False) -> dict[str, object]:
        rows = members if members is not None else self.history.top()
        return {"type": "member_level_leaderboard", "event_id": uuid.uuid4().hex, "members": rows[:3],
                "duration_ms": int(float(self.settings.get("member_ranking_duration", 12)) * 1000),
                "position": self.settings.get("member_ranking_position", "Superior"),
                "scale": int(self.settings.get("member_ranking_scale", 100)),
                "mode": self.settings.get("member_ranking_mode", "Periódicamente"), "test": test}

    def maybe_send_ranking(self) -> bool:
        mode = str(self.settings.get("member_ranking_mode", "Periódicamente"))
        if not bool(self.settings.get("member_ranking_enabled", True)) or mode == "Oculto": return False
        now = self.clock(); interval = max(60, int(self.settings.get("member_ranking_interval", 600)))
        if mode != "Siempre visible" and now - self.last_ranking < interval: return False
        if not self.history.top(): return False
        self.last_ranking = now; return bool(self.sender(self.ranking_event()))
