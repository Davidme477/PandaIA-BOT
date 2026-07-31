from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


class OllamaServiceError(RuntimeError):
    """Error controlado al comunicarse con Ollama."""


class OllamaService:
    def __init__(
        self,
        timeout: float = 30.0,
    ) -> None:
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            self.list_models()
            return True
        except OllamaServiceError:
            return False

    def list_models(self) -> list[str]:
        request = Request(
            OLLAMA_TAGS_URL,
            method="GET",
            headers={
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                response_data = response.read().decode("utf-8")

        except HTTPError as error:
            error_content = error.read().decode(
                "utf-8",
                errors="replace",
            )

            raise OllamaServiceError(
                "Ollama rechazó la consulta de modelos: "
                f"{error.code} {error_content}"
            ) from error

        except URLError as error:
            raise OllamaServiceError(
                "No se pudo conectar con Ollama. "
                "Verifica que Ollama esté abierto."
            ) from error

        except TimeoutError as error:
            raise OllamaServiceError(
                "Ollama tardó demasiado en responder."
            ) from error

        except OSError as error:
            raise OllamaServiceError(
                f"Error de conexión con Ollama: {error}"
            ) from error

        try:
            data = json.loads(response_data)
        except json.JSONDecodeError as error:
            raise OllamaServiceError(
                "Ollama devolvió una respuesta inválida."
            ) from error

        models = data.get("models", [])
        model_names: list[str] = []

        for model_data in models:
            model_name = str(
                model_data.get("name")
                or model_data.get("model")
                or ""
            ).strip()

            if model_name:
                model_names.append(model_name)

        return sorted(
            set(model_names),
            key=str.casefold,
        )

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        model = model.strip()
        prompt = prompt.strip()
        system_prompt = system_prompt.strip()

        if not model:
            raise OllamaServiceError(
                "No se seleccionó ningún modelo."
            )

        if not prompt:
            raise OllamaServiceError(
                "El mensaje para Ollama está vacío."
            )

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }

        if system_prompt:
            payload["system"] = system_prompt

        request = Request(
            OLLAMA_GENERATE_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                response_data = response.read().decode("utf-8")

        except HTTPError as error:
            error_content = error.read().decode(
                "utf-8",
                errors="replace",
            )

            raise OllamaServiceError(
                "Ollama rechazó la generación: "
                f"{error.code} {error_content}"
            ) from error

        except URLError as error:
            raise OllamaServiceError(
                "No se pudo conectar con Ollama."
            ) from error

        except TimeoutError as error:
            raise OllamaServiceError(
                "El modelo tardó demasiado en responder."
            ) from error

        except OSError as error:
            raise OllamaServiceError(
                f"Error usando Ollama: {error}"
            ) from error

        try:
            data = json.loads(response_data)
        except json.JSONDecodeError as error:
            raise OllamaServiceError(
                "Ollama devolvió una respuesta inválida."
            ) from error

        answer = str(
            data.get("response", "")
        ).strip()

        if not answer:
            raise OllamaServiceError(
                "Ollama no generó ninguna respuesta."
            )

        return answer