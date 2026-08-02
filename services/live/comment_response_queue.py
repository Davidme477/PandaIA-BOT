from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic
import inspect

from services.live.runtime_controls import RuntimeControls
from services.live.session_memory import MemoryCallback, SessionMemory
from services.ollama.ollama_service import OllamaService
from services.ollama.personalities import build_system_prompt
from services.tts.voice_manager import VoiceManager
from services.live.command_router import CommandRouter
from services.ollama.response_length import ResponseLength, finalize_ollama_response


AUTONOMOUS_IDLE_SECONDS = 90.0
LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class ResponseRequest:
    kind: str
    username: str = ""
    text: str = ""
    gift_name: str = ""
    quantity: int = 1
    command: bool = False


class CommentResponseQueue:
    """Cola FIFO única para comentarios, regalos e intervenciones autónomas."""

    def __init__(
        self,
        *,
        dashboard_settings: Mapping[str, object],
        tts_settings: Mapping[str, object],
        controls: RuntimeControls | None = None,
        memory: SessionMemory | None = None,
        ollama: OllamaService | None = None,
        voice_manager: VoiceManager | None = None,
        log_callback: LogCallback | None = None,
        memory_callback: MemoryCallback | None = None,
        autonomous_interval: float = AUTONOMOUS_IDLE_SECONDS,
    ) -> None:
        self.controls = controls or RuntimeControls(dashboard_settings, tts_settings)
        self.memory = memory or SessionMemory(on_change=memory_callback)
        if memory is not None:
            self.memory.set_callback(memory_callback)
        self.log_callback = log_callback
        self.ollama = ollama or OllamaService(logger=self._log)
        self.voice_manager = voice_manager or VoiceManager()
        self.autonomous_interval = autonomous_interval
        self._items: Queue[ResponseRequest] = Queue()
        self._stopped = Event()
        self._thread: Thread | None = None
        self._start_lock = Lock()
        self._activity_lock = Lock()
        self._connected = False
        self._last_activity = monotonic()
        self._autonomous_sent = False
        self._warmup_lock = Lock()
        self.memory.set_enabled(self.controls.enabled("use_memory"))

    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopped.clear()
            self._thread = Thread(target=self._run, name="pandaia-responses", daemon=True)
            self._thread.start()

    def set_connected(self, connected: bool) -> None:
        with self._activity_lock:
            self._connected = connected
            self._last_activity = monotonic()
            self._autonomous_sent = False
        self.memory.set_connected(connected)
        if connected:
            self.start()
            self.warmup_async()

    def update_setting(self, key: str, value: object) -> None:
        self.controls.update_dashboard(key, value)
        if key == "use_memory":
            self.memory.set_enabled(bool(value))
        if key == "autonomous_mode" and not bool(value):
            self._remove_kind("autonomous")
        if key in {"model", "respond_comments", "autonomous_mode"} and bool(value):
            self.warmup_async()

    def warmup_async(self) -> None:
        dashboard, _tts = self.controls.snapshot()
        model = str(dashboard.get("model", "")).strip()
        warmup = getattr(self.ollama, "warmup", None)
        if not model or not callable(warmup) or not self._warmup_lock.acquire(blocking=False):
            return

        def run() -> None:
            try:
                warmup(model)
            except Exception as error:
                self._log(f"Calentamiento de Ollama falló: modelo={model}, error={error}")
            finally:
                self._warmup_lock.release()

        Thread(target=run, name="pandaia-ollama-warmup", daemon=True).start()

    def enqueue(self, username: str, comment: str) -> bool:
        return self.enqueue_comment(username, comment)

    def enqueue_comment(self, username: str, comment: str) -> bool:
        clean = comment.strip()
        self.note_activity()
        if not clean or not self.controls.enabled("respond_comments"):
            if clean:
                self._log("Respuestas a comentarios desactivadas.")
            return False
        dashboard, _tts = self.controls.snapshot()
        router = CommandRouter(chat_command=str(dashboard.get("chat_command", "/")))
        route = router.route(clean)
        if route.kind in {"music", "empty_music"}:
            return False
        if bool(dashboard.get("command_only_mode", True)):
            if route.kind != "chat":
                if route.kind == "empty_chat": self._log("Comando de conversación vacío.")
                return False
            return self.enqueue_routed_comment(username, route.text)
        if not self.controls.enabled("automatic_responses") and not self._is_directed(clean):
            return False
        return self._put(ResponseRequest("comment", username.strip() or "usuario", clean))

    def enqueue_routed_comment(self, username: str, text: str) -> bool:
        self.note_activity()
        clean = text.strip()
        if not clean or not self.controls.enabled("respond_comments"):
            if clean: self._log("Respuestas a comentarios desactivadas.")
            return False
        return self._put(ResponseRequest("comment", username.strip() or "usuario", clean, command=True))

    def enqueue_gift(
        self, username: str, gift_name: str, quantity: int, *, streaking: bool = False
    ) -> bool:
        self.note_activity()
        if streaking or not self.controls.enabled("read_gifts"):
            return False
        return self._put(ResponseRequest(
            "gift", username.strip() or "usuario", gift_name=gift_name.strip(),
            quantity=max(1, int(quantity)),
        ))

    def note_activity(self) -> None:
        with self._activity_lock:
            self._last_activity = monotonic()
            self._autonomous_sent = False

    def stop(self, *, wait: bool = True) -> None:
        self.memory.set_connected(False)
        self._stopped.set()
        with self._activity_lock:
            self._connected = False
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

    def pending_count(self) -> int:
        return self._items.qsize()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _put(self, request: ResponseRequest) -> bool:
        if self._stopped.is_set():
            return False
        self.start()
        self._items.put(request)
        return True

    def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                request = self._items.get(timeout=0.05)
            except Empty:
                self._maybe_autonomous()
                continue
            try:
                self._process(request)
            finally:
                self._items.task_done()

    def _process(self, request: ResponseRequest) -> None:
        dashboard, tts = self.controls.snapshot()
        if request.kind == "comment" and not bool(dashboard.get("respond_comments", True)):
            return
        if (
            request.kind == "comment"
            and not request.command
            and not bool(dashboard.get("automatic_responses", True))
            and not self._is_directed(request.text)
        ):
            return
        if request.kind == "gift" and not bool(dashboard.get("read_gifts", True)):
            return
        if request.kind == "autonomous" and not bool(dashboard.get("autonomous_mode", True)):
            return
        prompt = self._prompt(request, dashboard)
        try:
            answer = self._generate(
                model=str(dashboard.get("model", "")),
                prompt=prompt,
                system_prompt=build_system_prompt(dashboard),
                response_length=dashboard.get("response_length", "Corta"),
            )
        except Exception as error:
            self._log(f"Error de Ollama: {error}")
            return
        if self._stopped.is_set():
            return
        validation_started = monotonic()
        reformulated = False

        def note_reformulation() -> None:
            nonlocal reformulated
            reformulated = True
            self._log(f"Reformulación de Ollama: modelo={dashboard.get('model', '')}")

        answer = finalize_ollama_response(
            answer,
            dashboard.get("response_length", "Corta"),
            reformulate=lambda original, profile: self._reformulate(original, profile, dashboard),
            safe_response=self._safe_response(request),
            on_reformulation=note_reformulation,
        )
        self._log(
            f"Validador: tiempo={monotonic() - validation_started:.3f}s, "
            f"reformulación={'sí' if reformulated else 'no'}"
        )
        if self._stopped.is_set():
            return
        if request.kind == "comment" and bool(dashboard.get("use_memory", True)):
            self.memory.add(request.username, request.text, answer)
        self._log(self._answer_log(request, answer))
        try:
            self.voice_manager.speak(
                engine=str(tts.get("engine", "kokoro")), text=answer,
                voice=str(tts.get("voice", "ef_dora")),
                speed=float(tts.get("speed", 1.0)), volume=float(tts.get("volume", 1.0)),
            )
            self.note_activity()
        except Exception as error:
            self._log(f"Error del motor TTS: {error}")

    def _prompt(self, request: ResponseRequest, dashboard: Mapping[str, object]) -> str:
        if request.kind == "gift":
            return (
                f"Agradece a @{request.username.lstrip('@')} por enviar "
                f"{request.quantity} x {request.gift_name}. Haz la frase personalizada y diferente."
            )
        if request.kind == "autonomous":
            return "Haz una intervención espontánea para animar el live o preguntar algo al público."
        context = ""
        if bool(dashboard.get("use_memory", True)):
            previous = self.memory.context(request.username)
            if previous:
                context = f"\nContexto previo con este usuario:\n{previous}"
        return (
            f"El usuario @{request.username.lstrip('@')} escribió: {request.text}"
            f"{context}\nRespóndele directamente."
        )

    def _reformulate(self, original: str, profile: ResponseLength,
                     dashboard: Mapping[str, object]) -> str:
        return self._generate(
            model=str(dashboard.get("model", "")),
            prompt=(
                "Reformula una sola vez esta respuesta para que sea directa, natural y coherente. "
                f"Conserva nombres, intención, agradecimientos y datos importantes. Usa máximo "
                f"{profile.max_words} palabras y {profile.max_sentences} "
                f"{'frase' if profile.max_sentences == 1 else 'frases'} completas. "
                f"Sin Markdown ni listas. Respuesta original: {original}"
            ),
            system_prompt=build_system_prompt(dashboard),
            response_length=profile.name,
        )

    def _generate(self, **values: object) -> str:
        """Pasa controles de latencia sin romper servicios falsos antiguos."""
        generate = getattr(self.ollama, "generate")
        signature = inspect.signature(generate)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if not accepts_kwargs and "response_length" not in signature.parameters:
            values.pop("response_length", None)
        return str(generate(**values))

    @staticmethod
    def _safe_response(request: ResponseRequest) -> str:
        if request.kind == "gift":
            return f"Gracias @{request.username.lstrip('@')} por tu regalo, de verdad alegra muchísimo este live."
        if request.kind == "autonomous":
            return "¿Cómo están todos? Cuéntenme qué canción o tema disfrutan hoy."
        return "No lo entendí bien, ¿puedes preguntarlo otra vez de forma breve?"

    def _maybe_autonomous(self) -> None:
        if not self.controls.enabled("autonomous_mode"):
            return
        with self._activity_lock:
            due = (
                self._connected and not self._autonomous_sent
                and monotonic() - self._last_activity >= self.autonomous_interval
            )
            if due:
                self._autonomous_sent = True
        if due:
            self._items.put(ResponseRequest("autonomous"))

    def _remove_kind(self, kind: str) -> None:
        kept: list[ResponseRequest] = []
        while True:
            try:
                item = self._items.get_nowait()
                self._items.task_done()
                if item.kind != kind:
                    kept.append(item)
            except Empty:
                break
        for item in kept:
            self._items.put(item)

    @staticmethod
    def _is_directed(comment: str) -> bool:
        normalized = comment.casefold()
        return any(mark in comment for mark in ("?", "¿")) or any(
            name in normalized for name in ("pandaia", "panda ia", "panda")
        )

    @staticmethod
    def _answer_log(request: ResponseRequest, answer: str) -> str:
        if request.kind == "gift":
            return f"PandaIA agradece a @{request.username.lstrip('@')}: {answer}"
        if request.kind == "autonomous":
            return f"PandaIA interviene: {answer}"
        return f"PandaIA responde a @{request.username.lstrip('@')}: {answer}"

    def _log(self, message: str) -> None:
        print(f"[PandaIA] {message}")
        if self.log_callback is not None:
            self.log_callback(message)
