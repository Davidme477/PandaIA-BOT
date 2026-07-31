from __future__ import annotations

import json
import subprocess
import sys

from services.tts.base_engine import TTSEngine, TTSEngineError, VoiceOption


class WindowsTTSServiceError(TTSEngineError):
    pass


class WindowsTTSService(TTSEngine):
    engine_id = "windows"
    display_name = "Windows SAPI"

    @staticmethod
    def is_available() -> bool:
        return sys.platform == "win32"

    @staticmethod
    def _run(script: str) -> subprocess.CompletedProcess[str]:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
            check=False,
        )

    def list_voices(self) -> list[VoiceOption]:
        if not self.is_available():
            return []

        script = '''
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = @(
    $s.GetInstalledVoices() | ForEach-Object {
        [PSCustomObject]@{
            Name = $_.VoiceInfo.Name
            Culture = $_.VoiceInfo.Culture.Name
            Gender = $_.VoiceInfo.Gender.ToString()
            Age = $_.VoiceInfo.Age.ToString()
        }
    }
)
$voices | ConvertTo-Json -Compress
'''
        result = self._run(script)

        if result.returncode != 0:
            raise WindowsTTSServiceError(
                result.stderr.strip() or "No se pudieron consultar las voces de Windows."
            )

        output = result.stdout.strip()
        if not output:
            return []

        payload = json.loads(output)
        records = payload if isinstance(payload, list) else [payload]
        voices: list[VoiceOption] = []

        for record in records:
            name = str(record.get("Name", "")).strip()
            if not name:
                continue

            culture = str(record.get("Culture", "")).strip()
            gender_raw = str(record.get("Gender", "")).strip().lower()
            age = str(record.get("Age", "")).strip()

            gender = {
                "female": "Femenina",
                "male": "Masculina",
                "neutral": "Neutral",
            }.get(gender_raw, "No especificado")

            language = {
                "es-MX": "Español (México)",
                "es-ES": "Español (España)",
                "en-US": "Inglés (Estados Unidos)",
            }.get(culture, culture or "Idioma no identificado")

            voices.append(
                VoiceOption(
                    code=name,
                    display_name=name.replace("Microsoft ", ""),
                    gender=gender,
                    style=f"Voz de Windows · {age or 'Adult'}",
                    language=language,
                )
            )

        return voices

    def get_voice(self, code: str) -> VoiceOption:
        for voice in self.list_voices():
            if voice.code == code.strip():
                return voice
        raise WindowsTTSServiceError(f"La voz '{code}' no está disponible.")

    def speak(
        self,
        *,
        text: str,
        voice: str,
        speed: float = 1.0,
        volume: float = 1.0,
    ) -> None:
        safe_text = text.strip()
        if not safe_text:
            raise WindowsTTSServiceError("El texto está vacío.")

        self.get_voice(voice)

        rate = max(-5, min(5, round((speed - 1.0) * 7)))
        sapi_volume = max(0, min(100, round(volume * 100)))
        escaped_text = safe_text.replace("'", "''")
        escaped_voice = voice.replace("'", "''")

        script = f'''
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('{escaped_voice}')
$s.Rate = {rate}
$s.Volume = {sapi_volume}
$s.Speak('{escaped_text}')
'''
        result = self._run(script)
        if result.returncode != 0:
            raise WindowsTTSServiceError(
                result.stderr.strip() or "Windows no pudo reproducir la voz."
            )

    def preview(
        self, *, text: str, voice: str, speed: float, volume: float
    ) -> str:
        self.speak(text=text, voice=voice, speed=speed, volume=volume)
        return self.display_name
