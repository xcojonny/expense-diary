"""Chat-Completions-Adapter für OpenAI, OpenRouter und Ollama.

Alle drei sprechen dasselbe `/chat/completions`-Format mit `image_url` als
Data-URI — der Unterschied sind Basis-URL, Auth-Header und Modellname, also
ENV-Werte statt Code.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.core.logging import get_logger
from app.integrations.llm.base import LlmError

log = get_logger(__name__)


class OpenAiCompatibleVisionModel:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._provider = provider
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return f"{self._provider}:{self._model}"

    @property
    def available(self) -> bool:
        return bool(self._base_url and self._model)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._provider == "openrouter":
            # OpenRouter bittet um diese Kennung; ohne sie wird gedrosselt.
            headers["HTTP-Referer"] = "https://github.com/xcojonny/expense-diary"
            headers["X-Title"] = "expense-diary"
        return headers

    async def extract(self, *, image: bytes, media_type: str, prompt: str) -> str | None:
        if not self.available:
            return None

        data_uri = f"data:{media_type};base64,{base64.b64encode(image).decode()}"
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": 0,
            # Deterministisch und strikt: der Prompt verlangt reines JSON.
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        }

        log.info("llm.request", extra={"provider": self.name, "bytes": len(image)})
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LlmError(f"{self.name}: Netzwerkfehler: {exc}") from exc

        if response.status_code >= 400:
            # Den Providertext mitnehmen — „die LLM-Anbindung geht nicht" muss
            # diagnostizierbar sein, und der Text landet am Bon.
            raise LlmError(f"{self.name}: HTTP {response.status_code}: {response.text[:400]}")

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            raise LlmError(f"{self.name}: unerwartete Antwortstruktur: {exc}") from exc

        if isinstance(content, list):
            # Manche Provider liefern Content-Parts statt eines Strings.
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise LlmError(f"{self.name}: leere Antwort")

        log.info("llm.response", extra={"provider": self.name, "chars": len(content)})
        return content
