from app.core.config import Settings, get_settings
from app.integrations.llm.base import VisionLLM
from app.integrations.llm.null import NullVisionLLM
from app.integrations.llm.openai_compatible import OpenAICompatibleVisionLLM

__all__ = ["VisionLLM", "get_vision_llm"]


def get_vision_llm(settings: Settings | None = None) -> VisionLLM:
    """Resolve the configured vision-LLM adapter. Unknown/`none` providers and
    a missing model fall back to the no-op so extraction always has an adapter."""
    settings = settings or get_settings()
    provider = settings.llm_provider.lower()
    if provider in ("openai", "ollama") and settings.llm_model:
        return OpenAICompatibleVisionLLM(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
        )
    return NullVisionLLM()
