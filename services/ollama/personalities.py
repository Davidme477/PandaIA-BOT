from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PersonalityOption:
    name: str
    instructions: str


PERSONALITIES = (
    PersonalityOption("Amigable", "Sé cercana, respetuosa y natural."),
    PersonalityOption("Entusiasta", "Sé alegre, energética y expresiva."),
    PersonalityOption("Profesional", "Sé clara, educada y moderada."),
    PersonalityOption(
        "Divertida",
        "Usa humor ligero, sé carismática y mantente apropiada para TikTok.",
    ),
    PersonalityOption(
        "Romántica",
        "Sé cálida, afectuosa y adecuada para un live de música romántica.",
    ),
    PersonalityOption("Personalizada", ""),
)

PERSONALITY_NAMES = tuple(option.name for option in PERSONALITIES)
_INSTRUCTIONS = {option.name: option.instructions for option in PERSONALITIES}


def normalize_personality(value: object) -> str:
    name = str(value).strip()
    if name in PERSONALITY_NAMES:
        return name
    legacy = {
        "Amigable, divertida y carismática": "Amigable",
        "Amigable, divertida y carismÃ¡tica": "Amigable",
    }
    return legacy.get(name, "Amigable")


def personality_instructions(settings: Mapping[str, object]) -> str:
    personality = normalize_personality(settings.get("personality", "Amigable"))
    if personality == "Personalizada":
        custom = str(settings.get("custom_personality_prompt", "")).strip()
        return custom or _INSTRUCTIONS["Amigable"]
    return _INSTRUCTIONS[personality]


def build_system_prompt(settings: Mapping[str, object]) -> str:
    personality = normalize_personality(settings.get("personality", "Amigable"))
    language = str(settings.get("language", "Español")).strip() or "Español"
    display_name = (
        str(settings.get("custom_personality_name", "Personalizada")).strip()
        if personality == "Personalizada"
        else personality
    )
    return (
        "Eres PandaIA, asistente de un TikTok Live. "
        f"Personalidad {display_name}: {personality_instructions(settings)} "
        f"Responde exclusivamente en {language}. "
        "Usa frases cortas, naturales y adecuadas para ser pronunciadas por TTS. "
        "No uses Markdown, listas, emojis excesivos ni explicaciones largas."
    )


def dashboard_defaults(settings: Mapping[str, object] | None = None) -> dict[str, object]:
    source = dict(settings or {})
    defaults: dict[str, object] = {
        "model": "",
        "personality": "Amigable",
        "language": "Español",
        "custom_personality_name": "Mi personalidad",
        "custom_personality_prompt": "",
        "respond_comments": True,
        "command_only_mode": True,
        "chat_command": "/",
        "read_gifts": True,
        "use_memory": True,
        "automatic_responses": True,
        "autonomous_mode": True,
    }
    defaults.update(source)
    defaults["personality"] = normalize_personality(defaults["personality"])
    return defaults


def generate_personality_preview(
    ollama: object,
    *,
    model: str,
    message: str,
    settings: Mapping[str, object],
) -> str:
    generate = getattr(ollama, "generate")
    return str(generate(
        model=model,
        prompt=message,
        system_prompt=build_system_prompt(settings),
    )).strip()
