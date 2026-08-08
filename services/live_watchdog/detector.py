from __future__ import annotations

import hashlib
import re
import subprocess
import unicodedata
from dataclasses import dataclass


HIGH_PRIORITY = (
    "continuar en vivo",
    "seguir en vivo",
    "sigues ahi",
    "atencion requerida",
    "finalizar live",
    "se ha detectado inactividad durante el live",
    "inactividad durante el live",
    "inactividad durante el studio",
    "completa la verificacion en live studio",
    "completa la verificacion",
    "dentro de 5 minutos",
    "para continuar con el live actual",
    "tu live se cancelo por inactividad",
    "live cancelado",
    "verificacion de actividad",
    "confirmar actividad",
)
TERMS = (
    "inactividad", "actividad", "confirmar", "validacion", "validar", "verifica",
    "advertencia", "restriccion", "transmision pausada", "atencion", "requerida",
    "cancelado", "cancelada", "completa", "verificacion", "confirmar actividad",
)


def normalize_detection_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
    text = text.replace("liv3", "live").replace("liv e", "live").replace("confirn", "confirmar")
    text = text.replace("cancel0", "cancelado").replace("cance10", "cancelado")
    text = text.replace("veriflcacion", "verificacion").replace("verificaci0n", "verificacion")
    text = text.replace("validaci0n", "validacion").replace("validacionn", "validacion")
    text = text.replace("inactivldad", "inactividad").replace("inactlvidad", "inactividad")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    # Correcciones pequeñas y conservadoras de OCR.
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class WarningMatch:
    kind: str
    event_id: str
    text: str
    immediate: bool = False


def classify_warning(value: object) -> WarningMatch | None:
    text = normalize_detection_text(value)
    if not text:
        return None

    strong = next((phrase for phrase in HIGH_PRIORITY if phrase in text), "")
    hits = [term for term in TERMS if term in text]

    # Reglas de alta confianza: aceptan advertencia en LIVE Studio con evidencia visual directa o OCR.
    if "inactividad" in text and ("live" in text or "studio" in text):
        kind = "Advertencia de inactividad"
        strong = "inactividad durante el live"
        immediate = True
    elif "cancelado" in text and ("inactividad" in text or "live" in text or "studio" in text):
        kind = "Advertencia de inactividad"
        strong = "live cancelado"
        immediate = True
    elif "verificacion" in text and ("live" in text or "studio" in text or "dentro de 5 minutos" in text):
        kind = "Validación"
        strong = "completa la verificacion"
        immediate = True
    elif "verifica" in text and "actividad" in text:
        kind = "Validación"
        strong = "verificacion de actividad"
        immediate = True
    elif "confirmar" in text and "actividad" in text:
        kind = "Advertencia de inactividad"
        strong = "confirmar actividad"
        immediate = True
    elif "restric" in text:
        kind = "Restricción"
        immediate = bool(strong)
    elif "valid" in text or "verifica" in text or "verificacion" in text:
        kind = "Validación"
        immediate = bool(strong)
    elif "inactiv" in text:
        kind = "Advertencia de inactividad"
        immediate = bool(strong)
    elif "atencion" in text:
        kind = "Atención requerida"
        immediate = bool(strong)
    else:
        # No aceptamos live/actividad por sí mismos sin evidencia de adscripción ni restricción/requerimiento.
        if len(set(hits)) < 2 and not strong:
            return None
        kind = "Atención requerida"
        immediate = bool(strong)

    # Las frases de alta confianza deben disparar inmediatamente para no poner en riesgo el tiempo disponible.
    if strong and strong in text:
        immediate = True

    # Si el texto no contiene una señal suficiente, la clasificación se bloquea antes de llegar al Telegram.
    # En la clasificación de restricción, "advertencia" + "restric" es una combinación válida y no debe caer como texto irrelevante.
    context_terms = {"inactividad", "verificacion", "verifica", "validacion", "restric", "restriccion", "cancelado", "confirmar", "actividad", "atencion", "advertencia", "confirmar actividad"}
    matches = set(term for term in context_terms if term in text)
    if not strong and len(matches) < 2:
        return None

    identity = hashlib.sha256(f"{kind}:{' '.join(sorted(set(hits)))}:{strong}".encode()).hexdigest()[:16]
    return WarningMatch(kind, identity, text, immediate)


class ConsecutiveWarningDetector:
    def __init__(self) -> None: self.pending_id = ""; self.count = 0
    def inspect(self, text: object) -> WarningMatch | None:
        match = classify_warning(text)
        if match is None:
            self.pending_id = ""; self.count = 0; return None
        if match.immediate:
            self.pending_id = match.event_id
            self.count = 1
            return match
        if match.event_id == self.pending_id:
            self.count += 1
        else:
            self.pending_id, self.count = match.event_id, 1
        return match if self.count >= 2 else None


def find_live_studio(process_hint: str = "TikTok Live Studio") -> tuple[bool, str]:
    if not hasattr(subprocess, "CREATE_NO_WINDOW"): return False, ""
    try:
        output = subprocess.check_output(["tasklist", "/FO", "CSV", "/NH"], text=True,
                                         creationflags=subprocess.CREATE_NO_WINDOW, timeout=3)
    except (OSError, subprocess.SubprocessError): return False, ""
    aliases = ("tiktok live studio", "tiktoklive", normalize_detection_text(process_hint))
    for line in output.splitlines():
        if any(alias and alias in normalize_detection_text(line) for alias in aliases):
            return True, line.split(",", 1)[0].strip('"')
    return False, ""
