import base64
import time

import httpx

from app.core.logging import get_logger

log = get_logger(__name__)

# Cap the provider error body we log/store so a huge HTML error page can't blow
# up the log ring or the receipt.error column.
_ERR_BODY_MAX = 500


class LLMError(RuntimeError):
    """A vision-LLM call failed. The message is kept human-readable (includes the
    provider's own error text where available) so it is useful both in the admin
    log and on the receipt's ``error`` field."""


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
        url = f"{self.base_url}/chat/completions"

        # Log the request up front (without the image payload or key) so a stuck
        # or failing call is visible in the admin log even before it returns.
        log.info(
            "llm request",
            base_url=self.base_url,
            model=self.model,
            media_type=media_type,
            image_bytes=len(image_bytes),
            has_api_key=bool(self.api_key),
            timeout_s=self.timeout,
        )
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            log.warning(
                "llm timeout", base_url=self.base_url, model=self.model, timeout_s=self.timeout
            )
            raise LLMError(
                f"LLM-Zeitüberschreitung nach {self.timeout:g}s ({self.model} @ {self.base_url})"
            ) from exc
        except httpx.HTTPError as exc:
            log.warning("llm connection error", base_url=self.base_url, error=str(exc))
            raise LLMError(f"LLM nicht erreichbar ({self.base_url}): {exc}") from exc

        elapsed_ms = round((time.monotonic() - started) * 1000)
        if resp.status_code >= 400:
            body = resp.text[:_ERR_BODY_MAX]
            log.warning(
                "llm http error",
                base_url=self.base_url,
                model=self.model,
                status=resp.status_code,
                elapsed_ms=elapsed_ms,
                body=body,
            )
            raise LLMError(f"LLM-Fehler HTTP {resp.status_code} ({self.model}): {body}")

        body_json = resp.json()
        content = self._content_of(body_json)
        usage = body_json.get("usage") or {}
        log.info(
            "llm response",
            base_url=self.base_url,
            model=self.model,
            status=resp.status_code,
            elapsed_ms=elapsed_ms,
            content_chars=len(content) if content else 0,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
        if not content:
            raise LLMError(
                f"LLM lieferte eine leere Antwort ({self.model}). "
                "Modell evtl. nicht vision- oder JSON-fähig."
            )
        return content

    @staticmethod
    def _content_of(body: object) -> str | None:
        """Pull the assistant message text out of an OpenAI-shaped response,
        tolerating providers that return no choices / a non-string content."""
        if not isinstance(body, dict):
            return None
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        return content if isinstance(content, str) else None
