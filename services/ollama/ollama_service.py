from __future__ import annotations

from collections.abc import Callable
import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.ollama.response_length import generation_token_limit


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
DEFAULT_KEEP_ALIVE = "10m"
_THINKING_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


class OllamaServiceError(RuntimeError):
    """Error controlado al comunicarse con Ollama."""


class OllamaService:
    def __init__(
        self,
        timeout: float = 30.0,
        *,
        opener: Callable[..., object] | None = None,
        keep_alive: str = DEFAULT_KEEP_ALIVE,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        self.timeout = timeout
        self.opener = opener or urlopen
        self.keep_alive = keep_alive
        self.logger = logger

    def is_available(self) -> bool:
        try:
            self.list_models()
            return True
        except OllamaServiceError:
            return False

    def list_models(self) -> list[str]:
        request = Request(OLLAMA_TAGS_URL, method="GET", headers={"Accept": "application/json"})
        try:
            with self.opener(request, timeout=self.timeout) as response:
                response_data = response.read().decode("utf-8")
        except HTTPError as error:
            content = error.read().decode("utf-8", errors="replace")
            raise OllamaServiceError(
                f"Ollama rechazó la consulta de modelos: {error.code} {content}"
            ) from error
        except URLError as error:
            raise OllamaServiceError(
                "No se pudo conectar con Ollama. Verifica que Ollama esté abierto."
            ) from error
        except TimeoutError as error:
            raise OllamaServiceError("Ollama tardó demasiado en responder.") from error
        except OSError as error:
            raise OllamaServiceError(f"Error de conexión con Ollama: {error}") from error
        try:
            data = json.loads(response_data)
        except json.JSONDecodeError as error:
            raise OllamaServiceError("Ollama devolvió una respuesta inválida.") from error
        names = []
        for item in data.get("models", []):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                names.append(name)
        return sorted(set(names), key=str.casefold)

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str = "",
        response_length: object = "Corta",
    ) -> str:
        model, prompt, system_prompt = model.strip(), prompt.strip(), system_prompt.strip()
        if not model:
            raise OllamaServiceError("No se seleccionó ningún modelo.")
        if not prompt:
            raise OllamaServiceError("El mensaje para Ollama está vacío.")
        payload: dict[str, object] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_predict": generation_token_limit(response_length),
                "num_ctx": 2048,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt
        qwen3 = "qwen3" in model.casefold()
        if qwen3:
            payload["think"] = False
        started = time.monotonic()
        try:
            response_data = self._post_generate(payload)
        except HTTPError as error:
            if qwen3 and error.code == 400:
                payload.pop("think", None)
                payload["prompt"] = f"/no_think\n{prompt}"
                try:
                    response_data = self._post_generate(payload)
                except HTTPError as fallback_error:
                    error = fallback_error
                else:
                    return self._parse_generation(response_data, model, started)
            content = error.read().decode("utf-8", errors="replace")
            raise OllamaServiceError(
                f"Ollama rechazó la generación: {error.code} {content}"
            ) from error
        except URLError as error:
            raise OllamaServiceError("No se pudo conectar con Ollama.") from error
        except TimeoutError as error:
            raise OllamaServiceError("El modelo tardó demasiado en responder.") from error
        except OSError as error:
            raise OllamaServiceError(f"Error usando Ollama: {error}") from error
        return self._parse_generation(response_data, model, started)

    def warmup(self, model: str) -> float:
        """Carga el modelo sin generar texto y devuelve el tiempo empleado."""
        model = model.strip()
        if not model:
            return 0.0
        started = time.monotonic()
        self._post_generate({
            "model": model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": 2048},
        })
        elapsed = time.monotonic() - started
        self._log(f"Ollama calentado: modelo={model}, carga={elapsed:.2f}s")
        return elapsed

    def _post_generate(self, payload: dict[str, object]) -> str:
        request = Request(
            OLLAMA_GENERATE_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with self.opener(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8")

    def _parse_generation(self, response_data: str, model: str, started: float) -> str:
        try:
            data = json.loads(response_data)
        except json.JSONDecodeError as error:
            raise OllamaServiceError("Ollama devolvió una respuesta inválida.") from error
        answer = _THINKING_RE.sub("", str(data.get("response", ""))).strip()
        answer = re.sub(
            r"(?is)^\s*(?:thinking|razonamiento)\s*:.*?(?=\n\s*respuesta\s*:)", "", answer
        )
        answer = re.sub(r"(?is)^\s*respuesta\s*:\s*", "", answer).strip()
        if not answer:
            raise OllamaServiceError("Ollama no generó ninguna respuesta.")
        elapsed = time.monotonic() - started
        load = float(data.get("load_duration", 0) or 0) / 1_000_000_000
        self._log(
            f"Ollama respondió: modelo={model}, carga={load:.2f}s, respuesta={elapsed:.2f}s"
        )
        return answer

    def _log(self, message: str) -> None:
        if self.logger is not None:
            self.logger(message)
        else:
            print(f"[PandaIA] {message}")
