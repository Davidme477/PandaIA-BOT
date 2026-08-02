from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Callable


@dataclass(frozen=True)
class ResponseLength:
    name: str
    min_words: int
    max_words: int
    max_sentences: int
    max_tokens: int


RESPONSE_LENGTHS = {
    "Corta": ResponseLength("Corta", 10, 15, 1, 32),
    "Normal": ResponseLength("Normal", 15, 25, 2, 64),
    "Detallada": ResponseLength("Detallada", 25, 45, 3, 96),
}
RESPONSE_LENGTH_NAMES = tuple(RESPONSE_LENGTHS)
SAFE_RESPONSE = "No lo entendí bien, ¿puedes preguntarlo otra vez de forma breve?"
_WORD_RE = re.compile(r"\b[\wÀ-ÿ]+(?:['’\-][\wÀ-ÿ]+)*\b", re.UNICODE)
_SENTENCE_RE = re.compile(r".*?[.!?]+(?:[\"'»”)]*)?(?=\s|$)", re.DOTALL)


def normalize_response_length(value: object) -> str:
    text = str(value or "").strip().casefold()
    return next((name for name in RESPONSE_LENGTH_NAMES if name.casefold() == text), "Corta")


def response_length(value: object) -> ResponseLength:
    return RESPONSE_LENGTHS[normalize_response_length(value)]


def generation_token_limit(value: object) -> int:
    return response_length(value).max_tokens


def clean_ollama_response(value: object) -> str:
    text = str(value or "").replace("\r", "\n")
    text = re.sub(r"(?is)<think>.*?</think>", "", text)
    text = re.sub(r"```(?:\w+)?\s*(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[([^]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?m)^\s{0,3}(?:#{1,6}|[-*+]\s+|\d+[.)]\s+|>\s*)", "", text)
    text = re.sub(r"(?<!\w)([*_~]{1,3})(.+?)\1(?!\w)", r"\2", text)
    return re.sub(r"\s+", " ", text).strip()


def count_words(text: str) -> int: return len(_WORD_RE.findall(text))


def complete_sentences(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", match.group(0)).strip() for match in _SENTENCE_RE.finditer(text)]


def sentence_count(text: str) -> int:
    sentences = complete_sentences(text)
    return len(sentences) if sentences else (1 if text.strip() else 0)


def _within_limits(text: str, profile: ResponseLength) -> bool:
    words = count_words(text)
    complete = bool(re.search(r"[.!?][\"'»”)]*\s*$", text))
    return (
        bool(text)
        and words <= profile.max_words
        and sentence_count(text) <= profile.max_sentences
        and (words <= 5 or complete)
    )


def _trim_at_complete_sentence(text: str, profile: ResponseLength) -> str:
    chosen: list[str] = []
    for sentence in complete_sentences(text):
        candidate = " ".join((*chosen, sentence))
        if len(chosen) >= profile.max_sentences or count_words(candidate) > profile.max_words: break
        chosen.append(sentence)
    return " ".join(chosen)


def finalize_ollama_response(
    value: object,
    level: object,
    *,
    reformulate: Callable[[str, ResponseLength], str] | None = None,
    safe_response: str = SAFE_RESPONSE,
    on_reformulation: Callable[[], None] | None = None,
) -> str:
    profile = response_length(level); clean = clean_ollama_response(value)
    if _within_limits(clean, profile): return clean
    trimmed = _trim_at_complete_sentence(clean, profile)
    if trimmed: return trimmed
    if reformulate is not None:
        if on_reformulation is not None: on_reformulation()
        try: rewritten = clean_ollama_response(reformulate(clean, profile))
        except Exception: rewritten = ""
        if _within_limits(rewritten, profile): return rewritten
        rewritten_trimmed = _trim_at_complete_sentence(rewritten, profile)
        if rewritten_trimmed: return rewritten_trimmed
    fallback = clean_ollama_response(safe_response)
    return fallback if _within_limits(fallback, profile) else SAFE_RESPONSE
