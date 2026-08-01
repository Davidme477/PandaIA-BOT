from __future__ import annotations

import hashlib
import re
import subprocess
import unicodedata
from dataclasses import dataclass


HIGH_PRIORITY = ("continuar en vivo", "seguir en vivo", "sigues ahi", "atencion requerida", "finalizar live")
TERMS = ("inactividad", "actividad", "confirmar", "validacion", "validar", "verifica",
         "advertencia", "restriccion", "transmision pausada", "atencion", "requerida")


def normalize_detection_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    # Correcciones pequeñas y conservadoras de OCR.
    return re.sub(r"\s+", " ", text.replace("validaci0n", "validacion").replace("inactivldad", "inactividad")).strip()


@dataclass(frozen=True)
class WarningMatch:
    kind: str
    event_id: str
    text: str
    immediate: bool = False


def classify_warning(value: object) -> WarningMatch | None:
    text = normalize_detection_text(value)
    strong = next((phrase for phrase in HIGH_PRIORITY if phrase in text), "")
    hits = [term for term in TERMS if term in text]
    if not strong and len(set(hits)) < 2: return None
    if "restric" in text: kind = "Restricción"
    elif "valid" in text or "verifica" in text: kind = "Validación"
    elif "inactiv" in text or "actividad" in text: kind = "Advertencia de inactividad"
    else: kind = "Atención requerida"
    identity = hashlib.sha256(f"{kind}:{' '.join(sorted(set(hits)))}:{strong}".encode()).hexdigest()[:16]
    return WarningMatch(kind, identity, text, bool(strong))


class ConsecutiveWarningDetector:
    def __init__(self) -> None: self.pending_id = ""; self.count = 0
    def inspect(self, text: object) -> WarningMatch | None:
        match = classify_warning(text)
        if match is None: self.pending_id = ""; self.count = 0; return None
        if match.immediate: return match
        if match.event_id == self.pending_id: self.count += 1
        else: self.pending_id, self.count = match.event_id, 1
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
