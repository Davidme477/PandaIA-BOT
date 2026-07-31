from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread

from services.ollama.ollama_service import OllamaService
from services.tts.voice_manager import VoiceManager


LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class CommentRequest:
    username: str
    comment: str


class CommentResponseQueue:
    """Procesa comentarios secuencialmente fuera de TikTok y de la UI."""

    def __init__(
        self,
        *,
        dashboard_settings: Mapping[str, object],
        tts_settings: Mapping[str, object],
        ollama: OllamaService | None = None,
        voice_manager: VoiceManager | None = None,
        log_callback: LogCallback | None = None,
    ) -> None:
        self.dashboard_settings = dict(dashboard_settings)
        self.tts_settings = dict(tts_settings)
        self.ollama = ollama or OllamaService()
        self.voice_manager = voice_manager or VoiceManager()
        self.log_callback = log_callback
        self._items: Queue[CommentRequest] = Queue()
        self._stopped = Event()
        self._thread: Thread | None = None
        self._start_lock = Lock()

    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopped.clear()
            self._thread = Thread(
                target=self._run,
                name="pandaia-comment-responses",
                daemon=True,
            )
            self._thread.start()

    def enqueue(self, username: str, comment: str) -> bool:
        if not bool(self.dashboard_settings.get("respond_comments", True)):
            return False
        clean_comment = comment.strip()
        if not clean_comment or self._stopped.is_set():
            return False
        self.start()
        self._items.put(CommentRequest(username.strip() or "usuario", clean_comment))
        return True

    def stop(self, *, wait: bool = True) -> None:
        self._stopped.set()
        self.clear()
        thread = self._thread
        if wait and thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def clear(self) -> None:
        while True:
            try:
                self._items.get_nowait()
                self._items.task_done()
            except Empty:
                return

    def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                request = self._items.get(timeout=0.1)
            except Empty:
                continue
            try:
                self._process(request)
            finally:
                self._items.task_done()

    def _process(self, request: CommentRequest) -> None:
        try:
            answer = self.ollama.generate(
                model=str(self.dashboard_settings.get("model", "")),
                prompt=(
                    f"El usuario @{request.username.lstrip('@')} escribió: "
                    f"{request.comment}\nRespóndele directamente."
                ),
                system_prompt=self._system_prompt(),
            )
        except Exception as error:
            self._log(f"Error de Ollama al responder a @{request.username.lstrip('@')}: {error}")
            return

        if self._stopped.is_set():
            return
        self._log(f"PandaIA responde a @{request.username.lstrip('@')}: {answer}")
        try:
            self.voice_manager.speak(
                engine=str(self.tts_settings.get("engine", "kokoro")),
                text=answer,
                voice=str(self.tts_settings.get("voice", "ef_dora")),
                speed=float(self.tts_settings.get("speed", 1.0)),
                volume=float(self.tts_settings.get("volume", 1.0)),
            )
        except Exception as error:
            self._log(f"Error del motor TTS: {error}")

    def _system_prompt(self) -> str:
        personality = str(self.dashboard_settings.get("personality", "Amigable"))
        language = str(self.dashboard_settings.get("language", "Español"))
        return (
            "Eres PandaIA, asistente de un TikTok Live. "
            f"Tu personalidad es: {personality}. Responde en {language}. "
            "Da una respuesta breve, natural, amable y apropiada para decirse en voz alta. "
            "No uses listas, formato Markdown ni explicaciones largas."
        )

    def _log(self, message: str) -> None:
        print(f"[PandaIA] {message}")
        if self.log_callback is not None:
            self.log_callback(message)
