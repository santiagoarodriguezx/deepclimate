"""Remote chat APIs may explain project evidence; they never create measurements."""

import json
import logging
import os
import threading
import time
from collections import deque

import httpx

logger = logging.getLogger(__name__)


class RemoteExplanationAssistant:
    API_URL = ""
    API_KEY_ENV = ""
    MODEL_ENV = ""
    DEFAULT_MODEL = ""
    PROVIDER = "remote"
    MAX_REQUESTS_PER_MINUTE = 10
    MAX_CONTEXT_CHARS = 12_000
    _request_times = deque()
    _request_lock = threading.Lock()

    def explain(self, query: str, evidence: dict) -> tuple[str | None, str | None]:
        api_key = os.getenv(self.API_KEY_ENV, "").strip()
        model = os.getenv(self.MODEL_ENV, self.DEFAULT_MODEL).strip()
        if not api_key or not model:
            return None, None
        if not self._allow_request():
            logger.warning("%s request limit reached; using the local evidence summary.", self.PROVIDER)
            return None, None

        context = json.dumps(
            {"question": query, "verified_project_data": evidence},
            ensure_ascii=False,
            default=str,
        )[: self.MAX_CONTEXT_CHARS]
        payload = {
            "model": model,
            "temperature": 0.2,
            "max_tokens": 500,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Responde en español claro y breve. Interpreta únicamente los datos entregados. "
                        "No inventes cifras, pronósticos, estaciones ni frescura. Si falta evidencia, dilo. "
                        "Una correlación no demuestra causalidad. Distingue mediciones observadas de predicciones. "
                        "No calcules ni sustituyas pronósticos meteorológicos: resume los resultados verificados."
                    ),
                },
                {"role": "user", "content": context},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        headers.update(self._extra_headers())
        with httpx.Client(timeout=20.0) as client:
            response = client.post(self.API_URL, headers=headers, json=payload)
            response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"{self.PROVIDER} devolvió una respuesta sin texto.") from exc
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"{self.PROVIDER} devolvió una respuesta vacía.")
        logger.info("%s explanation completed (model=%s).", self.PROVIDER, model)
        return content.strip(), model

    def _extra_headers(self) -> dict[str, str]:
        return {}

    @classmethod
    def _allow_request(cls) -> bool:
        now = time.monotonic()
        with cls._request_lock:
            while cls._request_times and now - cls._request_times[0] >= 60:
                cls._request_times.popleft()
            if len(cls._request_times) >= cls.MAX_REQUESTS_PER_MINUTE:
                return False
            cls._request_times.append(now)
            return True


class NvidiaNimAssistant(RemoteExplanationAssistant):
    API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
    API_KEY_ENV = "NVIDIA_API_KEY"
    MODEL_ENV = "NVIDIA_MODEL"
    DEFAULT_MODEL = "nvidia/nemotron-3.5-bolt-e4b"
    PROVIDER = "NVIDIA NIM"


class OpenRouterAssistant(RemoteExplanationAssistant):
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    API_KEY_ENV = "OPENROUTER_API_KEY"
    MODEL_ENV = "OPENROUTER_MODEL"
    PROVIDER = "OpenRouter"

    def _extra_headers(self) -> dict[str, str]:
        return {
            "HTTP-Referer": "http://localhost",
            "X-Title": "SIATA Intelligence",
        }


def configured_assistant() -> tuple[RemoteExplanationAssistant | None, str | None]:
    """Prefer NVIDIA's hosted API; keep configured OpenRouter as a remote fallback."""
    if os.getenv("NVIDIA_API_KEY", "").strip():
        return NvidiaNimAssistant(), "nvidia_nim"
    if os.getenv("OPENROUTER_API_KEY", "").strip() and os.getenv("OPENROUTER_MODEL", "").strip():
        return OpenRouterAssistant(), "openrouter"
    return None, None
