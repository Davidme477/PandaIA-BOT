from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import inspect
from services.ollama.response_length import normalize_response_length, response_length


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
    profile = response_length(settings.get("response_length", "Corta"))
    return (
        "Eres PandaIA, asistente de un TikTok Live. "
        f"Personalidad {display_name}: {personality_instructions(settings)} "
        f"Responde exclusivamente en {language}. "
        "Responde directamente y no repitas la pregunta. "
        "No uses Markdown, listas, explicaciones innecesarias ni te presentes como una IA. "
        "Usa lenguaje natural, conversacional y adecuado para ser pronunciado por TTS. "
        "Si no entiendes, haz una sola pregunta breve. "
        f"Longitud {profile.name}: usa entre {profile.min_words} y {profile.max_words} palabras "
        f"y un máximo de {profile.max_sentences} {'frase' if profile.max_sentences == 1 else 'frases'}."
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
        "response_length": "Corta",
    }
    defaults.update(source)
    defaults["personality"] = normalize_personality(defaults["personality"])
    defaults["response_length"] = normalize_response_length(defaults["response_length"])
    return defaults


def generate_personality_preview(
    ollama: object,
    *,
    model: str,
    message: str,
    settings: Mapping[str, object],
) -> str:
    generate = getattr(ollama, "generate")
    values = dict(
        model=model,
        prompt=message,
        system_prompt=build_system_prompt(settings),
        response_length=settings.get("response_length", "Corta"),
    )
    signature = inspect.signature(generate)
    if (
        "response_length" not in signature.parameters
        and not any(item.kind == inspect.Parameter.VAR_KEYWORD for item in signature.parameters.values())
    ):
        values.pop("response_length")
    return str(generate(**values)).strip()
