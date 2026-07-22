import base64

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)


class OpenAICompatibleVisionLLM:
    """Talks to any OpenAI-Vision-compatible chat-completions endpoint.

    Covers both ``LLM_PROVIDER=openai`` (api.openai.com or a compatible proxy)
    and ``LLM_PROVIDER=ollama`` (Ollama exposes the same API under /v1) — the
    only difference is base URL / model / key, all from ENV. The image is sent
    inline as a data URL; ``response_format=json_object`` nudges compliant
    models to emit bare JSON.
    """

    def __init__(self, *, base_url: str, model: str, api_key: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    async def extract(self, *, image_bytes: bytes, media_type: str, prompt: str) -> str | None:
        data_url = f"data:{media_type};base64,{base64.b64encode(image_bytes).decode()}"
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            body = resp.json()
        content = body["choices"][0]["message"]["content"]
        return content if isinstance(content, str) else None
