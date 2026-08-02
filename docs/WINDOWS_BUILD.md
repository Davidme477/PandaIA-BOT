# Construcción de PandaIA BOT para Windows

PandaIA usa PyInstaller en modo `onedir`. Es la opción estable para PySide6, PyTorch y Kokoro: evita la extracción de `onefile`, reduce el tiempo de arranque y simplifica las DLL nativas.

## Requisitos de construcción

- Windows x64 y Python 3.12 x64.
- Dependencias de `requirements.txt`.
- PyInstaller fijado en `requirements-build.txt`.
- Inno Setup 6 oficial solo para producir el instalador.

Desde PowerShell:

```powershell
.\scripts\build_windows.ps1 -Python python -Clean
```

La carpeta portable queda en `dist\PandaIA`. Para el instalador, abre `packaging\installer\PandaIA.iss` con Inno Setup 6 o ejecuta `ISCC.exe packaging\installer\PandaIA.iss`. El resultado queda en `installer_output`.

## Datos y dependencias externas

El ejecutable se instala normalmente en `C:\Program Files\PandaIA BOT`. Los datos modificables viven en `%LOCALAPPDATA%\PandaIA`, incluidos `config`, `cache`, `logs`, `temp`, `credentials`, `animations_custom` y `sounds_custom`. Actualizar o desinstalar no elimina esa carpeta.

Ollama, sus modelos y `cloudflared.exe` no se empaquetan. Ollama es opcional; Cloudflare solo se inicia al solicitar un enlace HTTPS. Windows SAPI usa las voces instaladas en Windows. PandaIA nunca incluye `config/settings.json`, `config/spotify_local.json`, `config/telegram_local.json`, tokens, caché o modelos personales.

## Prueba portable

Ejecuta `dist\PandaIA\PandaIA.exe` desde una ruta con espacios. Comprueba navegación, cierre y reapertura, overlay local y TTS. Las pruebas automáticas no conectan TikTok, Spotify, Telegram ni Cloudflare. El instalador se desinstala desde Configuración de Windows; las preferencias quedan disponibles para una reinstalación. Para borrarlas voluntariamente, elimina `%LOCALAPPDATA%\PandaIA` después de desinstalar.
