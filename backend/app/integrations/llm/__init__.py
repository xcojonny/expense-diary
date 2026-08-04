"""Modellauswahl aus der Konfiguration.

Wichtig: ein **konfigurierter, aber unbrauchbarer** Provider (unbekannter Name,
leeres `LLM_MODEL`) wird laut geloggt und fällt nicht still auf No-op zurück.
Genau dieses stille Zurückfallen macht „warum erkennt er nichts?" unlösbar.
"""

from __future__ import annotations

from app.core.config import LlmProvider, Settings
from app.core.logging import get_logger
from app.integrations.llm.base import LlmError, VisionModel
from app.integrations.llm.null import NullVisionModel
from app.integrations.llm.openai_compatible import OpenAiCompatibleVisionModel

log = get_logger(__name__)

_DEFAULT_BASE_URLS = {
    LlmProvider.OPENAI: "https://api.openai.com/v1",
    LlmProvider.OPENROUTER: "https://openrouter.ai/api/v1",
    LlmProvider.OLLAMA: "http://localhost:11434/v1",
}

# Testeinstiegspunkt: der Extraktionsdienst nimmt dieses Modell, wenn gesetzt.
_override: VisionModel | None = None


def set_vision_model(model: VisionModel | None) -> None:
    """Modell überschreiben (Tests injizieren hier einen Fake)."""
    global _override
    _override = model


def build_vision_model(settings: Settings) -> VisionModel:
    if _override is not None:
        return _override

    provider = settings.llm_provider
    if provider is LlmProvider.NONE:
        return NullVisionModel()

    if not settings.llm_model:
        log.warning(
            "llm.misconfigured",
            extra={"provider": provider.value, "reason": "LLM_MODEL ist leer"},
        )
        return NullVisionModel()

    return OpenAiCompatibleVisionModel(
        provider=provider.value,
        base_url=settings.llm_base_url or _DEFAULT_BASE_URLS[provider],
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


__all__ = [
    "LlmError",
    "NullVisionModel",
    "VisionModel",
    "build_vision_model",
    "set_vision_model",
]
