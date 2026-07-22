class NullVisionLLM:
    """No-op fallback used when ``LLM_PROVIDER=none`` (the default) or no model
    is configured. Signals "no extraction" so the receipt lands in
    ``needs_review`` for manual entry, keeping the app fully runnable without
    any LLM."""

    async def extract(self, *, image_bytes: bytes, media_type: str, prompt: str) -> str | None:
        return None
