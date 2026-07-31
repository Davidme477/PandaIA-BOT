from __future__ import annotations

import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from services.tts.kokoro_service import (  # noqa: E402
    KokoroService,
    KokoroServiceError,
)


TEST_TEXT = (
    "Hola, soy PandaIA. "
    "Bienvenidos al directo de Latidos Musicales."
)


def play_on_windows(audio_path: Path) -> None:
    if sys.platform != "win32":
        print("Audio creado. Reprodúcelo manualmente:", audio_path)
        return

    import winsound

    winsound.PlaySound(
        str(audio_path),
        winsound.SND_FILENAME,
    )


def main() -> None:
    service = KokoroService()

    print("=" * 60)
    print("VOCES ESPAÑOLAS DISPONIBLES")
    print("=" * 60)

    for voice in service.list_voices():
        print(
            f"{voice.code} | {voice.display_name} | "
            f"{voice.gender}"
        )

    output_path = (
        PROJECT_DIR
        / "temp"
        / "kokoro"
        / "prueba_dora.wav"
    )

    print("=" * 60)
    print("Generando voz. La primera ejecución puede tardar...")
    print("=" * 60)

    try:
        generated_file = service.save_wav(
            text=TEST_TEXT,
            output_path=output_path,
            voice="ef_dora",
            speed=1.0,
        )
    except KokoroServiceError as error:
        print("ERROR:", error)
        raise SystemExit(1) from error

    print("Audio creado:", generated_file)
    print("Reproduciendo...")

    play_on_windows(generated_file)

    print("=" * 60)
    print("PRUEBA FINALIZADA CORRECTAMENTE")
    print("=" * 60)


if __name__ == "__main__":
    main()
