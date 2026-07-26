from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.integrations.llm.base import VisionLLM
from app.integrations.llm.null import NullVisionLLM
from app.integrations.llm.openai_compatible import LLMError, OpenAICompatibleVisionLLM

__all__ = ["LLMError", "VisionLLM", "get_vision_llm"]

log = get_logger(__name__)

# Providers served by the OpenAI-Vision-compatible adapter. OpenRouter and Ollama
# both speak the same chat-completions API — only the base URL / model / key
# differ, all from ENV — so they're aliases of the same adapter, not new code.
_OPENAI_COMPATIBLE = ("openai", "ollama", "openrouter")
_ALL_PROVIDERS = (*_OPENAI_COMPATIBLE, "none")

_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
# Canonical endpoint per provider, applied only when the operator left
# LLM_BASE_URL at the OpenAI default — so setting LLM_PROVIDER=openrouter alone
# (with a key + model) works, while an explicit base URL always wins.
_PROVIDER_BASE_URLS = {
    "openrouter": "https://openrouter.ai/api/v1",
}


def get_vision_llm(settings: Settings | None = None) -> VisionLLM:
    """Resolve the configured vision-LLM adapter. Unknown/`none` providers and
    a missing model fall back to the no-op so extraction always has an adapter.

    The fallback is logged at ``warning`` when it's likely a misconfiguration
    (a provider was set but isn't usable) — a silent no-op is exactly what makes
    "the LLM doesn't work" so hard to diagnose."""
    settings = settings or get_settings()
    provider = settings.llm_provider.lower()
    if provider in _OPENAI_COMPATIBLE and settings.llm_model:
        base_url = settings.llm_base_url
        # Provider has a known endpoint and the operator left the base URL at the
        # OpenAI default → use the provider's endpoint (e.g. openrouter.ai/api/v1).
        if (
            provider in _PROVIDER_BASE_URLS
            and base_url.rstrip("/") == _DEFAULT_OPENAI_BASE_URL
        ):
            base_url = _PROVIDER_BASE_URLS[provider]
        log.info(
            "llm adapter: openai-compatible",
            provider=provider,
            base_url=base_url,
            model=settings.llm_model,
        )
        return OpenAICompatibleVisionLLM(
            base_url=base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
        )

    if provider != "none":
        # A provider was configured but we can't use it — surface why instead of
        # silently degrading to manual entry.
        reason = (
            f"unbekannter Provider '{provider}' (unterstützt: {', '.join(_ALL_PROVIDERS)})"
            if provider not in _OPENAI_COMPATIBLE
            else "LLM_MODEL ist leer"
        )
        log.warning(
            "llm adapter: falling back to no-op (extraction will need manual review)",
            provider=provider,
            reason=reason,
        )
    else:
        # The default. Not an error, but make it explicit in the log — otherwise
        # "why does every photo land in needs_review?" has no visible answer.
        # (Text-PDF eBons still work without a model; only photos/scans need one.)
        log.info(
            "llm adapter: none — no vision model configured; "
            "photo/scan receipts go to needs_review (set LLM_PROVIDER=openrouter to enable)"
        )
    return NullVisionLLM()
