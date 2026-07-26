from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.integrations.llm.base import VisionLLM
from app.integrations.llm.null import NullVisionLLM
from app.integrations.llm.openai_compatible import LLMError, OpenAICompatibleVisionLLM

__all__ = ["LLMError", "VisionLLM", "get_vision_llm"]

log = get_logger(__name__)

_SUPPORTED_PROVIDERS = ("openai", "ollama")


def get_vision_llm(settings: Settings | None = None) -> VisionLLM:
    """Resolve the configured vision-LLM adapter. Unknown/`none` providers and
    a missing model fall back to the no-op so extraction always has an adapter.

    The fallback is logged at ``warning`` when it's likely a misconfiguration
    (a provider was set but isn't usable) — a silent no-op is exactly what makes
    "the LLM doesn't work" so hard to diagnose."""
    settings = settings or get_settings()
    provider = settings.llm_provider.lower()
    if provider in _SUPPORTED_PROVIDERS and settings.llm_model:
        log.info(
            "llm adapter: openai-compatible",
            provider=provider,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
        return OpenAICompatibleVisionLLM(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    if provider != "none":
        # A provider was configured but we can't use it — surface why instead of
        # silently degrading to manual entry.
        reason = (
            f"unbekannter Provider '{provider}' (unterstützt: "
            f"{', '.join(_SUPPORTED_PROVIDERS)}, none)"
            if provider not in _SUPPORTED_PROVIDERS
            else "LLM_MODEL ist leer"
        )
        log.warning(
            "llm adapter: falling back to no-op (extraction will need manual review)",
            provider=provider,
            reason=reason,
        )
    return NullVisionLLM()
