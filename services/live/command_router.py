from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


INVISIBLE_CATEGORIES = {"Cf"}


@dataclass(frozen=True)
class CommandRoute:
    kind: str
    text: str = ""


def normalize_mobile_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    cleaned = []
    for character in normalized:
        if unicodedata.category(character) in INVISIBLE_CATEGORIES:
            cleaned.append(" ")
        elif character.isspace():
            cleaned.append(" ")
        else:
            cleaned.append(character)
    return re.sub(r" +", " ", "".join(cleaned)).strip()


def normalize_command(value: object, default: str) -> str:
    return normalize_mobile_text(value).replace(" ", "") or default


class CommandRouter:
    def __init__(self, *, chat_command: str = "/", music_command: str = "a/") -> None:
        self.chat_command = normalize_command(chat_command, "/")
        self.music_command = normalize_command(music_command, "a/")

    def update(self, *, chat_command: str | None = None, music_command: str | None = None) -> None:
        if chat_command is not None: self.chat_command = normalize_command(chat_command, "/")
        if music_command is not None: self.music_command = normalize_command(music_command, "a/")

    @staticmethod
    def _prefix_pattern(command: str) -> re.Pattern[str]:
        parts = [re.escape(character) for character in command]
        return re.compile(r"^" + r"\s*".join(parts) + r"\s*(.*)$", re.IGNORECASE)

    def route(self, comment: object) -> CommandRoute:
        clean = normalize_mobile_text(comment)
        if not clean: return CommandRoute("normal")
        music = self._prefix_pattern(self.music_command).fullmatch(clean)
        if music:
            query = normalize_mobile_text(music.group(1))
            return CommandRoute("music", query) if len(query) >= 3 else CommandRoute("empty_music")
        chat = self._prefix_pattern(self.chat_command).fullmatch(clean)
        if chat:
            message = normalize_mobile_text(chat.group(1))
            return CommandRoute("chat", message) if message else CommandRoute("empty_chat")
        return CommandRoute("normal")
